# # app/router/claim.py
# from fastapi import APIRouter, Depends, HTTPException
# from model import ClaimInput,ClaimResponse
# from services.local_validator import prevalidate_claim
# from services import imis_services
# from dependencies import get_api_key
# from insurance_database import Session, engine,get_db


# router = APIRouter(prefix="/api", tags=["Claims"])

# @router.post("/prevalidate_claim", response_model=ClaimResponse) #, dependencies=[Depends(get_api_key)])   #the reason is the same
# async def prevalidate_claim_endpoint(input_data: ClaimInput, db: Session=Depends(get_db)):
#     result = prevalidate_claim(input_data)
#     return {
#         "is_locally_valid": result["is_locally_valid"],
#         "warnings": result["warnings"],
#         "items": result["items"],
#         "total_approved_local": result["total_approved_local"]
#     }

# @router.post("/validate_claim", response_model=ClaimResponse)#, dependencies=[Depends(get_api_key)])  #this is commented out for now for the testing purpose
# async def validate_claim_endpoint(input_data: ClaimInput):
#     local = prevalidate_claim(input_data)

#     patient_info = await imis_services.get_patient_info(input_data.patient_id)

#     if not patient_info or "entry" not in patient_info or not patient_info["entry"]:
#         raise HTTPException(status_code=404, detail="Patient not found in IMIS")


#     patient_uuid = patient_info["entry"][0]["resource"]["id"]

#     eligibility = await imis_services.check_eligibility(patient_uuid)

#     return {
#         "local_validation": local,
#         "imis_patient": patient_info,
#         "eligibility": eligibility
#     }
# app/router/claim.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from model import ClaimInput, ClaimResponse, FullClaimValidationResponse  # <-- You'll need this
from services.local_validator import prevalidate_claim
from services import imis_services
from dependencies import get_api_key
from insurance_database import Claim, Patient, get_db


router = APIRouter(prefix="/api", tags=["Claims"])


# def _extract_patient_name(patient_info: dict) -> str:
#     """Extract human name from FHIR patient resource."""
#     try:
#         name = patient_info["entry"][0]["resource"]["name"][0]
#         given = " ".join(name.get("given", []))
#         family = name.get("family", "")
#         return f"{given} {family}".strip() or "Unknown"
#     except (IndexError, KeyError, TypeError):
#         return "Unknown"


@router.post("/prevalidate_claim", response_model=ClaimResponse)
async def prevalidate_claim_endpoint(
    input_data: ClaimInput,
    db: Session = Depends(get_db),
    # api_key: str = Depends(get_api_key),  # Uncomment when auth is ready
):
    """
    Local pre-validation + persist draft patient & claim.
    """
    result = prevalidate_claim(input_data)

    # Patient: get or create
    patient = db.query(Patient).filter_by(patient_code=input_data.patient_id).first()
    if not patient:
        patient = Patient(patient_code=input_data.patient_id)#, name="Unknown")
        db.add(patient)
        try:
            db.commit()
            db.refresh(patient)
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to save patient") from e

    # Claim: create draft
    claim = Claim(
        claim_code=input_data.claim_code,
        patient_id=patient.id,
        amount_claimed=sum(item.cost for item in input_data.claimable_items),
        claim_date=input_data.visit_date,
        status="pending",
    )
    db.add(claim)
    try:
        db.commit()
        db.refresh(claim)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save claim") from e

    return {
        "is_locally_valid": result["is_locally_valid"],
        "warnings": result["warnings"],
        "items": result["items"],
        "total_approved_local": result["total_approved_local"],
    }


@router.post("/validate_claim", response_model=FullClaimValidationResponse)
async def validate_claim_endpoint(
    input_data: ClaimInput,
    db: Session = Depends(get_db),
    # api_key: str = Depends(get_api_key),
):
    """
    Full validation: local + IMIS lookup + eligibility + DB persistence.
    """
    local = prevalidate_claim(input_data)

    # --- IMIS: patient lookup ---
    patient_info = await imis_services.get_patient_info(input_data.patient_id)
    if not patient_info or "entry" not in patient_info or not patient_info["entry"]:
        raise HTTPException(status_code=404, detail="Patient not found in IMIS")

    patient_uuid = patient_info["entry"][0]["resource"]["id"]
    eligibility = await imis_services.check_eligibility(patient_uuid)

    # --- Extract real name ---
   # patient_name = _extract_patient_name(patient_info)

    # --- Patient: upsert in local DB ---
    patient = db.query(Patient).filter_by(patient_code=input_data.patient_id).first()
    if not patient:
        patient = Patient(
            patient_code=input_data.patient_id,
            # name=patient_name,
            imis_info=patient_info,
            eligibility=eligibility,
        )
        db.add(patient)
    else:
        #patient.name = patient_name
        patient.imis_info = patient_info
        patient.eligibility = eligibility

    try:
        db.commit()
        db.refresh(patient)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update patient") from e

    # --- Claim: create ---
    claim = Claim(
        claim_code=input_data.claim_code,
        patient_id=patient.id,
        amount_claimed=sum(item.cost for item in input_data.claimable_items),
        claim_date=input_data.visit_date,
        status="pending",
    )
    db.add(claim)
    try:
        db.commit()
        db.refresh(claim)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save claim") from e

    return {
        "local_validation": local,
        "imis_patient": patient_info,
        "eligibility": eligibility,
    }


# ————————————————————————
# Testing Endpoints
# ————————————————————————
@router.get("/patients")
def get_patients(db: Session = Depends(get_db)):
    return db.query(Patient).all()


@router.get("/claims")
def get_claims(db: Session = Depends(get_db)):
    return db.query(Claim).all()