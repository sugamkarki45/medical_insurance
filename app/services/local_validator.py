
from datetime import timedelta,date
from typing import Dict, List, Any, Optional
from decimal import Decimal
from model import ClaimInput, ClaimableItem
from rule_loader import get_rules, get_med, get_package
from sqlalchemy.orm import Session
from insurance_database import Claim, Patient, EligibilityCache
from collections import defaultdict


def _get_previous_claims_for_patient(db: Session, patient_imis_id: str) -> List[Claim]:
#latest claims first
    return (
        db.query(Claim)
        .join(Patient)
        .filter(Patient.patient_code == patient_imis_id)
        .order_by(Claim.claim_date.desc())
        .all()
    )


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

    patient = db.query(Patient).filter(Patient.patient_code == claim.patient_id).first()

#rules according to category
    category = claim.service_type  # "OPD", "IPD", "Emergency"
    cat_rules = rules["claim_categories"].get(category, {}).get("rules", {})

    if category == "OPD":

        ticket_days = cat_rules.get("ticket_valid_days", 7)
        use_same_claim_code = cat_rules.get("use_same_claim_code_within_validity", True)
        require_referral = cat_rules.get("require_referral_for_interdepartmental_consultation", True)
        require_same_day_submit = cat_rules.get("submit_daily_after_service", True)

        if claim.service_code:
            for prev in previous_claims:
                if prev.service_code == claim.service_code:
                    days_diff = (claim.visit_date - prev.claim_date).days
                    if 0 < days_diff < ticket_days:
                        pass
                    elif days_diff >= ticket_days:
                        warnings.append(f"OPD ticket expired . New ticket required.") #({(date.today() - claim.visit_date).days} days) calculate the days and add if you want



        if use_same_claim_code:
            same_episode_detected = any(
                0 <= (claim.visit_date - prev.claim_date).days < ticket_days and prev.claim_code != claim.claim_code
                for prev in previous_claims
            )
            if same_episode_detected:
                warnings.append("Same OPD episode detected; claim_code MUST remain the same for all visits.")


# #check these three rules later when the claim object is updated to have department, referral_provided, submit_date, visit_date fields
#         if require_referral:
#             for prev in previous_claims:
#                 if prev.department != claim.department:
#                     if not claim.referral_provided:
#                         warnings.append(
#                             f"Inter-department visit requires referral documentation."
#                         )


#         if require_same_day_submit:
#             if claim.submit_date.date() != claim.visit_date.date():
#                 warnings.append("OPD claims must be submitted on the same date of service.")

#IPD and emergency rules implementation
        if category in ("Emergency", "IPD"):
            submit_at_discharge = cat_rules.get("submit_at_discharge", True)

            if submit_at_discharge and claim.claim_time != "discharge":
                warnings.append(f"{category} claims must be submitted at discharge.")
        if category == "IPD" and cat_rules.get("package_based_claim_only", True):
            if not claim.is_package:
                warnings.append("IPD claims must be package based according to IMIS rules.")


#processing of claiumable items
    seen_surgery_packages = set()
    surgery_disease_count = defaultdict(int)  # disease → count of surgery claims

    for item in claim.claimable_items:
        approved_amount = Decimal("0")  
        copay_amount = Decimal("0")   
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
        time_based = capping.get("time_based", {})
        max_units_in_window = time_based.get("max_per_visit")  # maximum units allowed
        window_days = time_based.get("max_days")           # rolling window in days

        if window_days and max_units_in_window:
            start_date = claim.visit_date - timedelta(days=window_days)
            # sum all previous quantities of this item within the window
            used_qty = sum(
                Decimal(str(c.quantity))
                for c in previous_claims
                if c.item_code == item.item_code and start_date <= c.claim_date <= claim.visit_date
            )

            available_qty = Decimal(max_units_in_window) - used_qty
            if qty > available_qty:
                item_result["warnings"].append(
                    f"Only {available_qty} units left in the last {window_days}-day window for {item.item_code}."
                )
                qty = max(Decimal(0), available_qty)
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


# Fetch latest eligibility cache entry for the patient_uuid
    elig_cache = (
        db.query(EligibilityCache)
        .filter(EligibilityCache.patient_uuid == patient.patient_uuid)
        .order_by(EligibilityCache.id.desc())
        .first()
    )

    # fallback to zero if cache doesn't exist
    allowed_money = Decimal(str(elig_cache.allowed_money)) if elig_cache and elig_cache.allowed_money else Decimal("0")
    used_money = Decimal(str(elig_cache.used_money)) if elig_cache and elig_cache.used_money else Decimal("0")
    available_money = allowed_money - used_money

    if available_money <= 0:
        warnings.append(
            f"Patient has no remaining balance (allowed: {allowed_money}, used: {used_money}), but claim is locally valid."
        )


# here this is to fetch the amount from raw eligibility field if elig_cache is not present

   # fallback to empty dict
    # elig = elig_cache.raw_response if elig_cache and elig_cache.raw_response else {}
    # allowed_money = used_money = Decimal("0")
    # insurance = elig.get("insurance", [])

    # if insurance:
    #     benefit_balances = insurance[0].get("benefitBalance", [])
    #     if benefit_balances:
    #         first_balance = benefit_balances[0]
    #         first_financial = first_balance.get("financial", [{}])[0]  # first financial entry
    #         allowed_money = Decimal(str(first_financial.get("allowedMoney", {}).get("value", 0)))
    #         used_money = Decimal(str(first_financial.get("usedMoney", {}).get("value", 0)))






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

    return {
        "is_locally_valid": is_valid,
        "warnings": warnings,
        "items": items_output,
        "total_approved_local": float(total_approved_local.quantize(Decimal("0.01"))),
        "total_copay": float(total_copay.quantize(Decimal("0.01"))),
        "net_claimable": float(total_claimable.quantize(Decimal("0.01"))),
        "applied_rules_version": rules["rules_version"],
        "allowed_money": float(allowed_money),
        "used_money": float(used_money),
        "available_money": float(available_money),
    }