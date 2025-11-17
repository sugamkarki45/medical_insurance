
from datetime import timedelta
from typing import Dict, List, Any, Optional
from decimal import Decimal
from model import ClaimInput, ClaimableItem
from rule_loader import get_rules, get_med, get_package
from sqlalchemy.orm import Session
from insurance_database import Claim, Patient
from collections import defaultdict


def _get_previous_claims_for_patient(db: Session, patient_imis_id: str) -> List[Claim]:
    """Fetch all *persisted* claims for the patient (by IMIS ID → patient_code)."""
    return (
        db.query(Claim)
        .join(Patient)
        .filter(Patient.patient_code == patient_imis_id)
        .all()
    )


def _is_exempt_from_copay(patient: Dict, hospital_type: str, rules: Dict) -> bool:
    """Check co-payment exemption based on IMIS data."""
    exempt = rules["co-payment_method"]

    # Age exemption
    if patient.get("age", 0) >= exempt["exempt_age"]:
        return True

    # Category exemption
    family_category = patient.get("family", {}).get("category", "").lower()
    if family_category in [c.lower() for c in exempt["exempt_categories"]]:
        return True


    return False


def _calculate_copay(approved_amount: Decimal, is_exempt: bool, rules: Dict) -> Decimal:
    if is_exempt:
        return Decimal("0")
    return (approved_amount * Decimal(str(rules["co-payment_method"]["co_payment_percentage"]))) / 100


def prevalidate_claim(claim: ClaimInput, db: Session) -> Dict[str, Any]:
    """
    Fully validate a claim against the HIB rule JSON.
    Returns a rich validation dict.
    """
    rules = get_rules()
    warnings: List[str] = []
    items_output: List[Dict] = []
    total_approved_local = Decimal("0")
    total_copay = Decimal("0")

#to load previous claims
    previous_claims = _get_previous_claims_for_patient(db, claim.patient_id)

#rules according to category
    category = claim.service_type  # "OPD", "IPD", "Emergency"
    cat_rules = rules["claim_categories"].get(category, {}).get("rules", {})

    if category == "OPD":
        ticket_days = cat_rules.get("ticket_valid_days")
        if ticket_days and claim.opd_code:
            for prev in previous_claims:
                if prev.opd_code == claim.opd_code:
                    days_diff = (claim.visit_date - prev.claim_date).days
                    if 0 < days_diff < ticket_days:
                        warnings.append(
                            f"Same diagnosis claimed {days_diff} day(s) ago. "
                            f"Must wait {ticket_days} days."
                        )

        if cat_rules.get("different_claim_code_per_day"):
            same_day_codes = [
                p.claim_code for p in previous_claims
                if p.claim_date.date() == claim.visit_date.date()
            ]
            if claim.claim_code in same_day_codes:
                warnings.append("Claim code must be unique per day (OPD rule).")

        if cat_rules.get("require_different_claim_code_per_consultation"):
            # Assume consultation = department + diagnosis
            key = (claim.department, claim.diagnosis_code)
            for prev in previous_claims:
                if (prev.department, getattr(prev, "diagnosis_code", None)) == key:
                    warnings.append("Same consultation (dept + diagnosis) already claimed.")

#IPD and emergency rules implementation
    if category in ("Emergency", "IPD"):
        allowed_time = cat_rules.get("claim_time")
        if allowed_time == "during_discharge" and claim.claim_time != "discharge":
            warnings.append(f"{category} claims can only be submitted during discharge.")

#here referral logic is not required as local validation cannot be done for that
    # referral_rules = rules["rules_regarding_referal"]
    # is_emergency = category == "Emergency"
    # requires_referral = (
    #     not is_emergency and referral_rules["require_referal_slip_for_non_emergency_cases"]
    # )

    # if requires_referral:
    #     if not claim.referral_slip_code:
    #         warnings.append("Referral slip required for non-emergency claim.")
    #     elif claim.first_service_point not in referral_rules["first_service_points"]:
    #         warnings.append(
    #             f"First service point must be one of: {', '.join(referral_rules['first_service_points'])}"
    #         )
    #     elif claim.service_type not in referral_rules["allowed_service_type_after_referal"]:
    #         warnings.append(
    #             f"After referral, only {', '.join(referral_rules['allowed_service_type_after_referal'])} allowed."
    #         )

