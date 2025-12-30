from fastapi import APIRouter, Depends, HTTPException,Request
from sqlalchemy.orm import Session
from services.imis_services import extract_copayment
from model import ClaimInput, FullClaimValidationResponse ,PatientFullInfoRequest
from services.local_validator import prevalidate_claim
from services import imis_services
from insurance_database import get_db, ImisResponse, PatientInformation
from services.imis_parser import parse_eligibility_response
from decimal import Decimal 
from datetime import datetime
import logging,uuid,json
from rule_loader import get_all_items,get_all_services
from dependencies import get_api_key
from typing import  Optional
from fastapi import Query



router = APIRouter(tags=["Claims"])
IMIS_LOGIN_URL = "https://imis.hib.gov.np"
BASE_URL = "https://ourdomaintostorethefiles.com/uploads/claims/"




# @router.post("/imis-login-check")
# async def check_imis_login(
#     username: str,
#     password: str,
#     api_key: str = Depends(get_api_key)
# ):
#     url = f"{IMIS_BASE_URL}/"  
#     headers = get_auth_header(username, password)

#     try:
#         async with httpx.AsyncClient(timeout=15.0) as client:
#             response = await client.get(url, headers=headers)

#         if response.status_code == 200:
#             return {"status": "success", "message": "IMIS login successful"}

#         if response.status_code in (401, 403,500,404):
#             raise HTTPException(status_code=401, detail="Invalid IMIS credentials")

#         raise HTTPException(
#             status_code=502,
#             detail=f"IMIS returned {response.status_code}"
#         )

