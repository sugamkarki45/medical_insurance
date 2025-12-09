# tests/test_claim.py
import respx
from httpx import AsyncClient, Response, ASGITransport
import pytest, httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.insurance_database import Base, get_db, ImisResponse


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(base_url="http://testserver", transport=transport) as ac:
        yield ac


@pytest.fixture
def respx_mock_fixture():
    with respx.mock(base_url="http://imislegacy.hib.gov.np/api/api_fhir") as mock:
        yield mock


# -------------------------------------------------------------------------------
# TEST 1: patient full info + eligibility
# -------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_get_patient_and_eligibility_success(client, respx_mock_fixture):

    # Mock the external IMIS full-info endpoint
    respx_mock_fixture.post("/patient/full-info").mock(
        return_value=Response(
            201,
            json={
                "resourceType": "EligibilityResponse",
                "patient": {"id": "740500036"}
            }
        )
    )

    # FIX: Correct payload for your model
    payload = {
        "patient_code": "740500036",
        "username": "user",
        "password": "pass"
    }

    response = await client.post("/api/patient/full-info", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["patient"]["id"] == "740500036"


# -------------------------------------------------------------------------------
# TEST 2: prevalidation
# -------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_prevalidation_endpoint(client, respx_mock_fixture):

    await test_get_patient_and_eligibility_success(client, respx_mock_fixture)

    payload = {
        "claim_code": "CLAIM001",
        "items": [{"item_code": "OPD01"}],
        "username": "user",
        "password": "pass"
    }

    response = await client.post("/api/prevalidate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "prevalidation_result" in data


# -------------------------------------------------------------------------------
# TEST 3: submit claim
# -------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_submit_claim_full_flow(client, respx_mock_fixture):

    await test_get_patient_and_eligibility_success(client, respx_mock_fixture)

    payload = {
        "claim_code": "CLAIM002",
        "items": [{"item_code": "OPD02"}],
        "username": "user",
        "password": "pass"
    }

    response = await client.post("/api/submit_claim", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "status" in data


# -------------------------------------------------------------------------------
# TEST 4: get all claims
# -------------------------------------------------------------------------------
@pytest.mark.anyio
async def test_get_all_claims(client):

    db = next(override_get_db())

    fake_claim = ImisResponse(
        claim_code="TEST123",
        patient_id="1234567890",
        status="submitted",
        items=[{"item_code": "OPD01"}]
    )

    db.add(fake_claim)
    db.commit()

    response = await client.get("/api/claims/all")
    assert response.status_code == 200

    data = response.json()

    assert len(data) > 0
    assert data[0]["claim_code"] == "TEST123"
