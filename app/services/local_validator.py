
from datetime import timedelta
from typing import Dict, List, Any
from decimal import Decimal
from model import ClaimInput
from rule_loader import get_rules, get_med, get_package
from sqlalchemy.orm import Session
from insurance_database import  PatientInformation,ImisResponse
from collections import defaultdict
from fastapi import HTTPException
import random
import string

def _get_previous_claims_for_patient(db: Session, patient_imis_id: str) -> List[ImisResponse]:
#latest claims first
    return (
        db.query(ImisResponse)
        .join(PatientInformation)
        .filter(PatientInformation.patient_code == patient_imis_id)
        .order_by(ImisResponse.fetched_at.desc())
        .all()
    )

#claim code generation
# def _generate_claim_code():
#     return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# def _generate_or_reuse_claim_code(patient, claim_date, service_type, service_code, db):
#     # Always generate new code for IPD/Emergency
#     if service_type in {"IPD", "ER"}:
#         return _generate_claim_code()

#     # OPD logic
#     seven_days_ago = claim_date - timedelta(days=7)

#     last_claim = (
#         db.query(ImisResponse)
#         .filter(
#             ImisResponse.patient_id == patient.id,
#             ImisResponse.created_at >= seven_days_ago,
#             ImisResponse.created_at <= claim_date,
#         )# ImisResponse.service_type == "OPD",
#         .order_by(ImisResponse.created_at.desc())
#         .first()
#     )


#     if not last_claim:
#         return _generate_claim_code()

#     same_service = last_claim.service_code == service_code
#     ticket_valid = (claim_date - last_claim.claim_date).days < 7


#     if same_service and ticket_valid:
#         return last_claim.claim_code
#     return _generate_claim_code()



def prevalidate_claim(claim: ClaimInput, db: Session,allowed_money:Decimal=None, used_money:Decimal= None) -> Dict[str, Any]:#, claim_code:str=None
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

    patient = db.query(PatientInformation).filter(PatientInformation.patient_code == claim.patient_id).first()
#rules according to category
    category = claim.service_type  # "OPD", "IPD", "Emergency"
    cat_rules = rules["claim_categories"].get(category, {}).get("rules", {})

    if category == "OPD":

        ticket_days = cat_rules.get("ticket_valid_days", 7)
        use_same_claim_code = cat_rules.get("use_same_claim_code_within_validity", True)
        require_same_day_submit = cat_rules.get("submit_daily_after_service", True)
        cutoff = claim.visit_date - timedelta(days=ticket_days)

        last_opd_claim = (
            db.query(ImisResponse)
            .join(PatientInformation)
            .filter(PatientInformation.patient_code == claim.patient_id)
            .filter(ImisResponse.fetched_at >= cutoff)
            .order_by(ImisResponse.fetched_at.asc())
            .first()
        )#            .filter(ImisResponse.service_type == "OPD")


        # Check if a new ticket is required
        new_ticket_required = True
        if not last_opd_claim:
            new_ticket_required=False
        else:
            if last_opd_claim and claim.service_code:
                days_diff = (claim.visit_date - last_opd_claim.fetched_at.date()).days


                # Case 1: Same ticket still valid
                if 0 <= days_diff < ticket_days and claim.service_code == last_opd_claim.service_type:
                    new_ticket_required = False

                # Case 2: Different service code within validity → valid ticket, but warn
                elif 0 <= days_diff < ticket_days and claim.service_code != last_opd_claim.service_code:
                    new_ticket_required = False
                    warnings.append("The previous OPD ticket is still valid. No new ticket needed even for a different service. The claim code shall also be the same")

                # Case 3: Different service code + ticket expired → valid new service, no warning
                elif days_diff >= ticket_days and claim.service_code != last_opd_claim.service_code:
                    new_ticket_required = False

                # Case 4: Same service code + ticket expired → new ticket required
                elif days_diff >= ticket_days and claim.service_code == last_opd_claim.service_code:
                    new_ticket_required = True


        # Append warning only if a new ticket is actually required
            if new_ticket_required:
                warnings.append("OPD ticket expired. New ticket required.")