#processing of claiumable items
    seen_surgery_packages = set()
    surgery_disease_count = defaultdict(int)  # disease → count of surgery claims

    for item in claim.claimable_items:
        med = get_med(item.item_code)
        pkg = get_package(item.item_code)
        data = med or pkg

        item_result = {
            "item_code": item.item_code,
            "item_name": item.name,
            "quantity": item.quantity,
            "claimable": False,
            "approved_amount": 0,
            "copay_amount": 0,
            "warnings": [],
            "type": data["type"] if data else "unknown",
        }

        # ---- Item not in HIB catalog ----
        if not data:
            item_result["warnings"].append("Item not found in HIB catalog.")
            items_output.append(item_result)
            continue

        rate = Decimal(str(data.get("rate_npr", item.cost)))
        qty = Decimal(str(item.quantity))
        raw_amount = rate * qty

        # ---- Non-covered services (spectacles, hearing aid, etc.) ----
        non_covered = rules["non_covered_services"]["items"]
        for nc in non_covered:
            if nc["name"].lower() in item.name.lower() and not nc["claimable"]:
                threshold = nc.get("annual_cost_threshold_npr")
                if threshold:
                    # Sum previous + current
                    prev_spent = sum(
                        c.quantity * c.rate for c in previous_claims
                        if nc["name"].lower() in c.item_name.lower()
                    )
                    total = prev_spent + raw_amount
                    if total > threshold:
                        item_result["warnings"].append(
                            f"{nc['name']} exceeds annual limit of NPR {threshold}."
                        )
                        raw_amount = max(Decimal(0), Decimal(threshold) - prev_spent)
                else:
                    item_result["warnings"].append(f"{nc['name']} is not covered.")
                    raw_amount = Decimal(0)

        # ---- Capping (max_per_visit, time_based) ----
        capping = data.get("capping", {})
        max_per_visit = capping.get("max_per_visit") or rules.get("max_per_visit_default")

        if max_per_visit is not None and qty > max_per_visit:
            item_result["warnings"].append(
                f"Quantity exceeds max per visit ({max_per_visit}). Capped."
            )
            qty = Decimal(str(max_per_visit))
            raw_amount = rate * qty

        # Time-based capping (e.g., 30 units per 90 days)
        time_based = capping.get("time_based")
        if time_based and time_based.get("days") and time_based.get("max_total"):
            days = time_based["days"]
            max_total = time_based["max_total"]
            start = claim.visit_date - timedelta(days=days)
            used = sum(
                c.quantity for c in previous_claims
                if c.item_code == item.item_code and start <= c.claim_date <= claim.visit_date
            )
            available = max_total - used
            if qty > available:
                item_result["warnings"].append(
                    f"Only {available} units left in {days}-day window."
                )
                qty = max(Decimal(0), Decimal(available))
                raw_amount = rate * qty

        approved_amount = raw_amount

        # ---- Surgery & Medical Management % rules ----
        if data["type"] == "surgery":
            disease = claim.diagnosis_code
            surgery_disease_count[disease] += 1
            order = surgery_disease_count[disease]
            pct = rules["general_rules"]["surgery"]["claim_percentage"]
            multiplier = Decimal(str(pct.get("first_disease", 100) if order == 1 else pct.get("second_disease", 50))) / 100
            approved_amount = raw_amount * multiplier
            if multiplier < 1:
                item_result["warnings"].append(f"Surgery #{order}: {int(multiplier*100)}% claimable.")

        elif data["type"] == "medical_management":
            disease = claim.diagnosis_code
            order = len([c for c in previous_claims if c.diagnosis_code == disease and c.item_type == "medical_management"]) + 1
            pct = rules["general_rules"]["medical_management"]["claim_percentage"]
            multiplier = Decimal(str(pct.get("first_disease", 100) if order == 1 else pct.get("second_disease", 50))) / 100
            approved_amount = raw_amount * multiplier
            if multiplier < 1:
                item_result["warnings"].append(f"Medical mgmt #{order}: {int(multiplier*100)}% claimable.")

        # ---- Surgery package: block separate pre-op claims ----
        if data.get("is_surgery_package"):
            if item.item_code in seen_surgery_packages:
                item_result["warnings"].append("Surgery package already claimed. Pre-op not allowed separately.")
                approved_amount = Decimal(0)
            else:
                seen_surgery_packages.add(item.item_code)

        # ---- Bed charge cap ----
        if "bed" in item.name.lower():
            max_bed = rules["general_rules"]["max_bed_charge_per_day"]
            if approved_amount > max_bed:
                item_result["warnings"].append(f"Bed charge capped at NPR {max_bed}/day.")
                approved_amount = Decimal(str(max_bed))

        # ------------------------------------------------------------------
        # 5. Finalize item
        # ------------------------------------------------------------------
        item_result["claimable"] = len(item_result["warnings"]) == 0 or approved_amount > 0
        item_result["approved_amount"] = float(approved_amount.quantize(Decimal("0.01")))

        
#copayment implement garna baki chha
        # Co-payment (only if not exempt)
        # patient_imis = claim.imis_patient_info or {}  # passed from API or fetched
        # is_exempt = _is_exempt_from_copay(patient_imis, claim.hospital_type, rules)
        #copay = _calculate_copay(approved_amount, is_exempt, rules)
        # copay = _calculate_copay(approved_amount, rules)
        # item_result["copay_amount"] = float(copay.quantize(Decimal("0.01")))

        total_approved_local += approved_amount
        total_copay =0
        total_copay = Decimal(total_copay) 
        item_result["warnings"] = item_result["warnings"] 
        items_output.append(item_result)

    # ------------------------------------------------------------------
    # 6. Final response
    # ------------------------------------------------------------------
    is_valid = len(warnings) == 0 and all(i["claimable"] for i in items_output)

    return {
        "is_locally_valid": is_valid,
        "warnings": warnings ,
        "quantity": item.quantity,
        "items": items_output,
        "total_approved_local": float(total_approved_local.quantize(Decimal("0.01"))),
        "total_copay": float(total_copay.quantize(Decimal("0.01"))),
        "net_payable": float((total_approved_local - total_copay).quantize(Decimal("0.01"))),
        "applied_rules_version": rules["rules_version"],
    }



