from datetime import timedelta
from typing import Dict, List
from model import ClaimInput
from rule_loader import get_rules, get_med, get_package
from sqlalchemy.orm import Session
from insurance_database import Claim

# def prevalidate_claim(claim: ClaimInput, previous_claims: List = None) -> Dict:


def prevalidate_claim(claim: ClaimInput, db: Session) -> Dict:
    rules = get_rules()
    
    # Fetch previous claims for this patient from DB
    previous_claims = db.query(Claim).filter(Claim.patient_id == claim.patient_id).all()
    
    rules = get_rules()
    
    warnings = []
    items = []
    total_approved = 0

    for item in claim.claimable_items:
        med = get_med(item.item_code)
        pkg = get_package(item.item_code)
        data = med or pkg

        if not data:
            warnings.append(f"{item.name} is not claimable as per HIB guideline.")
            items.append({"item_code": item.item_code, "item_name": item.name, "claimable": False, "approved_amount": 0})
            continue

        rate = data.get("rate_npr", item.cost)
        approved_amount = rate * item.quantity

        # ----- Capping -----
        capping = data.get("capping", {})
        max_per_visit = capping.get("max_per_visit") or rules.get("max_per_visit_default")
        time_based = capping.get("time_based")

        if max_per_visit is not None and item.quantity > max_per_visit:
            warnings.append(f"{item.name}: Quantity ({item.quantity}) exceeds max per visit ({max_per_visit})")
            approved_amount = rate * max_per_visit


        claim_category = claim.service_type  # e.g., "OPD", "IPD", "Emergency"
        category_rules = rules["claim_categories"].get(claim_category, {}).get("rules", {})


#Validation rule based logic
        # same_disease_days_limit
        if "ticket_valid_days" in category_rules:
            limit = category_rules["ticket_valid_days"]
            for prev in previous_claims:
                if getattr(prev, "diagnosis_code", None) == getattr(claim, "diagnosis_code", None):
                    if (claim.visit_date - prev.claim_date).days < limit:
                        warnings.append(
                            f"{item.name}: Cannot claim same diagnosis within {limit} days"
                        )

        # require_different_claim_code
        if category_rules.get("different_claim_code_per_day"):
            for prev in previous_claims:
                if prev.claim_code == claim.claim_code:
                    warnings.append(f"{item.name}: Duplicate claim code detected ({claim.claim_code})")

        # interdepartmental_consultation_required
        if category_rules.get("interdepartmental_consultation_required"):
            for prev in previous_claims:
                if prev.department != claim.department:
                    warnings.append(f"{item.name}: Interdepartmental consultation required")

        # claim_frequency example: once_per_diagnosis
        if category_rules.get("claim_frequency") == "once_per_diagnosis":
            for prev in previous_claims:
                if getattr(prev, "diagnosis_code", None) == getattr(claim, "diagnosis_code", None):
                    warnings.append(f"{item.name}: Already claimed for this diagnosis once")

        items.append({
            "item_code": item.item_code,
            "item_name": data["name"],
            "claimable": True,
            "approved_amount": approved_amount,
            "type": data.get("type", "item")
        })
        total_approved += approved_amount

    return {
        "warnings": warnings,
        "is_locally_valid": len(warnings) == 0,
        "items": items,
        "total_approved_local": total_approved
    }
#here time based is commented for now as the checking after the response from IMIS is not yet implemented
        # if time_based:
        #     days = time_based.get("days")
        #     max_total = time_based.get("max_total")
        #     if days and max_total:
        #         start_date = claim.visit_date - timedelta(days=days)
        #         total_used = sum(
        #             c.quantity for c in previous_claims
        #             if c.item_code == item.item_code and start_date <= c.claim_date <= claim.visit_date
        #         )
        #         if total_used + item.quantity > max_total:
        #             warnings.append(
        #                 f"{item.name}: Only {max_total} units allowed per {days} days; already claimed {total_used} units"
        #             )
        #             approved_amount = rate * max(0, max_total - total_used)

