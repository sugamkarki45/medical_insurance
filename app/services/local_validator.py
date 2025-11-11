from rule_loader import get_rules, get_med, get_package
from model import ClaimInput
from typing import Dict

def prevalidate_claim(claim: ClaimInput) -> Dict:
    rules = get_rules()
    warnings = []
    items = []
    total_approved = 0

    for item in claim.claimable_items:
        med = get_med(item.item_code)
        pkg = get_package(item.item_code)
        data = med or pkg

        # If item not found in claimable nmedicines then, it's not claimable
        if not data:
            warnings.append(f"{item.name} is not claimable as per HIB guideline.")
            items.append({
                "item_code": item.item_code,
                "item_name": item.name,
                "claimable": False,
                "approved_amount": 0
            })
            continue

        rate = data.get("rate_npr", item.cost)
        approved_amount = rate * item.quantity

        # capping check 
        capping = data.get("capping", {})
        max_per_visit = capping.get("max_per_visit")
        time_based = capping.get("time_based")

        if max_per_visit is not None and item.quantity > max_per_visit:
            warnings.append(
                f"{item.name}: Quantity ({item.quantity}) exceeds max per visit limit ({max_per_visit})."
            )
            # Limit approval only up to allowed quantity
            approved_amount = rate * max_per_visit

        if time_based and isinstance(time_based, dict):
            days = time_based.get("days")
            max_total = time_based.get("max_total")
            if days and max_total:
                warnings.append(
                    f"{item.name}: Claimable only up to {max_total} units per {days} days as per HIB rule."
                )

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
