import os
import base64
import httpx
from dotenv import load_dotenv

load_dotenv()

IMIS_BASE_URL = "http://imislegacy.hib.gov.np/api/api_fhir" 
IMIS_USERNAME = os.getenv("IMIS_USERNAME")
IMIS_PASSWORD = os.getenv("IMIS_PASSWORD")
REMOTE_USER = os.getenv("REMOTE_USER")


def get_auth_header():
    token = base64.b64encode(f"{IMIS_USERNAME}:{IMIS_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    if REMOTE_USER:  
        headers["remote-user"] = REMOTE_USER
    return headers


async def get_patient_info(patient_identifier: str):
    url = f"{IMIS_BASE_URL}/Patient/?identifier={ patient_identifier}"
    headers = get_auth_header()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return None

async def check_eligibility(patient_identifier: str):
    patient_data = await get_patient_info(patient_identifier)
    if not patient_data or "entry" not in patient_data or not patient_data["entry"]:
        return None

    patient_uuid = patient_data["entry"][0]["resource"]["id"]

    url = f"{IMIS_BASE_URL}/EligibilityRequest/"
    headers = get_auth_header()
    body = {
        "resourceType": "EligibilityRequest",
        "patient": {"reference": f"Patient/{patient_uuid}"}
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=body)
        return response.json() if response.status_code in [200, 201] else None

async def submit_claim(payload: dict):
    url = f"{IMIS_BASE_URL}/Claim/"
    headers = get_auth_header()
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        return {
            "status": response.status_code,
            "response": response.text
        }