# check these three rules later when the claim object is updated to have department, referral_provided, submit_date, visit_date fields
#         if require_referral:
#             for prev in previous_claims:
#                 if prev.department != claim.department:
#                     if not claim.referral_provided:
#                         warnings.append(
#                             f"Inter-department visit requires referral documentation."
#                         )


        # if require_same_day_submit:
        #     if claim.visit_date != Claims.claim_date:
        #         warnings.append("OPD claims must be submitted on the same date of service.")



#IPD and emergency rules implementation
    if category in ("Emergency", "IPD"):
        submit_at_discharge = cat_rules.get("submit_at_discharge", True)
# claim time maybe included in the input to determine the claim has been submitted at discharge or not
        if submit_at_discharge and claim.claim_time != "discharge":
            warnings.append(f"{category} claims must be submitted at discharge.")
    # if category == "IPD" and cat_rules.get("package_based_claim_only", True):
    #     if not claim.is_package:
    #             warnings.append("IPD claims must be package based according to IMIS rules.")

        # Fetch latest eligibility cache entry for the patient_uuid
    if allowed_money is None or used_money is None:
        elig_cache = (
                db.query(PatientInformation)
                .filter(PatientInformation.patient_uuid == patient.patient_uuid)
                .order_by(PatientInformation.id.desc())
                .first()
        )
        available_money = Decimal("0")
        # fallback to zero if cache doesn't exist
        allowed_money = Decimal(str(elig_cache.allowed_money)) if elig_cache and elig_cache.allowed_money else Decimal("0")
        used_money = Decimal(str(elig_cache.used_money)) if elig_cache and elig_cache.used_money else Decimal("0")
    available_money = allowed_money - used_money
# now we will stop the claim if this condition is met instead of just giving a warning.
    if available_money <= 0:
            raise HTTPException(
                status_code=400, detail="This patient has no remaining balance")
            # warnings.append(
            #     f"Patient has no remaining balance (allowed: {allowed_money}, used: {used_money}), but claim is locally valid."
            # )
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
            item_result["warnings"].append("{item not found in HIB catalog.")
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
        max_per_visit = capping.get("max_per_visit")
        qty = Decimal(str(max_per_visit))
        if max_per_visit is not None and qty > max_per_visit:
            item_result["warnings"].append(
                f"Quantity exceeds max per visit ({max_per_visit}). Capped."
            )
            raw_amount = rate * qty

# Time-based capping 
        max_units_in_window = capping.get("max_per_visit")  # maximum units allowed
        window_days = capping.get("max_days")  # time window in days

        if window_days and max_units_in_window:

            visit_date = claim.visit_date
            start_date = visit_date - timedelta(days=window_days)

            # total used quantity for THIS item_code in the time window
            used_qty = Decimal("0")

            # 1. SUM all previous quantities for this item in the window
            for prev_claim in previous_claims:
                prev_date = prev_claim.fetched_at.date()

                # skip if outside the window
                if not (start_date <= prev_date <= visit_date):
                    continue

                prev_items = prev_claim.item_code or []
                for x in prev_items:
                    if x["item_code"] == item.item_code:
                        used_qty += Decimal(str(x["qty"]))

            # remaining units available
            available_qty = Decimal(str(max_units_in_window)) - used_qty

            if available_qty <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"No remaining units for {item.item_code}. "
                        f"Already fully used in the last {window_days}-day window."
                )

            # requested quantity
            qty = Decimal(str(item.quantity))

            if qty > available_qty:
                item_result["warnings"].append(
                    f"Only {available_qty} units can be claimed in {window_days}-day window for {item.item_code}. Remaining {qty-available_qty} number of {item.item_code} cannot be claimed."
                )
                qty = available_qty  # cap quantity

            # calculate amount
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
        else:
        # medicine, lab, urology, etc.
            approved_amount = raw_amount

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



#copayment calculation from eligibility field
        raw_copay = patient.copayment

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