#     except httpx.RequestError as e:
#         raise HTTPException(status_code=502, detail=str(e))

    
@router.post("/patient/full-info")
async def get_patient_and_eligibility(
    identifier: PatientFullInfoRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    patient_identifier = identifier.patient_identifier
    username=identifier.username
    password=identifier.password
    patient_info = await imis_services.get_patient_info(patient_identifier, username, password)
    data = patient_info.get("data") or {}
    entries = data.get("entry") or []

    if not (patient_info.get("success") and len(entries) > 0):
        raise HTTPException(status_code=404, detail="Patient not found in IMIS")

    resource = entries[0]["resource"]
    patient_uuid = resource.get("id")

    eligibility_raw = await imis_services.check_eligibility(patient_identifier, username, password)
    if not eligibility_raw.get("success"):
        raise HTTPException(status_code=eligibility_raw.get("status", 500),
                            detail="Eligibility request failed in IMIS")

    copayment = extract_copayment(patient_info.get("data"))
    parsed = parse_eligibility_response(eligibility_raw) or {}
    allowed_money = Decimal(str(parsed.get("allowed_money") or "0"))
    used_money = Decimal(str(parsed.get("used_money") or "0"))

    birth_date_str = resource.get("birthDate") 
    birth_date_obj = None

    if birth_date_str:
        birth_date_obj = datetime.strptime(birth_date_str, "%Y-%m-%d").date()

    record = db.query(PatientInformation).filter_by(patient_code=patient_identifier).first()
    if not record:
        record = PatientInformation(
            patient_code=patient_identifier,
            patient_uuid=patient_uuid,
            name=" ".join(resource.get("name", [{}])[0].get("given", [])),
            birth_date=birth_date_obj,
            gender=resource.get("gender"),
            copayment=copayment,
            allowed_money=allowed_money,
            used_money=used_money,
            category=parsed.get("category"),
            policy_id=parsed.get("policy_id"),
            policy_expiry=parsed.get("policy_expiry"),
            imis_full_response=patient_info.get("data"),
            eligibility_raw=eligibility_raw
        )
        db.add(record)
    else:
        record.patient_uuid = patient_uuid
        record.name = " ".join(resource.get("name", [{}])[0].get("given", []))
        record.birth_date = birth_date_obj
        record.gender = resource.get("gender")
        record.copayment = copayment
        record.allowed_money = allowed_money
        record.used_money = used_money
        record.category = parsed.get("category")
        record.policy_id = parsed.get("policy_id")
        record.policy_expiry = parsed.get("policy_expiry")
        record.imis_full_response = patient_info.get("data")
        record.eligibility_raw = eligibility_raw

    try:
        db.commit()
        db.refresh(record)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save patient eligibility: {str(e)}")

    return {
        "patient_code": record.patient_code,
        "uuid": record.patient_uuid,
        "name": record.name,
        "birthDate": record.birth_date,
        "gender": record.gender,
        "copayment": str(record.copayment),
        "allowed_money": str(record.allowed_money),
        "used_money": str(record.used_money),
        "category": record.category,
        "policy_id": record.policy_id,
        "policy_expiry": record.policy_expiry,
        "imis": record.imis_full_response,
        "eligibility": record.eligibility_raw
    }


@router.post("/prevalidation", response_model=FullClaimValidationResponse)
async def eligibility_check_endpoint(
    identifier: PatientFullInfoRequest,
    input_data: ClaimInput, 
    db: Session = Depends(get_db), 
    api_key: str = Depends(get_api_key)
):
    
    patient = (db.query(PatientInformation).filter(PatientInformation.patient_code == input_data.patient_id).first())
    if not patient:
     raise HTTPException(status_code=404, detail="Patient not found")

    allowed_money=patient.allowed_money
    used_money=patient.used_money
    local = prevalidate_claim(input_data, db, allowed_money=allowed_money, used_money=used_money)
    return {
        "local_validation": local,
        "imis_patient": patient.imis_full_response,
        "eligibility":patient.eligibility_raw
    }


@router.post("/submit_claim/{claim_id}")
async def submit_claim_endpoint(
    identifier: PatientFullInfoRequest,
    input:ClaimInput,
    claim_id: str,
    request:Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    username=identifier.username
    password=identifier.password
    patient = db.query(PatientInformation).filter(PatientInformation.patient_code == input.patient_id).first()
    if not patient:
        raise HTTPException(status_code=500, detail="Claim has no linked patient")

    patient_uuid = patient.patient_uuid
    
    imis_claim_code = uuid.uuid4().hex

    care_type_map = {"OPD": "O", "IPD": "I", "ER": "O","Referral":"O"}
    service_type_mapped = {"OPD": "O", "ER": "E", "IPD": "O", "Referral": "R"}
    if input.service_type in ["OPD", "ER"]:
        type_field = [{"text": service_type_mapped.get(input.service_type, "O")}]
    else:
        type_field = {"text": service_type_mapped.get(input.service_type, "O")}

    icd_codes = json.loads(input.icd_codes) if isinstance(input.icd_codes, str) else input.icd_codes
    fhir_claim_payload = {
        "resourceType": "Claim",
        "billablePeriod": {
            "start": input.visit_date.isoformat(),
            "end": input.visit_date.isoformat()
        },
        "created": datetime.utcnow().isoformat(),
        "patient": {"reference": f"Patient/{patient_uuid}"},

        "identifier": [
            {
                "type": {"coding": [{"code": "ACSN", "system": "https://hl7.org/fhir/valueset-identifier-type.html"}]},
                "use": "usual",
                "value": imis_claim_code
            },
            {
                "type": {"coding": [{"code": "MR", "system": "https://hl7.org/fhir/valueset-identifier-type.html"}]},
                "use": "usual",
                "value": input.claim_code
            }
        ],
        "item": [
            {
                "sequence": i + 1,
                "category": {"text": item.category},         
                "quantity": {"value": item.quantity},         
                "service": {"text": item.item_code},         
                "unitPrice": {"value": item.cost},  
            }
            for i, item in enumerate(input.claimable_items)
        ],
        "total":{"value": sum(round(item.cost * item.quantity, 2) 
        for item in input.claimable_items
        )},
        "careType":care_type_map.get(input.service_type),#care type shall be I and O 
        # "enterer": {"reference": "Practitioner/7aa79c53-057e-4e77-8576-dfcfb03584a8"},
        # "facility": {"reference": "Location/1ac457d3-efd3-4a67-89b3-bf8cbe18045d"},
        #here for testing this is commented out above is the hardcoded value for now
        "enterer": {"reference": f"Practitioner/{input.enterer_reference}"},
        "facility": {"reference": f"Location/{input.facility_reference}"},
        "diagnosis": [
            {"sequence": i + 1, 
             "type": [{"coding": [{"code": "icd_0"}], "text": "icd_0"}],
             "diagnosisCodeableConcept": {"coding": [{"code": code}]}}
            for i, code in enumerate(icd_codes or [])
        ],
        "nmc": ",".join(input.doctor_nmc) if isinstance(input.doctor_nmc, list) else input.doctor_nmc,
        "type": {"text":service_type_mapped.get(input.service_type,"E")},#service_type_mapped.get(claim.service_type, # visit type shall be O R and E only Others Referral and Emergency   
    }


    try:
        imis_response = await imis_services.submit_claim(fhir_claim_payload, username,password)
    except Exception as exc:
        logging.error(f"IMIS submission failed for claim {claim_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"IMIS submission failed: {str(exc)}") from exc

    imis_json_str = imis_response.get("response")
    imis_json = json.loads(imis_json_str) if imis_json_str else {}

    claim_code = "UNKNOWN_CLAIM_CODE"
    for ident in imis_json.get("identifier", []):
        codings = ident.get("type", {}).get("coding", [])
        if any(c.get("code") == "MR" for c in codings):
            claim_code = ident.get("value")
            break

    outcome_status = imis_json.get("outcome", {}).get("text", "unknown")
    created_date_str = imis_json.get("created")
    created_date = datetime.fromisoformat(created_date_str) if created_date_str else datetime.utcnow()

    seq_to_code = {}
    for add_item in imis_json.get("addItem", []):
        seq_list = add_item.get("sequenceLinkId", [])
        service_list = add_item.get("service", {}).get("coding", [])
        code = service_list[0].get("code") if service_list else None
        for seq in seq_list:
            seq_to_code[seq] = code

    items_info = []
    for item in imis_json.get("item", []):
        seq_id = item.get("sequenceLinkId")
        service_code = seq_to_code.get(seq_id, None)
        for adj in item.get("adjudication", []):
            status = adj.get("reason", {}).get("text")
            items_info.append({
                "sequence_id": seq_id,
                "item_code": service_code,
                "status": status
            })
    items_list = [
    {
        "item_code": item.item_code,
        "name": item.name,
        "qty": item.quantity,
        "cost": item.cost,
        "category": item.category,
        "type": item.type
    }
    for item in input.claimable_items
]
    items_list = [
    {
        "item_code": item.item_code,
        "name": item.name,
        "qty": item.quantity,
        "cost": item.cost,
        "category": item.category,
        "type": item.type
    }
    for item in input.claimable_items
]
    imis_record = ImisResponse(
        patient_id=input.patient_id,
        claim_code=claim_code,
        status=outcome_status,
        created_at=created_date,
        items=items_info,
        raw_response=imis_json,
        fetched_at=datetime.utcnow(),
        service_type=input.service_type,
        service_code=input.service_code,
        item_code=items_list,
        department=input.department,
    )
    db.add(imis_record)
    db.commit()
    db.refresh(imis_record)
    def detect_system(request: Request):
        user_agent = request.headers.get("User-Agent", "").lower()
        ip = request.client.host


        if "x-system-source" in request.headers:
            return request.headers["x-system-source"]

        if "hmis" in user_agent:
            return "HMIS"
        if "ehr" in user_agent:
            return "EHR"

        if ip.startswith("10."):
            return "HMIS-network"
        if ip.startswith("192.168."):
            return "EHR-network"

        return "Unknown"

    system_info = {
    "source": detect_system(request),
    "ip": request.client.host,
    "user_agent": request.headers.get("User-Agent"),
    "timestamp": datetime.utcnow().isoformat()
}
    return {
        "message": "Claim successfully submitted to IMIS",
        "claim_code": claim_code,
        "status": outcome_status,
        "submitted_at": datetime.utcnow().isoformat(),
        "created_at": created_date.isoformat(),
        "items": items_info,
        "IMIS_response":imis_json,
        "payload":fhir_claim_payload,
        "system_info":system_info
    }


@router.get("/claims/all")
def get_all_claims(db: Session = Depends(get_db),    api_key: str = Depends(get_api_key)):
    claims = db.query(ImisResponse).order_by(ImisResponse.claim_code.desc()).all()
    return {
        "count": len(claims),
        "results": claims
    }


@router.get("/claims/patient/{patient_uuid}")
def get_claims_by_patient(patient_uuid: str, db: Session = Depends(get_db),    api_key: str = Depends(get_api_key)):
    patient = db.query(PatientInformation).filter(PatientInformation.patient_uuid == patient_uuid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    claims = db.query(ImisResponse).filter(ImisResponse.patient_id == patient.patient_code).order_by(ImisResponse.claim_code.desc()).all()
    
    return {
        "count": len(claims),
        "results": claims
    }

@router.get("/items")
def list_items(
    api_key: str = Depends(get_api_key),
    q: Optional[str] = Query(None, min_length=2, description="Search term for medicine names"),
    limit: Optional[int] = Query(15, ge=1, le=100),
) -> dict:
    # Always work with raw data
    all_items = get_all_items()  # This uses your cached _cached_meds_list

    if not q:
        # Return full list as dict (FastAPI will convert to JSON)
        return {"count": len(all_items), "medicines": all_items}

    # Search mode
    query = q.strip().lower()
    filtered = [
        item for item in all_items
        if query in item.get("name", "").lower()
    ][:limit]

    return {"count": len(filtered), "medicines": filtered}


@router.get("/services")
def list_services(
    api_key: str = Depends(get_api_key),
    q: Optional[str] = Query(None, min_length=2, description="Search term for service names"),
    limit: Optional[int] = Query(15, ge=1, le=100),
) -> dict:
    all_services = get_all_services()

    if not q:
        return {"count": len(all_services), "packages": all_services}

    query = q.strip().lower()
    filtered = [
        service for service in all_services
        if query in service.get("name", "").lower()
    ][:limit]

    return {"count": len(filtered), "packages": filtered}
# @router.get("/items")
# def list_items(    api_key: str = Depends(get_api_key)):
#     return get_items_response()


# @router.get("/services")
# def list_services(    api_key: str = Depends(get_api_key)):
#     return get_services_response()