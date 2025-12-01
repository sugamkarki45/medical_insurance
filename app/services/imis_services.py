# services/imis_services.py
from anyio import to_thread
import requests
import json
from fastapi import Depends, HTTPException, status
from insurance_database import get_db
from sqlalchemy.orm import Session
from datetime import datetime
from insurance_database import IMISSession

IMIS_BASE_URL = "http://imislegacy.hib.gov.np/api/api_fhir"

def get_imis_session(
    username: str,
    db: Session = Depends(get_db)
) -> requests.Session:
    sess = db.query(IMISSession).filter(IMISSession.username == username.lower()).first()
    if not sess:
        raise HTTPException(status_code=401, detail="No active IMIS session. Please login first.")
    if sess.expires_at and sess.expires_at < datetime.utcnow():
        db.delete(sess)
        db.commit()
        raise HTTPException(status_code=401, detail="IMIS session expired. Please login again.")

    session = requests.Session()
    try:
        session.cookies.update(json.loads(sess.session_cookie))
    except:
        raise HTTPException(status_code=500, detail="Corrupted session")

    session.headers.update({
        "Accept": "application/fhir+json",
        "Content-Type": "application/fhir+json",
        "remote-user": username.lower(),
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://imislegacy.hib.gov.np",
        "Referer": "http://imislegacy.hib.gov.np/Home.aspx",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"
    })
    return session


async def get_patient_info(patient_identifier: str, session: requests.Session):
    def fetch():
        url = f"{IMIS_BASE_URL}/Patient/?identifier={patient_identifier}"
        return session.get(url, timeout=20)
    resp = await to_thread.run_sync(fetch)
    print(f"[IMIS] Patient {patient_identifier} → {resp.status_code}")
    if resp.status_code == 200 and resp.json().get("total", 0) > 0:
        return {"success": True, "data": resp.json()}
    return {"success": False, "reason": "Patient not found"}


async def check_eligibility(patient_identifier: str, session: requests.Session):
    patient = await get_patient_info(patient_identifier, session)
    if not patient["success"]:
        return patient
    patient_uuid = patient["data"]["entry"][0]["resource"]["id"]

    def fetch():
        return session.post(
            f"{IMIS_BASE_URL}/EligibilityRequest/",
            json={"resourceType": "EligibilityRequest", "patient": {"reference": f"Patient/{patient_uuid}"}},
            timeout=30
        )
    resp = await to_thread.run_sync(fetch)
    if resp.status_code in [200, 201]:
        return {"success": True, "data": resp.json()}
    print(f"[IMIS] Eligibility failed ({resp.status_code}): {resp.text}")
    return {"success": False, "status": resp.status_code}


async def submit_claim(payload: dict, session: requests.Session):
    def fetch():
        return session.post(f"{IMIS_BASE_URL}/Claim/", json=payload, timeout=90)
    resp = await to_thread.run_sync(fetch)
    if resp.status_code in [200, 201]:
        return {"success": True, "data": resp.json()}
    print(f"[IMIS] Claim failed ({resp.status_code}): {resp.text}")
    return {"success": False, "status": resp.status_code, "response": resp.text}


async def get_all_claims(session: requests.Session, page: int = 1, page_size: int = 50,
                        status: str | None = None, patient_identifier: str | None = None):
    def fetch():
        params = {"_count": page_size, "_page": page}
        if status: params["status"] = status
        if patient_identifier: params["patient.identifier"] = patient_identifier
        return session.get(f"{IMIS_BASE_URL}/Claim/", params=params, timeout=40)
    resp = await to_thread.run_sync(fetch)
    if resp.status_code == 200:
        return {"success": True, "data": resp.json()}
    return {"success": False, "status": resp.status_code}


async def get_claim_by_uuid(claim_uuid: str, session: requests.Session):
    def fetch():
        return session.get(f"{IMIS_BASE_URL}/Claim/{claim_uuid}", timeout=30)
    resp = await to_thread.run_sync(fetch)
    if resp.status_code == 200:
        return {"success": True, "data": resp.json()}
    if resp.status_code == 404:
        return {"success": False, "error": "Claim not found"}
    return {"success": False, "status": resp.status_code}


        
def extract_copayment(bundle: dict):
    """
    Extracts copayment extension value from IMIS FHIR bundle.
    Returns None if not found.
    """
    try:
        entries = bundle.get("entry", [])
        if not entries:
            return None

        resource = entries[0].get("resource", {})
        extensions = resource.get("extension", [])

        for ext in extensions:
            if "Copayment" in ext.get("url", ""):
                # Prefer decimal, fallback to string
                return ext.get("valueDecimal") or ext.get("valueString")

        return None
    except Exception:
        return None




# import os
# import base64
# import httpx
# from dotenv import load_dotenv
# from sqlalchemy.orm import Session
# from datetime import datetime
# import requests
# from insurance_database import IMISSession
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


