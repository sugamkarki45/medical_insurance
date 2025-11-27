from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from services.imis_services import get_patient_info, extract_copayment
from model import ClaimInput, FullClaimValidationResponse , LoginInput
from services.local_validator import prevalidate_claim
from services import imis_services
from services.imis_services import get_imis_session
from insurance_database import Claim, Patient, get_db, EligibilityCache, ImisResponse,IMISSession,ClaimDocument
from services.imis_parser import parse_eligibility_response
from bs4 import BeautifulSoup
from decimal import Decimal 
from services.local_validator import _generate_or_reuse_claim_code
from sqlalchemy.orm import joinedload
from datetime import datetime,timedelta
import logging,json,requests,uuid,os


router = APIRouter(tags=["Claims"])



UPLOAD_DIR = "uploads/claim_upload/"
BASE_URL = "https://ourdomaintostorethefiles.com/uploads/claims/"


@router.post("/upload_document/{claim_id}")
async def upload_document(claim_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    claim = db.query(Claim).filter(Claim.claim_id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    claim_folder = os.path.join(UPLOAD_DIR, claim_id)
    os.makedirs(claim_folder, exist_ok=True)

    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(claim_folder, filename)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    # URL accessible via your server
    file_url = f"{BASE_URL}{claim_id}/{filename}"

    doc = ClaimDocument(
        claim_id=claim_id,
        file_url=file_url,
        document_type="general"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "message": "File uploaded and saved",
        "file_url": file_url,
        "document_id": doc.id
    }



IMIS_LOGIN_URL = "http://imislegacy.hib.gov.np"

#here we have to check the login details with imis and store in our db
@router.post("/imis/login")
async def imis_login(input: LoginInput, db: Session = Depends(get_db)):
    session = requests.Session()


    try:
        login_page = session.get(IMIS_LOGIN_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch IMIS login page: {e}")

    soup = BeautifulSoup(login_page.text, "html.parser")
    try:
        viewstate = soup.find("input", {"name": "__VIEWSTATE"})["value"]
        eventvalidation = soup.find("input", {"name": "__EVENTVALIDATION"})["value"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse login form: {e}")


    payload = {
        "__VIEWSTATE": viewstate,
        "__EVENTVALIDATION": eventvalidation,
        "txtUserName": input.username,
        "txtPassword": input.password,
        "btnLogin": "Login"
    }

    try:
        response = session.post(IMIS_LOGIN_URL, data=payload, allow_redirects=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit login form: {e}")

    if "Home.aspx" not in response.url or "ASP.NET_SessionId" not in session.cookies.get_dict():
        raise HTTPException(status_code=401, detail="IMIS login failed")

    cookie = session.cookies.get_dict()

    existing = db.query(IMISSession).filter(IMISSession.username == input.username).first()
    if existing:
        db.delete(existing)
        db.commit()

    new_sess = IMISSession(
        username=input.username,
        session_cookie=str(cookie),
        expires_at=datetime.utcnow() + timedelta(hours=8)
    )

    db.add(new_sess)
    db.commit()
    db.refresh(new_sess)

    return {"message": "IMIS login successful", "session": cookie}


@router.get("/{identifier}")
async def get_patient(identifier: str, username: str, db: Session = Depends(get_db)):
    Session


    session_obj = db.query(IMISSession).filter(IMISSession.username == username).first()
    
    if not session_obj:
        raise HTTPException(status_code=401, detail="Invalid username or no active IMIS session found")
    

    session= get_imis_session(db, username)
    # 1. Try local DB
    patient = db.query(Patient).filter(Patient.patient_code == identifier).first()


    # 3. Fetch from IMIS if not found or no data
    imis_response = await get_patient_info(identifier,session)

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
    patient.copayment = copayment  #here the name of the field can be made accordingly 

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
        "copayment": patient.copayment,
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
    input_data: ClaimInput, username: str,
    db: Session = Depends(get_db), 
    #api_key: str = Depends(get_api_key),
):
    session_obj = db.query(IMISSession).filter(IMISSession.username == username).first()
    
    if not session_obj:
        raise HTTPException(status_code=401, detail="Invalid username or no active IMIS session found")
    

    session = get_imis_session(db, username)

    patient_info = await imis_services.get_patient_info(input_data.patient_id, session)

    data = patient_info.get("data") or {}
    entries = data.get("entry") or []

    if not (patient_info.get("success") and len(entries) > 0):
        raise HTTPException(status_code=404, detail="Patient not found in IMIS")

    patient_uuid = entries[0]["resource"]["id"]

    #Look up patient
    # patient_info = await imis_services.get_patient_info(input_data.patient_id, session)

    # if not (patient_info.get("success") and patient_info["data"].get("entry")):
    #     raise HTTPException(status_code=404, detail="Patient not found in IMIS")

    # patient_uuid = patient_info["data"]["entry"][0]["resource"]["id"]

    # 3. Eligibility check
    eligibility_raw = await imis_services.check_eligibility(input_data.patient_id, session)

    if not eligibility_raw.get("success"):
        raise HTTPException(
            status_code=eligibility_raw.get("status", 500),
            detail="Eligibility request failed in IMIS"
        )


    parsed = parse_eligibility_response(eligibility_raw) or {}

    allowed_money = Decimal(str(parsed.get("allowed_money") or "0"))
    used_money = Decimal(str(parsed.get("used_money") or "0"))
    item_code=parsed.get("item_code")


    patient = (
        db.query(Patient).filter(Patient.patient_code == input_data.patient_id).first()
    )

    claim_code = _generate_or_reuse_claim_code(
        patient=patient,
        claim_date=input_data.visit_date,
        service_type=input_data.service_type,
        service_code=input_data.service_code,
        db=db)

        # Local prevalidation
    local = prevalidate_claim(input_data, db, allowed_money=allowed_money, used_money=used_money, claim_code=claim_code)


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
        patient.imis_full_response = patient_info["data"]


    try:
        db.commit()
        db.refresh(patient)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update patient")





    cache_entry = EligibilityCache(

        patient_uuid=patient_uuid,
        category=parsed.get("category"),
        allowed_money=allowed_money,
        used_money=used_money,
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
    items = [
    {"item_code": item.item_code, "qty": item.quantity}
    for item in input_data.claimable_items
    ]
    claim = Claim(
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

    # 8. Final output
    return {
        "local_validation": local,
        "imis_patient": patient_info,
        "eligibility": eligibility_raw,
    }

@router.post("/submit_claim/{claim_code}")
async def submit_claim_endpoint(
    claim_code: str,
    username: str,
    db: Session = Depends(get_db),
):
    
    session_obj = db.query(IMISSession).filter(IMISSession.username == username).first()
    if not session_obj:
        raise HTTPException(status_code=401, detail="Invalid username or no active IMIS session found")
    session = get_imis_session(db, username)

# yesma claim id rakhni ki claim code rakhni ho vanni kura sochera garnu 
    claim = (
        db.query(Claim)
        .options(joinedload(Claim.patient))
        .filter(Claim.claim_code == claim_code)
        .first()
    )
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    if not claim.patient:
        raise HTTPException(status_code=404, detail="Patient not found for this claim")
    if claim.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Only 'pending' claims can be submitted. Current status: {claim.status}"
        )

    patient = db.query(Patient).filter(Patient.id == claim.patient_id).first()
    if not patient:
        raise HTTPException(status_code=500, detail="Claim has no linked patient")

    patient_uuid = patient.patient_uuid

    prevalidated_items = claim.prevalidation_result.get("items") if claim.prevalidation_result else None
    if not prevalidated_items:
        raise HTTPException(status_code=400, detail="Claim not prevalidated or has no items")

    cache_entry = (
        db.query(EligibilityCache)
        .filter(EligibilityCache.patient_uuid == patient_uuid)
        .order_by(EligibilityCache.checked_at.desc())
        .first()
    )
    if not cache_entry:
        raise HTTPException(status_code=400, detail="No eligibility cache found for patient")
    
    insurance_entries = cache_entry.raw_response.get("data", {}).get("insurance")
    if not insurance_entries or not insurance_entries[0].get("contract"):
        raise HTTPException(status_code=400, detail="No contract/coverage found in eligibility cache")

    coverage_reference = insurance_entries[0]["contract"]["reference"]
    imis_claim_code = uuid.uuid4().hex
    guarantee_id={"reference": "Contract/HIB-3500/2026-11-16 00:00:00"}
    care_type_map = {"OPD": "O", "IPD": "I", "ER": "O","Ref":"O"}
    service_type_mapped = {"OPD": "O", "ER": "E", "IPD": "O", "Ref": "R"}
    if claim.service_type in ["OPD", "ER"]:
        type_field = [{"text": service_type_mapped.get(claim.service_type, "O")}]
    else:  # for IPD, Referral, etc.
        type_field = {"text": service_type_mapped.get(claim.service_type, "O")}

    icd_codes = json.loads(claim.icd_codes) if isinstance(claim.icd_codes, str) else claim.icd_codes

    fhir_claim_payload = {
        "resourceType": "Claim",
        "billablePeriod": {
            "start": claim.claim_date.isoformat(),
            "end": claim.claim_date.isoformat()
        },
        "created": datetime.utcnow().isoformat(),
        "patient": {"reference": f"Patient/{patient_uuid}"},
        "information": [
    {
        "category": { "text": "guarantee_id" },
        "sequence": 1,
        "valueString": "Contract/HIB-8D/2026-11-16 00:00:00"
    }
]
,
        "identifier": [
            {
                "type": {"coding": [{"code": "ACSN", "system": "https://hl7.org/fhir/valueset-identifier-type.html"}]},
                "use": "usual",
                "value": patient_uuid
            },
            {
                "type": {"coding": [{"code": "MR", "system": "https://hl7.org/fhir/valueset-identifier-type.html"}]},
                "use": "usual",
                "value": claim.claim_code
            }
        ],
        "item": [
            {
                "category": {"text": "service"},
                "quantity": {"value":float(item["quantity"]) },#float(item["quantity"])
                "sequence": i + 1,
                "service": {"text": "OPD01"},#item.get("item_code", "UNKNOWN")
                "unitPrice": {"value": round(float(item["approved_amount"]), 2)},#round(float(item["approved_amount"]), 2)
            }
            for i, item in enumerate(prevalidated_items)
        ],
        "total": {"value": claim.amount_claimed},
        "careType":"O",#care type shall be I and O only care_type_map.get(claim.service_type,
  
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
        "nmc": ",".join(claim.doctor_nmc) if isinstance(claim.doctor_nmc, list) else claim.doctor_nmc,
        "type": {"text":service_type_mapped.get(claim.service_type,"O")},#service_type_mapped.get(claim.service_type, # visit type shall be O R and E only Others Referral and Emergency   
    }


    try:
        imis_response = await imis_services.submit_claim(fhir_claim_payload, session)
    except Exception as exc:
        logging.error(f"IMIS submission failed for claim {claim_code}: {exc}")
        raise HTTPException(status_code=500, detail=f"IMIS submission failed: {str(exc)}") from exc


    claim.status = "submitted"


    imis_record = ImisResponse(
        patient_id=claim.patient_id,
        raw_response=json.loads(json.dumps(imis_response, default=str)),
        fetched_at=datetime.utcnow()
    )
    db.add(imis_record)

    try:
        db.commit()
        db.refresh(claim)
    except Exception as exc:
        db.rollback()
        logging.error(f"Failed to commit claim or IMIS record: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to save submission record: {exc}")

    return {
        "message": "Claim successfully submitted to IMIS",
        "claim_code": claim.claim_code,
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
    patient = db.query(Patient).filter(Patient.patient_uuid == patient_uuid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    claims = db.query(Claim).filter(Claim.patient_id == patient.id).order_by(Claim.claim_code.desc()).all()
    
    return {
        "count": len(claims),
        "results": claims
    }

# @router.post("/submit_claim/{claim_code}")
# async def submit_claim_endpoint(
#     claim_code: str,
#     username: str,
#     db: Session = Depends(get_db),
# ):
    
            
#     session_obj = db.query(IMISSession).filter(IMISSession.username == username).first()

#     if not session_obj:
#             raise HTTPException(status_code=401, detail="Invalid username or no active IMIS session found")
        
#     session= get_imis_session(db, username)

#     claim = (
#         db.query(Claim)
#         .options(joinedload(Claim.patient))
#         .filter(Claim.claim_code == claim_code)
#         .first()
#     )
    
#     if not claim:
#         raise HTTPException(status_code=404, detail="Claim not found")

#     if not claim.patient:
#         raise HTTPException(status_code=404, detail="Patient not found for this claim")

#     if claim.status != "pending":
#         raise HTTPException(
#             status_code=400,
#             detail=f"Only 'pending' claims can be submitted. Current status: {claim.status}"
#         )

#     patient=db.query(Patient).filter(Patient.id==claim.patient_id).first()

#     patient_uuid = patient.patient_uuid 
#     imis_claim_code = uuid.uuid4().hex
#     # Prevalidation check
#     if not claim.prevalidation_result or not claim.prevalidation_result.get("items"):
#         raise HTTPException(status_code=400, detail="Claim not prevalidated or has no items")

#     care_type_map = {"OPD": "O", "IPD": "I", "Emergency": "O","ER":"O"}
#     icd_codes = json.loads(claim.icd_codes) if isinstance(claim.icd_codes, str) else claim.icd_codes

#     cache_entry = (
#         db.query(EligibilityCache)
#         .filter(EligibilityCache.patient_uuid == patient.patient_uuid)
#         .order_by(EligibilityCache.checked_at.desc())
#         .first()
#     )

#     if not cache_entry or not cache_entry.raw_response.get("data", {}).get("insurance"):
#         raise HTTPException(status_code=400, detail="No insurance found in eligibility cache")

#     insurance_entries = cache_entry.raw_response["data"]["insurance"]
#     guarantee_id = insurance_entries[0]["contract"]["reference"]


#     fhir_claim_payload = {
#         "resourceType": "Claim",
#         "billablePeriod": {
#             "start": claim.claim_date.isoformat(),
#             "end": claim.claim_date.isoformat()
#         },
#         "created": datetime.utcnow().isoformat(),  
#         "patient": {"reference": f"Patient/{patient_uuid}"},
#         "identifier": [
#             {
#                 "type": {
#                     "coding": [{"code": "ACSN", "system": "https://hl7.org/fhir/valueset-identifier-type.html"}]
#                 },
#                 "use": "usual",
#                 "value": uuid.uuid4().hex 
#             },
#             {
#                 "type": {
#                     "coding": [{"code": "MR", "system": "https://hl7.org/fhir/valueset-identifier-type.html"}]
#                 },
#                 "use": "usual",
#                 "value": claim.claim_code  
#             }
#         ],

#         "item": [
#             {
#                 "category": {"text": "service"},# service or item
#                 "quantity": {"value": float(item["quantity"])},
#                 "sequence": i+1,
#                 "service": {"text": "MED002IVF"},#item["item_code"]
#                 "unitPrice": {"value": round(float(item["approved_amount"]),2)},
#             }
#             for i, item in enumerate(claim.prevalidation_result.get("items", []))
#         ],
#         "total": {"value": claim.amount_claimed},
#         "careType": care_type_map.get(claim.service_type, "O"),#care type shall be I and O only
#         "type": {"text": "O"},  # visit type shall be O R and E only OPD Referral and Emergency     care_type_map.get(claim.service_type, "O")
#         "enterer": {"reference": "Practitioner/7aa79c53-057e-4e77-8576-dfcfb03584a8"},
#         "facility": {"reference": "Location/1ac457d3-efd3-4a67-89b3-bf8cbe18045d"},
#         #here for testing this is commented out above is the hardcoded value for now
#         # "enterer": {"reference": f"Practitioner/{claim.enterer_reference}"},
#         # "facility": {"reference": f"Location/{claim.facility_reference}"},
#         "diagnosis": [
#             {
#                 "sequence": i + 1,
#                 "type": [{"text": "icd_0"}],
#                 "diagnosisCodeableConcept": {
#                     "coding": [{"code": code}]
#                 }
#             }
#             for i, code in enumerate(icd_codes or [])
#         ],
#         "nmc": ",".join(claim.doctor_nmc)  


#     }

#     # Submit to IMIS
#     try:
#         imis_response = await imis_services.submit_claim(fhir_claim_payload, session)
#     except Exception as exc:
#         logging.error(f"IMIS submission failed for claim {claim_code}: {exc}")
#         raise HTTPException(status_code=500, detail=f"IMIS submission failed: {str(exc)}") from exc

#     # Update status and save response
#     claim.status = "submitted"
#     if not claim.patient_id:
#         raise HTTPException(status_code=500, detail="Claim.patient_id is missing; cannot save IMIS response")


#     raw_response_serializable = json.loads(json.dumps(imis_response, default=str))

#     imis_record = ImisResponse(
#         patient_id=claim.patient_id,
#         raw_response=raw_response_serializable,
#         fetched_at=datetime.utcnow()
#     )

#     db.add(imis_record)

#     try:
#         db.commit()
#         db.refresh(claim)
#     except Exception as exc:
#         db.rollback()
#         logging.error(f"Failed to commit claim {claim.claim_code} or IMIS record: {exc}")
#         raise HTTPException(status_code=500, detail=f"Failed to save submission record: {exc}")

#     return {
#         "message": "Claim successfully submitted to IMIS",
#         "claim_code": claim.claim_code,
#         "submitted_at": datetime.utcnow().isoformat(),
#         "imis_response": imis_response
#     }

