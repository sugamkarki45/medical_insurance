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
