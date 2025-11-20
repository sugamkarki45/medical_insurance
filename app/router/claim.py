from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from services.imis_services import get_patient_info, extract_copayment
from model import ClaimInput, FullClaimValidationResponse 
from services.local_validator import prevalidate_claim
from services import imis_services
from insurance_database import Claim, Patient, get_db, EligibilityCache, ImisResponse
from services.imis_parser import parse_eligibility_response
from datetime import datetime

router = APIRouter(tags=["Claims"])

@router.get("/{identifier}")
async def get_patient(identifier: str, db: Session = Depends(get_db)):
    # 1. Try local DB
    patient = db.query(Patient).filter(Patient.patient_code == identifier).first()


    # 3. Fetch from IMIS if not found or no data
    imis_response = await get_patient_info(identifier)

    if not imis_response["success"] or not imis_response["data"].get("entry"):
        raise HTTPException(status_code=404, detail="Patient not found")

    resource = imis_response["data"]["entry"][0]["resource"]

    # 4. Extract copayment
    copayment = extract_copayment(imis_response["data"])

    # 5. Upsert into DB
    if not patient:
        patient = Patient(patient_code=identifier)

    patient.imis_full_response = imis_response["data"]
    patient.imis_core_resource = resource
    patient.Copayment = copayment   #here the name of the field can be made accordingly 

    db.add(patient)
    db.commit()
    db.refresh(patient)

    return format_patient_response(patient)


def format_patient_response(patient: Patient):
    resource = patient.imis_core_resource or {}

    return {
        "patient_code": patient.patient_code,
        "uuid": resource.get("id"),
        "name": " ".join(resource.get("name", [{}])[0].get("given", [])),
        "birthDate": resource.get("birthDate"),
        "gender": resource.get("gender"),
        "copayment": patient.Copayment,
        "imis": patient.imis_full_response   # full IMIS dump
    }


# here we are commenting this endpoint as we are combining prevalidate and eligibility check into one endpoint called Eligibility_check and we can keep this endpoint if we need to perform local validation only without imis check
# @router.post("/prevalidate_claim", response_model=ClaimResponse)
# async def prevalidate_claim_endpoint(
#     input_data: ClaimInput,
#     db: Session = Depends(get_db),
#     # api_key: str = Depends(get_api_key),  # Uncomment when auth is ready
# ):
#     """
#     1. Run local validation
#     2. Persist a *draft* patient (if new)
#     3. Persist a *draft* claim with:
#          • input_snapshot  – exact JSON the user sent
#          • prevalidation_result
#          • status = "draft"
#     4. Return the validation result + draft claim ID
#     """

#     local_result = prevalidate_claim(input_data, db)

# #get or to create a new patient
#     patient = db.query(Patient).filter(Patient.patient_code == input_data.patient_id).first()
#     if not patient:
#         patient = Patient(
#             patient_code=input_data.patient_id,
#             last_visit_date=input_data.visit_date,   
#         )
#         db.add(patient)
#         try:
#             db.commit()
#             db.refresh(patient)
#         except Exception as exc:
#             db.rollback()
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Failed to save patient: {exc}"
#             ) from exc


#     existing = db.query(Claim).filter(Claim.claim_code == input_data.claim_code).first()
#     if existing:
#         # Allow re-prevalidate – just update the draft
#         claim = existing
#         claim.status = "draft"
#     else:
#         claim = Claim(
#             claim_code=input_data.claim_code,
#             patient=patient,                           
#             amount_claimed=sum(item.cost for item in input_data.claimable_items),
#             claim_date=input_data.visit_date,
#             status="draft",
#             prevalidation_result=local_result,
#         )
#         db.add(claim)

#     try:
#         db.commit()
#         db.refresh(claim)
#     except Exception as exc:
#         db.rollback()
#         raise HTTPException(
#             status_code=500,
#             detail=f"Failed to save claim: {exc}"
#         ) from exc

#     return{
#         "is_locally_valid": local_result["is_locally_valid"],
#         "warnings": local_result["warnings"],
#         "items": local_result["items"],
#         "total_approved_local": local_result["total_approved_local"],
#     }


