from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from services.imis_services import get_patient_info, extract_copayment
from model import ClaimInput, FullClaimValidationResponse 
from services.local_validator import prevalidate_claim
from services import imis_services
from insurance_database import get_db, ImisResponse, PatientInformation,Claim
from services.imis_parser import parse_eligibility_response
from bs4 import BeautifulSoup
from decimal import Decimal 
from services.local_validator import _generate_or_reuse_claim_code
from datetime import datetime
import logging,uuid,json



router = APIRouter(tags=["Claims"])
IMIS_LOGIN_URL = "http://imislegacy.hib.gov.np"
BASE_URL = "https://ourdomaintostorethefiles.com/uploads/claims/"



@router.post("/patient/full-info")
async def get_patient_and_eligibility(
    identifier: str,
    username: str,
    password: str,
    db: Session = Depends(get_db)
):

    patient_info = await imis_services.get_patient_info(identifier, username, password)
    data = patient_info.get("data") or {}
    entries = data.get("entry") or []

    if not (patient_info.get("success") and len(entries) > 0):
        raise HTTPException(status_code=404, detail="Patient not found in IMIS")

    resource = entries[0]["resource"]
    patient_uuid = resource.get("id")

    eligibility_raw = await imis_services.check_eligibility(identifier, username, password)
    if not eligibility_raw.get("success"):
        raise HTTPException(status_code=eligibility_raw.get("status", 500),
                            detail="Eligibility request failed in IMIS")

    copayment = extract_copayment(patient_info.get("data"))
    parsed = parse_eligibility_response(eligibility_raw) or {}
    allowed_money = Decimal(str(parsed.get("allowed_money") or "0"))
    used_money = Decimal(str(parsed.get("used_money") or "0"))

    birth_date_str = resource.get("birthDate")  # e.g., '2016-04-07'
    birth_date_obj = None

    if birth_date_str:
        birth_date_obj = datetime.strptime(birth_date_str, "%Y-%m-%d").date()

    record = db.query(PatientInformation).filter_by(patient_code=identifier).first()
    if not record:
        record = PatientInformation(
            patient_code=identifier,
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

@router.post("/Prevalidation", response_model=FullClaimValidationResponse)
async def eligibility_check_endpoint(
    input_data: ClaimInput, username: str,password:str,
    db: Session = Depends(get_db), 
    #api_key: str = Depends(get_api_key),
):
    #here this it to maintain the session if required or else we use basic auth
    # session_obj = db.query(IMISSession).filter(IMISSession.username == username).first()
    # if not session_obj:
    #     raise HTTPException(status_code=401, detail="Invalid username or no active IMIS session found")
    # session = get_imis_session(db, username)

    # patient_info = await imis_services.get_patient_info(input_data.patient_id, username,password)
    # data = patient_info.get("data") or {}
    # entries = data.get("entry") or []

    # if not (patient_info.get("success") and len(entries) > 0):
    #     raise HTTPException(status_code=404, detail="Patient not found in IMIS")

    # resource = entries[0]["resource"]
    # patient_uuid = resource.get("id")
    # eligibility_raw = await imis_services.check_eligibility(input_data.patient_id, username,password)

    # if not eligibility_raw.get("success"):
    #     raise HTTPException(
    #         status_code=eligibility_raw.get("status", 500),
    #         detail="Eligibility request failed in IMIS"
    #     )

    # parsed = parse_eligibility_response(eligibility_raw) or {}
    # allowed_money = Decimal(str(parsed.get("allowed_money") or "0"))
    # used_money = Decimal(str(parsed.get("used_money") or "0"))
    # item_code=parsed.get("item_code")


    # patient = (
    #     db.query(Patient).filter(Patient.patient_code == input_data.patient_id).first()
    # )

    # if not patient:
    #     patient = Patient(
    #         patient_code=input_data.patient_id,
    #         patient_uuid=patient_uuid,
    #         imis_info=patient_info,
    #         eligibility=eligibility_raw,
    #     )
    #     db.add(patient)
    # else:
    #     patient.patient_uuid = patient_uuid
    #     patient.imis_full_response = patient_info["data"]


    # try:
    #     db.commit()
    #     db.refresh(patient)
    # except Exception:
    #     db.rollback()
    #     raise HTTPException(status_code=500, detail="Failed to update patient")

    # cache_entry = EligibilityCache(

    #     patient_uuid=patient_uuid,
    #     category=parsed.get("category"),
    #     allowed_money=allowed_money,
    #     used_money=used_money,
    #     policy_id=parsed.get("policy_id"),
    #     policy_expiry=parsed.get("policy_expiry"),
    #     raw_response=eligibility_raw,
    # )

    # db.add(cache_entry)
    # try:
    #     db.commit()
    #     db.refresh(cache_entry)
    # except Exception as e:
    #     db.rollback()
    #     print("ELIG CACHE ERROR:", e)  
    #     raise HTTPException(status_code=500, detail=str(e))

    patient = (db.query(PatientInformation).filter(PatientInformation.patient_code == input_data.patient_id).first())
    allowed_money=patient.allowed_money
    used_money=patient.used_money    
    claim_code = _generate_or_reuse_claim_code(
        patient=patient,
        claim_date=input_data.visit_date,
        service_type=input_data.service_type,
        service_code=input_data.service_code,
        db=db)
    local = prevalidate_claim(input_data, db, allowed_money=allowed_money, used_money=used_money, claim_code=claim_code)



    items = [
    {"item_code": item.item_code, "qty": item.quantity}
    for item in input_data.claimable_items
    ]
    claim_id = str(uuid.uuid4())
    claim = Claim(
        claim_id=claim_id,
        claim_code=claim_code,
        service_code=input_data.service_code,
        service_type=input_data.service_type,
        icd_codes=json.dumps(input_data.icd_codes or []),
        patient=patient,
        item_code=items,
        amount_claimed=sum(item.cost for item in input_data.claimable_items),
        claim_date=input_data.visit_date,
        status="pending",
        prevalidation_result=local,
        enterer_reference=input_data.enterer_reference,
        facility_reference=input_data.facility_reference,
        doctor_nmc=input_data.doctor_nmc,
    )

    db.add(claim)
    try:
        db.commit()
        db.refresh(claim)
    except Exception as e:
        db.rollback()
        print("CLAIM SAVE ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))


    return {
        "local_validation": local,
        "claim_code":claim_code,
        "claim_id":claim_id,
        "imis_patient": patient.imis_full_response,
        "eligibility":patient.eligibility_raw
    }



@router.post("/submit_claim/{claim_id}")
async def submit_claim_endpoint(
    input:ClaimInput,
    claim_id: str,
    username: str,
    password:str,
    db: Session = Depends(get_db),
):#    session: requests.Session = Depends(get_imis_session), #here we have discarded the use of session 
    
    # session_obj = db.query(IMISSession).filter(IMISSession.username == username).first()
    # if not session_obj:
    #     raise HTTPException(status_code=401, detail="Invalid username or no active IMIS session found")
    # session = get_imis_session(db, username)


    # claim = (
    #     db.query(Claim)
    #     .filter(Claim.claim_id == claim_id)
    #     .first()
    # )
    # if not claim:
    #     raise HTTPException(status_code=404, detail="Claim not found")
    # if not claim.patient:
    #     raise HTTPException(status_code=404, detail="Patient not found for this claim")
    # if claim.status != "pending":
    #     raise HTTPException(
    #         status_code=400,
    #         detail=f"Only 'pending' claims can be submitted. Current status: {claim.status}"
    #     )

    patient = db.query(PatientInformation).filter(PatientInformation.patient_code == input.patient_id).first()
    if not patient:
        raise HTTPException(status_code=500, detail="Claim has no linked patient")

    patient_uuid = patient.patient_uuid

    # prevalidated_items = claim.prevalidation_result.get("items") if claim.prevalidation_result else None
    # if not prevalidated_items:
    #     raise HTTPException(status_code=400, detail="Claim not prevalidated or has no items")

#eligibility ko kura haru chha yesma which is changed for now see this and change if necessary 

    # cache_entry = (
    #     db.query(EligibilityCache)
    #     .filter(EligibilityCache.patient_uuid == patient_uuid)
    #     .order_by(EligibilityCache.checked_at.desc())
    #     .first()
    # )
    # if not cache_entry:
    #     raise HTTPException(status_code=400, detail="No eligibility cache found for patient")
    # insurance_entries = cache_entry.raw_response.get("data", {}).get("insurance")
    # if not insurance_entries or not insurance_entries[0].get("contract"):
    #     raise HTTPException(status_code=400, detail="No contract/coverage found in eligibility cache")
    # coverage_reference = insurance_entries[0]["contract"]["reference"]

    
    imis_claim_code = uuid.uuid4().hex


    care_type_map = {"OPD": "O", "IPD": "I", "ER": "O","Ref":"O"}
    service_type_mapped = {"OPD": "O", "ER": "E", "IPD": "O", "Ref": "R"}
    if input.service_type in ["OPD", "ER"]:
        type_field = [{"text": service_type_mapped.get(input.service_type, "O")}]
    else:  # for IPD, Referral, etc.
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
        #"id":imis_claim_code, # works fine without id as well, will uncomment when required

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
                "category": {"text": "service"},
                "quantity": {"value":1 },
                "sequence": 1,
                "service": {"text": "OPD01"},#item.get("item_code", "UNKNOWN")#here the service_code is a bit confusing as to enter the item_code or to enter the OPD01 and all opd and ER accordingly.
                "unitPrice": {"value": 10},#round(float(item["approved_amount"]), 2)
            }
            for i, item in enumerate(input)
        ],
        "total": {"value": 10},#claim.amount_claimed}
        "careType":care_type_map.get(input.service_type),#care type shall be I and O 
  
        "enterer": {"reference": "Practitioner/7aa79c53-057e-4e77-8576-dfcfb03584a8"},
        "facility": {"reference": "Location/1ac457d3-efd3-4a67-89b3-bf8cbe18045d"},
        #here for testing this is commented out above is the hardcoded value for now
        #"enterer": {"reference": f"Practitioner/{claim.enterer_reference}"},
        #"facility": {"reference": f"Location/{claim.facility_reference}"},
        "diagnosis": [
            {"sequence": i + 1, 
             "type": [{"coding": [{"code": "icd_0"}], "text": "icd_0"}],
             "diagnosisCodeableConcept": {"coding": [{"code": code}]}}
            for i, code in enumerate(icd_codes or [])
        ],
        "nmc": ",".join(input.doctor_nmc) if isinstance(input.doctor_nmc, list) else input.doctor_nmc,
        "type": {"text":"O"},#service_type_mapped.get(claim.service_type, # visit type shall be O R and E only Others Referral and Emergency   
    }


    try:
        imis_response = await imis_services.submit_claim(fhir_claim_payload, username,password)
    except Exception as exc:
        logging.error(f"IMIS submission failed for claim {claim_id}: {exc}")
        raise HTTPException(status_code=500, detail=f"IMIS submission failed: {str(exc)}") from exc


    # claim.status = "submitted"


    imis_record = ImisResponse(
        patient_id=input.patient_id,
        raw_response=json.loads(json.dumps(imis_response, default=str)),
        fetched_at=datetime.utcnow()
    )
    db.add(imis_record)

    try:
        db.commit()
        db.refresh(imis_record)
    except Exception as exc:
        db.rollback()
        logging.error(f"Failed to commit IMIS record: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to save submission record: {exc}")

    return {
        "message": "Claim successfully submitted to IMIS",
        "claim_code": input.claim_code,
        "submitted_at": datetime.utcnow().isoformat(),
        "imis_response": imis_response
    }


# Get all claims
@router.get("/claims/all")
def get_all_claims(db: Session = Depends(get_db)):
    claims = db.query(Claim).order_by(Claim.claim_code.desc()).all()
    return {
        "count": len(claims),
        "results": claims
    }

# Get claims by patient UUID
@router.get("/claims/patient/{patient_uuid}")
def get_claims_by_patient(patient_uuid: str, db: Session = Depends(get_db)):
    patient = db.query(PatientInformation).filter(PatientInformation.patient_uuid == patient_uuid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    claims = db.query(Claim).filter(Claim.patient_id == patient.id).order_by(Claim.claim_code.desc()).all()
    
    return {
        "count": len(claims),
        "results": claims
    }

