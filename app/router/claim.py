# app/router/claim.py
from fastapi import APIRouter, Depends, HTTPException
from model import ClaimInput,ClaimResponse
from services.local_validator import prevalidate_claim
from services import imis_services
from dependencies import get_api_key


router = APIRouter(prefix="/api", tags=["Claims"])

@router.post("/prevalidate_claim", response_model=ClaimResponse, dependencies=[Depends(get_api_key)])
async def prevalidate_claim_endpoint(input_data: ClaimInput):
    result = prevalidate_claim(input_data)
    return {
        "is_locally_valid": result["is_locally_valid"],
        "warnings": result["warnings"],
        "items": result["items"],
        "total_approved_local": result["total_approved_local"]
    }

@router.post("/validate_claim", response_model=ClaimResponse, dependencies=[Depends(get_api_key)])
async def validate_claim_endpoint(input_data: ClaimInput):
    local = prevalidate_claim(input_data)

    patient_info = await imis_services.get_patient_info(input_data.patient_id)

    if not patient_info or "entry" not in patient_info or not patient_info["entry"]:
        raise HTTPException(status_code=404, detail="Patient not found in IMIS")


    patient_uuid = patient_info["entry"][0]["resource"]["id"]

    eligibility = await imis_services.check_eligibility(patient_uuid)

    return {
        "local_validation": local,
        "imis_patient": patient_info,
        "eligibility": eligibility
    }


# @router.post("/validate_claim", response_model=ClaimResponse, dependencies=[Depends(get_api_key)])
# async def validate_claim_endpoint(input_data: ClaimInput):
#     local = prevalidate_claim(input_data)
#     # Get patient info and eligibility
#     patient_info = await imis_services.get_patient_info(input_data.patient_id)
#     eligibility = await imis_services.check_eligibility(input_data.patient_id)

#     if not patient_info:
#         raise HTTPException(status_code=404, detail="Patient not found in IMIS")

#     return {
#         "local_validation": local,
#         "imis_patient": patient_info,
#         "eligibility": eligibility
#     }