@router.post("/Eligibility_check", response_model=FullClaimValidationResponse)
async def eligibility_check_endpoint(
    input_data: ClaimInput,
    db: Session = Depends(get_db),
    #api_key: str = Depends(get_api_key),
):
    # Local prevalidation
    local = prevalidate_claim(input_data, db)

    #Look up patient
    patient_info = await imis_services.get_patient_info(input_data.patient_id)

    if not (patient_info.get("success") and patient_info["data"].get("entry")):
        raise HTTPException(status_code=404, detail="Patient not found in IMIS")

    patient_uuid = patient_info["data"]["entry"][0]["resource"]["id"]

    # 3. Eligibility check
    eligibility_raw = await imis_services.check_eligibility(input_data.patient_id)

    if not eligibility_raw.get("success"):
        raise HTTPException(
            status_code=eligibility_raw.get("status", 500),
            detail="Eligibility request failed in IMIS"
        )


    parsed = parse_eligibility_response(eligibility_raw) or {}


    patient = (
        db.query(Patient).filter(Patient.patient_code == input_data.patient_id).first()
    )

    if not patient:
        patient = Patient(
            patient_code=input_data.patient_id,
            patient_uuid=patient_uuid,
            imis_info=patient_info,
            eligibility=eligibility_raw,
        )
        db.add(patient)
    else:
        patient.patient_uuid = patient_uuid
        patient.imis_info = patient_info
        patient.eligibility = eligibility_raw

    try:
        db.commit()
        db.refresh(patient)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update patient")

    # 6. Create eligibility cache
    cache_entry = EligibilityCache(
        patient_uuid=patient_uuid,
        category=parsed.get("category"),
        allowed_money=parsed.get("allowed_money"),
        used_money=parsed.get("used_money"),
        policy_id=parsed.get("policy_id"),
        policy_expiry=parsed.get("policy_expiry"),
        raw_response=eligibility_raw,
    )

    db.add(cache_entry)
    try:
        db.commit()
        db.refresh(cache_entry)
    except Exception as e:
        db.rollback()
        print("ELIG CACHE ERROR:", e)  
        raise HTTPException(status_code=500, detail=str(e))


    # 7. Save claim
    claim = Claim(
        claim_code=input_data.claim_code,
        service_code=input_data.service_code,
        patient_id=patient.id,
        amount_claimed=sum(item.cost for item in input_data.claimable_items),
        claim_date=input_data.visit_date,
        status="pending",
        prevalidation_result=local,
        enterer_reference=input_data.enterer_reference,
        facility_reference=input_data.facility_reference,
    )

    db.add(claim)
    try:
        db.commit()
        db.refresh(claim)
    except Exception as e:
        db.rollback()
        print("CLAIM SAVE ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))

    # 8. Final output
    return {
        "local_validation": local,
        "imis_patient": patient_info,
        "eligibility": eligibility_raw,
    }



@router.post("/submit_claim/{claim_id}")
async def submit_claim_endpoint(
    claim_id: int,
    input_data: ClaimInput,
    db: Session = Depends(get_db),
):
#to fetch claim
    claim = db.query(Claim).filter(Claim.id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    if claim.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Only 'pending' claims can be submitted. Current status: {claim.status}"
        )

    patient=claim.patient
    patient_response = patient.imis_full_response or {}

    entries = patient_response.get("entry")
    if not entries or not isinstance(entries, list):
        raise HTTPException(
            status_code=400,
            detail="Patient IMIS info incomplete or malformed. Run full validate first."
        )

    patient_resource = entries[0].get("resource")
    if not patient_resource or "id" not in patient_resource:
        raise HTTPException(
            status_code=400,
            detail="Patient resource missing ID. Run full validate first."
        )

    patient_uuid = patient_resource["id"]

    if not claim.prevalidation_result or not claim.prevalidation_result.get("items"):
        raise HTTPException(status_code=400, detail="Claim not prevalidated or no items present")
    care_type_map = {"OPD": "O", "IPD": "I", "Emergency": "E"}


    fhir_claim_payload = {
        "resourceType": "Claim",
        "billablePeriod": {
            "start": claim.claim_date.isoformat(),
            "end": claim.claim_date.isoformat()
        },
        "created": claim.claim_date.isoformat(),
        "patient": {"reference": f"Patient/{patient_uuid}"},
        "identifier": [{"use": "usual", "value": claim.claim_code, "type": {"coding": [{"code": "MR"}]}}],
        "item": [
            {
                "sequence": i + 1,
                "category": {"text": "service"},
                "service": {"text": item["item_code"]},
                "quantity": {"value": item["quantity"]},
                "unitPrice": {"value": item["approved_amount"]},
            }
            for i, item in enumerate(claim.prevalidation_result["items"])
        ],
        "total": {"value": claim.amount_claimed},
        "careType": care_type_map.get(input_data.service_type, "O"),
        "type": {"text":care_type_map.get(input_data.service_type, "O")},  
        "enterer": {"reference": input_data.enterer_reference},  
        "facility": {"reference": input_data.facility_reference},  
         "diagnosis": [
        {
            "sequence": 1,
            "type": [{"text": input_data.service_code}]
        }
    ],
    }

#submit to imis
    try:
        imis_response = await imis_services.submit_claim(fhir_claim_payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"IMIS submission failed: {exc}") from exc
#update claim status
    claim.status = "submitted"
    imis_response_record = ImisResponse(
        patient_id=claim.patient_id,
        raw_response=imis_response,
        fetched_at=datetime.utcnow()
    )
    db.add(imis_response_record)

    try:
        db.commit()
        db.refresh(claim)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update claim: {exc}") from exc

    return {
        "message": "Claim successfully submitted",
        "claim_id": claim.id,
        "imis_response": imis_response
    }


@router.get("/claims/all")
def get_all_claims(db: Session = Depends(get_db)):
    claims = db.query(Claim).order_by(Claim.id.desc()).all()
    return {
        "count": len(claims),
        "results": claims
    }

# Get claims by patient UUID
@router.get("/claims/patient/{patient_uuid}")
def get_claims_by_patient(patient_uuid: str, db: Session = Depends(get_db)):
    # Ensure the patient exists
    patient = db.query(Patient).filter(Patient.patient_uuid == patient_uuid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    claims = db.query(Claim).filter(Claim.patient_id == patient.id).order_by(Claim.id.desc()).all()
    
    return {
        "count": len(claims),
        "results": claims
    }