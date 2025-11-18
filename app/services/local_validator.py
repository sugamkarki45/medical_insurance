
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

# copayment option is removed as the copayment information is directly stored in the eligibility field of patient table and we can get that from the database
# def _is_exempt_from_copay(patient: Dict, hospital_type: str, rules: Dict) -> bool:
#     """Check co-payment exemption based on IMIS data."""
#     exempt = rules["co-payment_method"]

#     # Age exemption
#     if patient.get("age", 0) >= exempt["exempt_age"]:
#         return True

#     # Category exemption
#     family_category = patient.get("family", {}).get("category", "").lower()
#     if family_category in [c.lower() for c in exempt["exempt_categories"]]:
#         return True


#     return False


# def _calculate_copay(approved_amount: Decimal, is_exempt: bool, rules: Dict) -> Decimal:
#     if is_exempt:
#         return Decimal("0")
#     return (approved_amount * Decimal(str(rules["co-payment_method"]["co_payment_percentage"]))) / 100


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

        ticket_days = cat_rules.get("ticket_valid_days", 7)
        use_same_claim_code = cat_rules.get("use_same_claim_code_within_validity", True)
        require_referral = cat_rules.get("require_referral_for_interdepartmental_consultation", True)
        require_same_day_submit = cat_rules.get("submit_daily_after_service", True)

        if claim.opd_code:
            for prev in previous_claims:
                if prev.opd_code == claim.opd_code:
                    days_diff = (claim.visit_date - prev.claim_date).days
                    if 0 < days_diff < ticket_days:
                        # OK – within validity
                        pass
                    elif days_diff >= ticket_days:
                        warnings.append(
                            f"OPD ticket expired ({days_diff} days). New ticket required."
                        )


        if use_same_claim_code:
            for prev in previous_claims:
                days_diff = (claim.visit_date - prev.claim_date).days  #previoous claim visit date need to be taken 
                if 0 <= days_diff < ticket_days and prev.claim_code != claim.claim_code:
                    warnings.append(
                        "Same OPD episode detected; claim_code MUST remain the same for all visits."
                    )

# check these three rules later when the claim object is updated to have department, referral_provided, submit_date, visit_date fields
        # if require_referral:
        #     for prev in previous_claims:
        #         if prev.department != claim.department:
        #             if not claim.referral_provided:
        #                 warnings.append(
        #                     f"Inter-department visit requires referral documentation."
        #                 )


        # if require_same_day_submit:
        #     if claim.submit_date.date() != claim.visit_date.date():
        #         warnings.append("OPD claims must be submitted on the same date of service.")

#IPD and emergency rules implementation
    if category in ("Emergency", "IPD"):
        submit_at_discharge = cat_rules.get("submit_at_discharge", True)

        if submit_at_discharge and claim.claim_time != "discharge":
            warnings.append(f"{category} claims must be submitted at discharge.")
    if category == "IPD" and cat_rules.get("package_based_claim_only", True):
        if not claim.is_package:
            warnings.append("IPD claims must be package based according to IMIS rules.")

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

        if not data:
            item_result["warnings"].append("Item not found in HIB catalog.")
            items_output.append(item_result)
            continue

        rate = Decimal(str(data.get("rate_npr", item.cost)))
        qty = Decimal(str(item.quantity))
        raw_amount = rate * qty

        # Non-covered services (spectacles, hearing aid, etc.) 
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

        # Capping 
        capping = data.get("capping", {})
        max_per_visit = capping.get("max_per_visit") or rules.get("max_per_visit_default")

        if max_per_visit is not None and qty > max_per_visit:
            item_result["warnings"].append(
                f"Quantity exceeds max per visit ({max_per_visit}). Capped."
            )
            qty = Decimal(str(max_per_visit))
            raw_amount = rate * qty

        # Time-based capping 
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

        # Surgery & Medical Management  
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

        # Surgery package
        if data.get("is_surgery_package"):
            if item.item_code in seen_surgery_packages:
                item_result["warnings"].append("Surgery package already claimed. Pre-op not allowed separately.")
                approved_amount = Decimal(0)
            else:
                seen_surgery_packages.add(item.item_code)

        # Bed charge cap 
        if "bed" in item.name.lower():
            max_bed = rules["general_rules"]["max_bed_charge_per_day"]
            if approved_amount > max_bed:
                item_result["warnings"].append(f"Bed charge capped at NPR {max_bed}/day.")
                approved_amount = Decimal(str(max_bed))

        patient = db.query(Patient).filter(Patient.patient_code == claim.patient_id).first()

#copayment calculation from eligibility field
        raw_copay = patient.Copayment

        if raw_copay is None:# if it is null or not present
            copayment_decimal = Decimal("0")  
        else:
            if isinstance(raw_copay, (int, float, Decimal)):
                copayment_decimal = Decimal(raw_copay)
            else:#clean if it is string
                cleaned = str(raw_copay).replace("%", "").strip()
                if not cleaned.replace(".", "", 1).isdigit():
                    raise ValueError(f"Invalid eligibility value: {raw_copay}")
                copayment_decimal = Decimal(cleaned)


        item_result["claimable"] = len(item_result["warnings"]) == 0 or approved_amount > 0
        item_result["approved_amount"] = float(approved_amount.quantize(Decimal("0.01")))

        copay_amount = approved_amount * copayment_decimal
        item_result["copay_amount"] = float(copay_amount.quantize(Decimal("0.01")))

        total_copay += copay_amount
        total_approved_local += approved_amount
        items_output.append(item_result)


        # Final validity
    is_valid = len(warnings) == 0 and all(i["claimable"] for i in items_output)

    total_claimable = total_approved_local - total_copay

    return{
        "is_locally_valid": is_valid,
        "warnings": warnings,
        "items": items_output,
        "total_approved_local": float(total_approved_local.quantize(Decimal("0.01"))),
        "total_copay": float(total_copay.quantize(Decimal("0.01"))),
        "net_claimable": float(total_claimable.quantize(Decimal("0.01"))),
        "applied_rules_version": rules["rules_version"],
        }