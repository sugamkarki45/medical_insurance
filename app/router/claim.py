from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import json
from model import ClaimInput, ClaimResponse, FullClaimValidationResponse  # <-- You'll need this
from services.local_validator import prevalidate_claim
from services import imis_services
from dependencies import get_api_key
from insurance_database import Claim, Patient, get_db


router = APIRouter(tags=["Claims"])
@router.post("/prevalidate_claim", response_model=ClaimResponse)
async def prevalidate_claim_endpoint(
    input_data: ClaimInput,
    db: Session = Depends(get_db),
    # api_key: str = Depends(get_api_key),  # Uncomment when auth is ready
):
    """
    1. Run local validation
    2. Persist a *draft* patient (if new)
    3. Persist a *draft* claim with:
         • input_snapshot  – exact JSON the user sent
         • prevalidation_result
         • status = "draft"
    4. Return the validation result + draft claim ID
    """
    # --------------------------------------------------------------
    # 1. LOCAL VALIDATION (no DB touch yet)
    # --------------------------------------------------------------
    local_result = prevalidate_claim(input_data, db)

    # --------------------------------------------------------------
    # 2. PATIENT – get or create (commit so we have patient.id)
    # --------------------------------------------------------------
    patient = db.query(Patient).filter(Patient.patient_code == input_data.patient_id).first()
    if not patient:
        patient = Patient(
            patient_code=input_data.patient_id,
            last_visit_date=input_data.visit_date,   # optional early fill
        )
        db.add(patient)
        try:
            db.commit()
            db.refresh(patient)
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save patient: {exc}"
            ) from exc

    # --------------------------------------------------------------
    # 3. CLAIM – duplicate-check + create draft
    # --------------------------------------------------------------
    existing = db.query(Claim).filter(Claim.claim_code == input_data.claim_code).first()
    if existing:
        # Allow re-prevalidate – just update the draft
        claim = existing
        claim.status = "draft"
    else:
        claim = Claim(
            claim_code=input_data.claim_code,
            patient=patient,                              # <-- relationship, patient_id is set automatically          # <-- EXACT USER INPUT
            amount_claimed=sum(item.cost for item in input_data.claimable_items),
            claim_date=input_data.visit_date,
            status="draft",
            prevalidation_result=local_result,
        )
        db.add(claim)

    try:
        db.commit()
        db.refresh(claim)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save claim: {exc}"
        ) from exc

    # --------------------------------------------------------------
    # 4. RETURN
    # --------------------------------------------------------------
    return {
        "is_locally_valid": local_result["is_locally_valid"],
        "warnings": local_result["warnings"],
        "items": local_result["items"],
        "total_approved_local": local_result["total_approved_local"],
        "draft_claim_id": claim.id,          # optional – handy for UI
    }
@router.post("/validate_claim", response_model=FullClaimValidationResponse)
async def validate_claim_endpoint(
    input_data: ClaimInput,
    db: Session = Depends(get_db),
    # api_key: str = Depends(get_api_key),
):

    local = prevalidate_claim(input_data,db)

    # --- IMIS: patient lookup ---
    patient_info = await imis_services.get_patient_info(input_data.patient_id)
    if not patient_info["success"] or not patient_info["data"] \
    or "entry" not in patient_info["data"] \
    or not patient_info["data"]["entry"]:
        raise HTTPException(status_code=404, detail="Patient not found in IMIS")

    patient_uuid = patient_info["data"]["entry"][0]["resource"]["id"]
    eligibility = await imis_services.check_eligibility(patient_uuid)


    # --- Patient: upsert in local DB ---
    patient = db.query(Patient).filter_by(patient_code=input_data.patient_id).first()
    if not patient:
        patient = Patient(
            patient_code=input_data.patient_id,
            imis_info=patient_info,
            eligibility=eligibility,
        )
        db.add(patient)
    else:
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