# async def  get_patient_info(patient_identifier: str ,session: requests.Session):
#     url = f"{IMIS_BASE_URL}/Patient/?identifier={patient_identifier}"
#     headers = get_auth_header()
#     async with httpx.AsyncClient(timeout=20.0) as client:
#         response = await client.get(url, headers=headers)
#         if response.status_code == 200:
#             return {"success": True, "data": response.json()}
#         print(f"[IMIS] Failed to get patient info ({response.status_code}): {response.text}")
#         return {"success": False, "status": response.status_code, "data": None}




# async def check_eligibility(patient_identifier: str,session: requests.Session):
#     patient_data = await get_patient_info(patient_identifier,session)
#     if not patient_data["success"] or not patient_data["data"].get("entry"):
#         return {"success": False, "reason": "Patient not found"}

#     patient_uuid = patient_data["data"]["entry"][0]["resource"]["identifier"]

#     url = f"{IMIS_BASE_URL}/EligibilityRequest/"
#     headers = get_auth_header()
#     body = {
#         "resourceType": "EligibilityRequest",
#         "patient": {"reference": f"Patient/{740500036}"},
#     }

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         response = await client.post(url, headers=headers, json=body)
#         if response.status_code in [200, 201]:
#             return {"success": True, "data": response.json()}
#         print(f"[IMIS] Eligibility check failed ({response.status_code}): {response.text}")
#         return {"success": False, "status": response.status_code, "data": None}


# async def submit_claim(payload: dict,session: requests.Session):
#     url = f"{IMIS_BASE_URL}/Claim/"
#     headers = get_auth_header()
#     async with httpx.AsyncClient(timeout=60.0) as client:
#         response = await client.post(url, headers=headers, json=payload)
#         return {
#             "success": response.status_code in [200, 201],
#             "status": response.status_code,
#             "response": response.text
#         }


# async def get_all_claims(
#     page: int = 1,
#     page_size: int = 50,
#     status: str | None = None,
#     patient_identifier: str | None = None
# ) -> dict:
#     """
#     Fetch paginated list of claims from IMIS.
#     Supports filtering by status and patient.
#     """
#     params = {
#         "_count": page_size,
#         "_page": page,
#     }
#     if status:
#         params["status"] = status
#     if patient_identifier:
#         params["patient.identifier"] = patient_identifier

#     url = f"{IMIS_BASE_URL}/Claim/"
#     headers = get_auth_header()

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         try:
#             response = await client.get(url, headers=headers, params=params)
#             if response.status_code == 200:
#                 return {"success": True, "data": response.json()}
#             print(f"[IMIS] Failed to get claims ({response.status_code}): {response.text}")
#             return {"success": False, "status": response.status_code, "error": response.text}
#         except Exception as e:
#             print(f"[IMIS] get_all_claims error: {e}")
#             return {"success": False, "error": str(e)}


# async def get_claim_by_uuid(claim_uuid: str) -> dict:
#     """
#     Fetch a single claim from IMIS by its UUID.
#     """
#     url = f"{IMIS_BASE_URL}/Claim/{claim_uuid}"
#     headers = get_auth_header()

#     async with httpx.AsyncClient(timeout=30.0) as client:
#         try:
#             response = await client.get(url, headers=headers)
#             if response.status_code == 200:
#                 return {"success": True, "data": response.json()}
#             if response.status_code == 404:
#                 return {"success": False, "status": 404, "error": "Claim not found in IMIS"}
#             print(f"[IMIS] Failed to get claim {claim_uuid} ({response.status_code}): {response.text}")
#             return {"success": False, "status": response.status_code, "error": response.text}
#         except Exception as e:
#             print(f"[IMIS] get_claim_by_uuid error: {e}")
#             return {"success": False, "error": str(e)}
        
        
# def extract_copayment(bundle: dict):
#     """
#     Extracts copayment extension value from IMIS FHIR bundle.
#     Returns None if not found.
#     """
#     try:
#         entries = bundle.get("entry", [])
#         if not entries:
#             return None

#         resource = entries[0].get("resource", {})
#         extensions = resource.get("extension", [])

#         for ext in extensions:
#             if "Copayment" in ext.get("url", ""):
#                 # Prefer decimal, fallback to string
#                 return ext.get("valueDecimal") or ext.get("valueString")

#         return None
#     except Exception:
#         return None


# def get_imis_session(db: Session, username: str):
#     sess = db.query(IMISSession).filter(IMISSession.username == username).first()

#     if not sess:
#         raise Exception("User not logged into IMIS")

#     if sess.expires_at < datetime.utcnow():
#         raise Exception("IMIS session expired. Please login again.")

#     session = requests.Session()
#     session.cookies.update(eval(sess.session_cookie))
#     return session
