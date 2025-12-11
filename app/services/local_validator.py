
from datetime import timedelta
from typing import Dict, List, Any
from decimal import Decimal
from app.model import ClaimInput
from app.rule_loader import get_rules, get_items,get_services
from sqlalchemy.orm import Session
from app.insurance_database import  PatientInformation,ImisResponse
from collections import defaultdict
from fastapi import HTTPException
import decimal

def _get_previous_claims_for_patient(db: Session, patient_imis_id: str) -> List[ImisResponse]:
    return (
        db.query(ImisResponse)
        .join(PatientInformation)
        .filter(PatientInformation.patient_code == patient_imis_id)
        .filter(ImisResponse.status.notin_(["rejected", "unknown"]))
        .order_by(ImisResponse.fetched_at.desc())
        .all()
    )


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

    patient = db.query(PatientInformation).filter(PatientInformation.patient_code == claim.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found in insurance database")

    if allowed_money is None or used_money is None:
        allowed_money = Decimal(str(patient.allowed_money or 0))
        used_money = Decimal(str(patient.used_money or 0))

    available_money = allowed_money - used_money
    if available_money <= 0:
            raise HTTPException(
                status_code=400, detail="This patient has no remaining balance")
    category = claim.service_type
    cat_rules = rules["claim_categories"].get(category, {}).get("rules", {})

    previous_claims = _get_previous_claims_for_patient(db, claim.patient_id)


    if category == "OPD":
        ticket_days = cat_rules.get("ticket_valid_days", 7)
        use_same_claim_code = cat_rules.get("use_same_claim_code_within_validity", True)
        require_same_day_submit = cat_rules.get("submit_daily_after_service", True)
        require_referral = cat_rules.get("require_referral_for_inter_department", True)
        cutoff = claim.visit_date - timedelta(days=ticket_days)


        last_opd_claim = (
            db.query(ImisResponse)
            .filter(ImisResponse.patient_id == claim.patient_id)
            .filter(ImisResponse.service_type == "OPD")
            .filter(ImisResponse.status.notin_(["rejected", "unknown"]))
            .order_by(ImisResponse.created_at.asc())
            .first()
        )
       

        new_ticket_required = True 

        if not last_opd_claim:
            new_ticket_required = False  
        else:
            days_diff = (claim.visit_date - last_opd_claim.created_at.date()).days
            # Case 1: Same service code, ticket still valid → no new ticket
            if 0 <= days_diff < ticket_days and claim.service_code == last_opd_claim.service_code:
                new_ticket_required = False

            # Case 2: Different service code, ticket still valid → warn, no new ticket
            elif 0 <= days_diff < ticket_days and claim.service_code != last_opd_claim.service_code:
                new_ticket_required = False
                warnings.append(
                    "Previous OPD ticket still valid. No new ticket needed for a different service. Claim code shall remain the same.")

            # Case 3: Different service code, ticket expired → valid new service, no warning
            elif days_diff >= ticket_days and claim.service_code != last_opd_claim.service_code:
                new_ticket_required = False

            # Case 4: Same service code, ticket expired → new ticket required
            elif days_diff >= ticket_days and claim.service_code == last_opd_claim.service_code:
                new_ticket_required = True



            # Inter-departmental referral check (only if ticket is valid)
            if require_referral and 0 <= days_diff < ticket_days:
                if last_opd_claim.department != claim.department:
                    if not getattr(claim, "referral_provided", False):
                        warnings.append(
                            "Inter-department OPD visit within ticket validity requires referral documentation."
                        )

#same day submission
            if require_same_day_submit:
                submit_date = getattr(claim, "submit_date", claim.visit_date)
                if submit_date != claim.visit_date:
                    warnings.append("OPD claims should ideally be submitted on the same date as the visit.")

        if new_ticket_required:
                    warnings.append("OPD ticket expired. New ticket required.")



    if category in ("ER", "IPD"):
        submit_at_discharge = cat_rules.get("submit_at_discharge", True)

        if submit_at_discharge and claim.claim_time != "discharge":
            warnings.append(f"{category} claims must be submitted at discharge.")

            
    seen_surgery_packages = set()
    surgery_disease_count = defaultdict(int)  
    medical_disease_count = defaultdict(int)
    for item in claim.claimable_items:
        approved_amount = Decimal("0")  
        copay_amount = Decimal("0")   
        med = get_items(item.item_code)
        pkg = get_services(item.item_code)
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

        if max_per_visit is not None:
            try:
                qty = Decimal(str(max_per_visit))
            except (ValueError, decimal.InvalidOperation):
                qty = Decimal("0")  
            if qty > Decimal(str(max_per_visit)):
                item_result["warnings"].append(
                    f"Quantity exceeds max per visit ({max_per_visit}). Capped."
                )
                raw_amount = rate * qty
        else:
            qty = Decimal("0") 


# Time-based capping 
        capping = data.get("capping", {})
        max_units_in_window = capping.get("max_per_visit")  # maximum units allowed
        window_days = capping.get("max_days")  # time window in days

        if max_units_in_window and window_days:
            visit_date = claim.visit_date
            start_date = visit_date - timedelta(days=window_days)

            # total used quantity for this item in the window
            used_qty = Decimal("0")
            for prev_claim in previous_claims:
                prev_date = prev_claim.fetched_at.date()
                if start_date <= prev_date <= visit_date:
                    for x in prev_claim.item_code or []:
                        if x["item_code"] == item.item_code:
                            used_qty += Decimal(str(x["qty"]))

            available_qty = Decimal(str(max_units_in_window)) - used_qty

            if available_qty <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"No remaining units for {item.item_code}. Already fully used in the last {window_days}-day window."
                )

            requested_qty = Decimal(str(item.quantity))
            if requested_qty > available_qty:
                item_result["warnings"].append(
                    f"Only {available_qty} units can be claimed in {window_days}-day window for {item.item_code}. "
                    f"Remaining {requested_qty - available_qty} cannot be claimed."
                )
                requested_qty = available_qty

            qty = requested_qty
            raw_amount = rate * qty
            approved_amount = raw_amount


        # Surgery & Medical Management  
        if data["type"] == "surgery":
            disease = tuple(claim.icd_codes) if claim.icd_codes else ("UNKNOWN",)

            surgery_disease_count[disease] += 1
            order = surgery_disease_count[disease]

            pct = rules["general_rules"]["surgery"]["claim_percentage"]
            multiplier = Decimal(str(
                pct["first_disease"] if order == 1 else pct.get("second_disease", 50)
            )) / 100

            approved_amount = raw_amount * multiplier

            if multiplier < 1:
                item_result["warnings"].append(
                    f"Surgery #{order}: {int(multiplier*100)}% claimable."
                )

        elif data["type"] == "medical_management":
            disease = tuple(claim.icd_codes) if claim.icd_codes else ("UNKNOWN",)

            medical_disease_count[disease] += 1
            order = medical_disease_count[disease]

            pct = rules["general_rules"]["medical_management"]["claim_percentage"]
            multiplier = Decimal(str(
                pct["first_disease"] if order == 1 else pct.get("second_disease", 50)
            )) / 100

            approved_amount = raw_amount * multiplier

            if multiplier < 1:
                item_result["warnings"].append(
                    f"Medical mgmt #{order}: {int(multiplier*100)}% claimable."
                )
        else:
            approved_amount = raw_amount

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