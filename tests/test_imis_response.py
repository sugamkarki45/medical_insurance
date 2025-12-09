# tests/test_imis_response.py
import pytest
import httpx
import respx
from httpx import Response

from app.services.imis_services import (
    get_auth_header,
    get_patient_info,
    check_eligibility,
    submit_claim,
    get_all_claims,
    get_claim_by_uuid,
    extract_copayment,
)


@pytest.fixture
def mocked_httpx():
    with respx.mock:
        yield respx


@pytest.mark.asyncio
async def test_get_auth_header():
    headers = get_auth_header("admin", "secret123")
    auth_token = "YWRtaW46c2VjcmV0MTIz"  # base64("admin:secret123")

    assert headers == {
        "Authorization": f"Basic {auth_token}",
        "remote-user": "admin"
    }

    headers2 = get_auth_header("", "pass")
    assert "remote-user" not in headers2


@pytest.mark.asyncio
async def test_get_patient_info_success(mocked_httpx):
    patient_id = "1234567890"
    mock_response = {
        "resourceType": "Bundle",
        "total": 1,
        "entry": [{
            "resource": {
                "id": "740500036",
                "identifier": [{"value": patient_id}]
            }
        }]
    }

    mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Patient/",
        params={"identifier": patient_id}
    ).mock(return_value=Response(200, json=mock_response))

    result = await get_patient_info(patient_id, "user", "pass")

    assert result["success"] is True
    assert result["data"] == mock_response


@pytest.mark.asyncio
async def test_get_patient_info_not_found(mocked_httpx):
    patient_id = "999"
    mock_response = {
        "resourceType": "Bundle",
        "total": 0,
        "entry": []  # Explicit empty entry
    }

    mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Patient/",
        params={"identifier": patient_id}
    ).mock(return_value=Response(200, json=mock_response))

    result = await get_patient_info(patient_id, "user", "pass")

    assert result["success"] is True
    assert "data" in result
    assert result["data"]["total"] == 0


@pytest.mark.asyncio
async def test_get_patient_info_http_error(mocked_httpx):
    mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Patient/",
        params={"identifier": "123"}
    ).mock(return_value=Response(401, text="Unauthorized"))

    result = await get_patient_info("123", "wrong", "pass")
    assert result["success"] is False
    assert result["status"] == 401


@pytest.mark.asyncio
async def test_check_eligibility_success(mocked_httpx):
    patient_id = "1234567890"

    # Mock patient lookup
    patient_resp = {
        "resourceType": "Bundle",
        "entry": [{
            "resource": {
                "id": "740500036",
                "identifier": [{"value": patient_id}]
            }
        }]
    }
    eligibility_resp = {
        "resourceType": "EligibilityResponse",
        "outcome": "complete",
        "extension": [{
            "url": "http://hib.gov.np/fhir/StructureDefinition/Copayment",
            "valueDecimal": 0.1
        }]
    }

    mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Patient/",
        params={"identifier": patient_id}
    ).mock(return_value=Response(200, json=patient_resp))

    mocked_httpx.post(
        "http://imislegacy.hib.gov.np/api/api_fhir/EligibilityRequest/"
    ).mock(return_value=Response(201, json=eligibility_resp))

    result = await check_eligibility(patient_id, "user", "pass")

    assert result["success"] is True
    assert result["data"] == eligibility_resp


@pytest.mark.asyncio
async def test_check_eligibility_patient_not_found(mocked_httpx):
    mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Patient/",
        params={"identifier": "000"}
    ).mock(return_value=Response(200, json={"resourceType": "Bundle", "total": 0, "entry": []}))

    result = await check_eligibility("000", "user", "pass")
    assert result["success"] is False
    assert result["reason"] == "Patient not found"


@pytest.mark.asyncio
async def test_submit_claim_success(mocked_httpx):
    payload = {"resourceType": "Claim", "status": "active"}
    claim_response = {"id": "CLAIM-001", "status": "entered-in-error"}

    mocked_httpx.post(
        "http://imislegacy.hib.gov.np/api/api_fhir/Claim/"
    ).mock(return_value=Response(201, json=claim_response))

    result = await submit_claim(payload, "user", "pass")

    assert result["success"] is True
    assert result["status"] == 201
    assert result["response"] == '{"id":"CLAIM-001","status":"entered-in-error"}'  


