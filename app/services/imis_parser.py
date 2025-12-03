from datetime import datetime


def parse_eligibility_response(raw):
    """
    Converts raw IMIS EligibilityResponse to a flat dict.
    Returns None if parsing fails.
    """
    if not raw or not raw.get("success"):
        return None

    data = raw.get("data", {})

    try:
        insurance = data["insurance"][0]

        balance = insurance["benefitBalance"][0]
        fin = balance["financial"][0]

        allowed = fin["allowedMoney"]["value"]
        used = fin["usedMoney"]["value"]
        category = balance["category"]["text"]
        contract_ref = insurance.get("contract", {}).get("reference", "")
        policy_id = None
        policy_expiry = None

        if contract_ref:
            parts = contract_ref.split("/")
            if len(parts) >= 3:
                policy_id = parts[1]
                expiry_raw = parts[2].strip()

                try:
                    policy_expiry = datetime.strptime(expiry_raw, "%Y-%m-%d %H:%M:%S").date()
                except Exception:
                    policy_expiry = None

        return {
            "category": category,
            "allowed_money": allowed,
            "used_money": used,
            "policy_id": policy_id,
            "policy_expiry": policy_expiry,
        }

    except Exception as e:
        print("ELIG PARSE ERROR:", e)
        return None




