# tests/test_claim.py
import respx
from httpx import AsyncClient, Response
import pytest,httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.insurance_database import Base, get_db, ImisResponse
from app.model import ClaimInput


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
    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://testserver", transport=httpx.ASGITransport(app=app)) as ac:
        yield ac


@pytest.fixture
def respx_mock_fixture():
    with respx.mock(base_url="http://imislegacy.hib.gov.np/api/api_fhir") as mock:
        yield mock


@pytest.mark.anyio
async def test_get_patient_and_eligibility_success(client, respx_mock_fixture):
    respx_mock_fixture.get("/Patient/").mock(
        return_value=Response(200, json={
            "entry": [{
                "resource": {
                    "id": "740500036",
                    "name": [{"given": ["Test", "User"]}],
                    "birthDate": "1990-01-01",
                    "gender": "male"
                }
            }]
        })
    )

    respx_mock_fixture.post("/EligibilityRequest/").mock(
        return_value=Response(201, json={"resourceType": "EligibilityResponse"})
    )

    payload = {"identifier": "1234567890", "username": "user", "password": "pass"}
    response = await client.post("/api/patient/full-info", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["patient"]["id"] == "740500036"

@pytest.mark.anyio
async def test_prevalidation_endpoint(client, respx_mock_fixture):
    # Ensure patient eligibility runs first
    await test_get_patient_and_eligibility_success(client, respx_mock_fixture)

    payload = {"claim_code": "CLAIM001", "items": [{"item_code": "OPD01"}], "username": "user", "password": "pass"}
    response = await client.post("/api/claim/prevalidate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "prevalidation_result" in data

@pytest.mark.anyio
async def test_submit_claim_full_flow(client, respx_mock_fixture):
    await test_get_patient_and_eligibility_success(client, respx_mock_fixture)

    payload = {
        "claim_code": "CLAIM002",
        "items": [{"item_code": "OPD02"}],
        "username": "user",
        "password": "pass"
    }
    response = await client.post("/api/claim/submit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "status" in data

@pytest.mark.anyio
async def test_get_all_claims(client):
    db = next(override_get_db())
    # Insert a fake claim for testing
    claim = ImisResponse(
        claim_code="TEST123",
        patient_id="1234567890",
        status="submitted",
        items=[{"item_code": "OPD01"}]
    )
    db.add(claim)
    db.commit()

    response = await client.get("/api/claims/all")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["claim_code"] == "TEST123"