@pytest.mark.asyncio
async def test_submit_claim_failure(mocked_httpx):
    payload = {"invalid": "data"}

    mocked_httpx.post(
        "http://imislegacy.hib.gov.np/api/api_fhir/Claim/"
    ).mock(return_value=Response(400, text="Invalid FHIR resource"))

    result = await submit_claim(payload, "user", "pass")

    assert result["success"] is False
    assert result["status"] == 400
    assert "Invalid FHIR resource" in result["response"]


@pytest.mark.asyncio
async def test_get_all_claims(mocked_httpx):
    mock_bundle = {
        "resourceType": "Bundle",
        "total": 5,
        "entry": [{"resource": {"id": "C1"}}] * 5
    }

    route = mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Claim/"
    ).mock(return_value=Response(200, json=mock_bundle))

    result = await get_all_claims("user", "pass", page=2, page_size=10, status="active")

    assert result["success"] is True
    assert result["data"]["total"] == 5
    assert route.called
    assert route.call_count == 1
    assert "status=active" in str(route.calls.last.request.url.params)
    assert "page=2" in str(route.calls.last.request.url.params)
    assert "count=10" in str(route.calls.last.request.url.params)


@pytest.mark.asyncio
async def test_get_all_claims_with_patient_filter(mocked_httpx):
    route = mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Claim/"
    ).mock(return_value=Response(200, json={"total": 1}))

    await get_all_claims("user", "pass", patient_identifier="1234567890")

    assert route.called
    assert "patient.identifier=1234567890" in str(route.calls.last.request.url.params)


@pytest.mark.asyncio
async def test_get_claim_by_uuid_found(mocked_httpx):
    claim_data = {"id": "CLAIM-123", "status": "active"}

    mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Claim/CLAIM-123"
    ).mock(return_value=Response(200, json=claim_data))

    result = await get_claim_by_uuid("CLAIM-123", "user", "pass")

    assert result["success"] is True
    assert result["data"]["id"] == "CLAIM-123"


@pytest.mark.asyncio
async def test_get_claim_by_uuid_not_found(mocked_httpx):
    mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Claim/MISSING-999"
    ).mock(return_value=Response(404, text="Not Found"))

    result = await get_claim_by_uuid("MISSING-999", "user", "pass")

    assert result["success"] is False
    assert result["status"] == 404
    assert "Claim not found in IMIS" in result["error"]


@pytest.mark.asyncio
async def test_get_claim_by_uuid_server_error(mocked_httpx):
    mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Claim/BROKEN"
    ).mock(return_value=Response(500, text="Server exploded"))

    result = await get_claim_by_uuid("BROKEN", "user", "pass")

    assert result["success"] is False
    assert result["status"] == 500


@pytest.mark.asyncio
async def test_get_claim_by_uuid_connection_error(mocked_httpx):
    mocked_httpx.get(
        "http://imislegacy.hib.gov.np/api/api_fhir/Claim/TIMEOUT"
    ).mock(side_effect=httpx.ConnectTimeout(message="Timeout"))

    result = await get_claim_by_uuid("TIMEOUT", "user", "pass")

    assert result["success"] is False
    assert "error" in result
    assert "Timeout" in result["error"]


# extract_copayment tests - Fixed to iterate in order and return first matching
def test_extract_copayment_value_decimal():
    bundle = {
        "entry": [{
            "resource": {
                "extension": [
                    {"url": "http://hib.gov.np/fhir/StructureDefinition/Copayment", "valueDecimal": 0.2},
                    {"url": "other", "valueString": "test"}
                ]
            }
        }]
    }
    assert extract_copayment(bundle) == 0.2


def test_extract_copayment_value_string():
    bundle = {
        "entry": [{
            "resource": {
                "extension": [
                    {"url": "CopaymentRate", "valueString": "10%"},
                    {"url": "http://hib.gov.np/fhir/StructureDefinition/Copayment", "valueString": "15%"}
                ]
            }
        }]
    }
    assert extract_copayment(bundle) == "10%"  # Now returns the correct one


def test_extract_copayment_no_extension():
    bundle = {"entry": [{"resource": {"id": "123"}}]}
    assert extract_copayment(bundle) is None


def test_extract_copayment_empty_bundle():
    assert extract_copayment({}) is None
    assert extract_copayment({"entry": []}) is None


def test_extract_copayment_malformed():
    assert extract_copayment({"entry": [{"resource": None}]}) is None
    assert extract_copayment(None) is None