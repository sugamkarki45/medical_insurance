# tests/test_claim.py
import pytest, uuid
from httpx import AsyncClient, Response, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.insurance_database import Base, get_db, ImisResponse, PatientInformation


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        
app.dependency_overrides[get_db] = lambda: db_session()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(base_url="http://testserver", transport=transport) as ac:
        yield ac


@pytest.fixture
def respx_mock_fixture():
    import respx
    with respx.mock(base_url="http://imislegacy.hib.gov.np/api/api_fhir") as mock:
        yield mock


@pytest.fixture
def create_patient(db_session):
    patient = PatientInformation(
        patient_code="740500036",
        patient_uuid=str(uuid.uuid4()),
        name="John Doe",
        gender="male",
        copayment=0,
        allowed_money=1000,
        used_money=0,
        category="Normal",
        policy_id="POL123",
    )
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return patient


@pytest.mark.anyio
async def test_get_patient_and_eligibility_success(client, respx_mock_fixture):
    # Ensure URL matches the FastAPI route
    respx_mock_fixture.post("/api/patient/full-info").mock(
        return_value=Response(
            200,
            json={"success": True, "data": {"entry":[{"resource":{"id":"740500036","name":[{"given":["John"]}],"gender":"male"}}]}}
        )
    )
    respx_mock_fixture.post("/api/eligibility").mock(
        return_value=Response(
            200,
            json={"success": True, "data":{"allowed_money":1000,"used_money":0}}
        )
    )

    payload = {
        "identifier": "740500036",
        "username": "user",
        "password": "pass"
    }
    response = await client.post("/api/patient/full-info", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["patient_code"] == "740500036"
    assert data["gender"] == "male"

@pytest.mark.anyio
async def test_prevalidation_endpoint(client, create_patient):
    payload = {
        "patient_id": create_patient.patient_code,
        "claim_code": "CLAIM001",
        "claimable_items": [
            {"item_code": "OPD01", "quantity": 1, "cost": 100, "category": "General", "type": "medical"}
        ]
    }
    response = await client.post("/api/prevalidation?username=user&password=pass", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "local_validation" in data
    assert "imis_patient" in data
    assert "eligibility" in data

@pytest.mark.anyio
async def test_submit_claim_full_flow(client, create_patient):
    payload = {
        "patient_id": create_patient.patient_code,
        "claim_code": "CLAIM002",
        "service_type": "OPD",
        "service_code": "OPD01",
        "doctor_nmc": ["NMC123"],
        "icd_codes": ["I10"],
        "claimable_items": [
            {"item_code": "OPD01", "quantity": 1, "cost": 100, "category": "General", "type": "medical"}
        ],
        "enterer_reference": "E1",
        "facility_reference": "F1",
        "department": "General",
        "visit_date": "2025-12-11"
    }
    response = await client.post(f"/api/submit_claim/{uuid.uuid4().hex}?username=user&password=pass", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Claim successfully submitted to IMIS"
    assert "claim_code" in data
    assert "items" in data

@pytest.mark.anyio
async def test_get_all_claims(client, create_patient, db_session):
    claim_record = ImisResponse(
        claim_code="TEST123",
        patient_id=create_patient.patient_code,
        status="submitted",
        items=[{"item_code": "OPD01"}]
    )
    db_session.add(claim_record)
    db_session.commit()
    db_session.refresh(claim_record)

    response = await client.get("/api/claims/all")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0
    assert any(claim["claim_code"] == "TEST123" for claim in data["results"])
