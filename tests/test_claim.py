# tests/test_claim.py
import pytest
import respx
from httpx import Response
from datetime import date
import json

from app.model import ClaimInput, ClaimableItem, Diagnosis


@pytest.mark.asyncio
async def test_get_patient_and_eligibility_success(client, respx_mock):
    respx_mock.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Patient/",
        params={"identifier": "1234567890"}
    ).mock(return_value=Response(200, json={
        "entry": [{
            "resource": {
                "id": "740500036",
                "name": [{"given": ["Test", "User"]}],
                "birthDate": "1990-01-01",
                "gender": "male"
            }
        }]
    }))

    respx_mock.post(
        "http://imislegacy.hib.gov.np/api/api_fhir/EligibilityRequest/"
    ).mock(return_value=Response(201, json={"resourceType": "EligibilityResponse"}))

    response = await client.post(
        "/patient/full-info",
        json={"identifier": "1234567890", "username": "user", "password": "pass"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test User"


@pytest.mark.asyncio
async def test_prevalidation_endpoint(client, respx_mock):
    await test_get_patient_and_eligibility_success(client, respx_mock)

    claim_data = {
        "patient_id": "1234567890",
        "service_type": "OPD",
        "visit_date": str(date.today()),
        "submit_date": str(date.today()),
        "service_code": "SVC001",
        "claim_time": "discharge",
        "claimable_items": [{
            "item_code": "MED001",
            "name": "Paracetamol",
            "quantity": 2,
            "cost": "100.00",
            "type": "medicine",
            "category": "general"
        }],
        "icd_codes": ["A00"],
        "department": "General",
        "referral_provided": True,
        "hospital_type": "private",
        "claim_code": "CLM001",
        "diagnosis": {"provisional": "A00"},
        "enterer_reference": "pract123",
        "facility_reference": "loc123",
        "doctor_nmc": ["NMC001"]
    }

    response = await client.post(
        "/prevalidation?username=test&password=test",
        json=claim_data
    )

    assert response.status_code == 200
    assert "local_validation" in response.json()


@pytest.mark.asyncio
async def test_submit_claim_full_flow(client, respx_mock):
    await test_get_patient_and_eligibility_success(client, respx_mock)

    respx_mock.post(
        "http://imislegacy.hib.gov.np/api/api_fhir/Claim/"
    ).mock(return_value=Response(201, json={
        "identifier": [{"type": {"coding": [{"code": "MR"}]}, "value": "CLM001"}],
        "outcome": {"text": "complete"}
    }))

    response = await client.post(
        "/submit_claim/claim123",
        json={
            "patient_id": "1234567890",
            "service_type": "OPD",
            "visit_date": str(date.today()),
            "claim_code": "CLM001",
            "claimable_items": [{
                "item_code": "MED001",
                "name": "Paracetamol",
                "quantity": 2,
                "cost": "100.00",
                "type": "medicine",
                "category": "general"
            }],
            "icd_codes": ["A00"],
            "department": "General",
            "enterer_reference": "pract123",
            "facility_reference": "loc123",
            "doctor_nmc": ["NMC001"]
        },
        headers={"username": "u", "password": "p"}
    )

    assert response.status_code == 200
    assert response.json()["claim_code"] == "CLM001"


def test_get_all_claims(client):
    response = client.get("/claims/all")
    assert response.status_code == 200