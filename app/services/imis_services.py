import os
import base64
import httpx
from dotenv import load_dotenv

load_dotenv()

IMIS_BASE_URL = "http://imislegacy.hib.gov.np/api/api_fhir"
IMIS_USERNAME = os.getenv("IMIS_USERNAME") or ""
IMIS_PASSWORD = os.getenv("IMIS_PASSWORD") or ""
REMOTE_USER = os.getenv("REMOTE_USER", "")

if not IMIS_USERNAME or not IMIS_PASSWORD:
    raise ValueError("Missing IMIS credentials in environment variables.")

def get_auth_header():
    token = base64.b64encode(f"{IMIS_USERNAME}:{IMIS_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    if REMOTE_USER:
        headers["remote-user"] = REMOTE_USER
    return headers


async def get_patient_info(patient_identifier: str):
    url = f"{IMIS_BASE_URL}/Patient/?identifier={patient_identifier}"
    headers = get_auth_header()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        print(f"[IMIS] Failed to get patient info ({response.status_code}): {response.text}")
        return {"success": False, "status": response.status_code, "data": None}


async def check_eligibility(patient_identifier: str):
    patient_data = await get_patient_info(patient_identifier)
    if not patient_data["success"] or not patient_data["data"].get("entry"):
        return {"success": False, "reason": "Patient not found"}

    patient_uuid = patient_data["data"]["entry"][0]["resource"]["id"]

    url = f"{IMIS_BASE_URL}/EligibilityRequest/"
    headers = get_auth_header()
    body = {
        "resourceType": "EligibilityRequest",
        "patient": {"reference": f"Patient/{patient_uuid}"}
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=body)
        if response.status_code in [200, 201]:
            return {"success": True, "data": response.json()}
        print(f"[IMIS] Eligibility check failed ({response.status_code}): {response.text}")
        return {"success": False, "status": response.status_code, "data": None}


async def submit_claim(payload: dict):
    url = f"{IMIS_BASE_URL}/Claim/"
    headers = get_auth_header()
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        return {
            "success": response.status_code in [200, 201],
            "status": response.status_code,
            "response": response.text
        }


async def get_all_claims(
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    patient_identifier: str | None = None
) -> dict:
    """
    Fetch paginated list of claims from IMIS.
    Supports filtering by status and patient.
    """
    params = {
        "_count": page_size,
        "_page": page,
    }
    if status:
        params["status"] = status
    if patient_identifier:
        params["patient.identifier"] = patient_identifier

    url = f"{IMIS_BASE_URL}/Claim/"
    headers = get_auth_header()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            print(f"[IMIS] Failed to get claims ({response.status_code}): {response.text}")
            return {"success": False, "status": response.status_code, "error": response.text}
        except Exception as e:
            print(f"[IMIS] get_all_claims error: {e}")
            return {"success": False, "error": str(e)}


async def get_claim_by_uuid(claim_uuid: str) -> dict:
    """
    Fetch a single claim from IMIS by its UUID.
    """
    url = f"{IMIS_BASE_URL}/Claim/{claim_uuid}"
    headers = get_auth_header()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            if response.status_code == 404:
                return {"success": False, "status": 404, "error": "Claim not found in IMIS"}
            print(f"[IMIS] Failed to get claim {claim_uuid} ({response.status_code}): {response.text}")
            return {"success": False, "status": response.status_code, "error": response.text}
        except Exception as e:
            print(f"[IMIS] get_claim_by_uuid error: {e}")
            return {"success": False, "error": str(e)}

# import os
# import base64
# import httpx
# from dotenv import load_dotenv
# from typing import Optional, Dict, Any

# load_dotenv()

# IMIS_BASE_URL = "http://imislegacy.hib.gov.np/api/api_fhir"
# IMIS_USERNAME = os.getenv("IMIS_USERNAME") or ""
# IMIS_PASSWORD = os.getenv("IMIS_PASSWORD") or ""
# REMOTE_USER = os.getenv("REMOTE_USER", "")

# if not IMIS_USERNAME or not IMIS_PASSWORD:
#     raise ValueError("Missing IMIS credentials in environment variables.")


# def get_auth_header():
#     token = base64.b64encode(f"{IMIS_USERNAME}:{IMIS_PASSWORD}".encode()).decode()
#     headers = {"Authorization": f"Basic {token}"}
#     if REMOTE_USER:
#         headers["remote-user"] = REMOTE_USER
#     return headers

# #
# # ---------------------------
# #   PATIENT LOOKUP
# # ---------------------------
# #
# async def get_patient_info(identifier: str) -> Optional[Dict[str, Any]]:
#     url = f"{IMIS_BASE_URL}/Patient/?identifier={identifier}"
#     headers = get_auth_header()

#     try:
#         async with httpx.AsyncClient(timeout=20.0) as client:
#             resp = await client.get(url, headers=headers)
#     except Exception as e:
#         print(f"[IMIS] Patient lookup error: {e}")
#         return None

#     if resp.status_code != 200:
#         print(f"[IMIS] Patient lookup failed ({resp.status_code}): {resp.text}")
#         return None

#     data = resp.json()
#     if not data.get("entry"):
#         return None

#     return data


# #
# # ---------------------------
# #   ELIGIBILITY CHECK
# # ---------------------------
# #
# async def check_eligibility(patient_uuid: str) -> Optional[Dict[str, Any]]:
#     url = f"{IMIS_BASE_URL}/EligibilityRequest/"
#     headers = get_auth_header()
#     payload = {
#         "resourceType": "EligibilityRequest",
#         "patient": {"reference": f"Patient/{patient_uuid}"}
#     }

#     try:
#         async with httpx.AsyncClient(timeout=30.0) as client:
#             resp = await client.post(url, headers=headers, json=payload)
#     except Exception as e:
#         print(f"[IMIS] Eligibility error: {e}")
#         return None

#     if resp.status_code // 100 != 2:
#         print(f"[IMIS] Eligibility failed ({resp.status_code}): {resp.text}")
#         return None

#     return resp.json()


# #
# # ---------------------------
# #   CLAIM SUBMISSION
# # ---------------------------
# #
# async def submit_claim(payload: dict) -> dict:
#     url = f"{IMIS_BASE_URL}/Claim/"
#     headers = get_auth_header()

#     try:
#         async with httpx.AsyncClient(timeout=60.0) as client:
#             resp = await client.post(url, headers=headers, json=payload)
#     except Exception as e:
#         return {"success": False, "error": str(e)}

#     return {
#         "success": resp.status_code // 100 == 2,
#         "status": resp.status_code,
#         "data": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
#     }
