# tests/test_local_validator_full_fixed.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock
from decimal import Decimal

from app.services.local_validator import prevalidate_claim, ClaimInput
from app.model import ClaimableItem, Diagnosis
from app.insurance_database import PatientInformation, ImisResponse
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def patch_external_functions(monkeypatch):
    import app.services.local_validator as validator_module

    # Simplified rules for testing
    monkeypatch.setattr(validator_module, "get_rules", lambda: {
        "claim_categories": {
            "OPD": {"rules": {
                "ticket_valid_days": 7,
                "submit_daily_after_service": True,
                "require_referral_for_inter_department": True,
            }},
            "IPD": {"rules": {"submit_at_discharge": True}},
            "ER": {"rules": {"submit_at_discharge": True}},
        },
        "non_covered_services": {"items": [{"name": "spectacles", "claimable": False}]},
        "general_rules": {
            "surgery": {"claim_percentage": {"first_disease": 100, "second_disease": 50}},
            "medical_management": {"claim_percentage": {"first_disease": 100, "second_disease": 50}},
            "max_bed_charge_per_day": 5000
        },
        "rules_version": "1.0"
    })

    # Patch get_med to return correct types for different codes
    def fake_get_med(code):
        if code.startswith("SURG"):
            return {"type": "surgery", "rate_npr": 1000.0}
        elif code.startswith("BED"):
            return {"type": "medical_management", "rate_npr": 10000.0}
        elif code.startswith("SPEC"):
            return {"type": "medical_management", "rate_npr": 200.0}
        else:
            return {"type": "medical_management", "rate_npr": 100.0}
    monkeypatch.setattr(validator_module, "get_med", fake_get_med)
    monkeypatch.setattr(validator_module, "get_package", lambda code: None)

    # Patch previous claims
    def fake_get_previous_claims_for_patient(db, patient_imis_id):
        class FakeClaim:
            item_code = []
            fetched_at = datetime.now() - timedelta(days=3)
        return [FakeClaim()]
    validator_module._get_previous_claims_for_patient = fake_get_previous_claims_for_patient


@pytest.fixture
def mock_db():
    db = MagicMock()

    class Patient:
        patient_uuid = "uuid123"
        patient_code = "patient123"
        copayment = 0.1
        allowed_money = 1000.0
        used_money = 0.0

    patient = Patient()

    class LastOPDClaim:
        service_code = "SVC001"
        service_type = "OPD"
        status = "approved"
        created_at = datetime.now() - timedelta(days=3)
        department = "General"
        claim_code = "CLM001"
        patient_id = "patient123"

    last_opd_claim = LastOPDClaim()

    patient_query = MagicMock()
    patient_query.filter.return_value.first.return_value = patient

    imis_query = MagicMock()
    imis_query.filter.return_value = imis_query
    imis_query.order_by.return_value = imis_query
    imis_query.first.return_value = last_opd_claim

    def query(model):
        if model is PatientInformation:
            return patient_query
        if model is ImisResponse:
            return imis_query
        raise ValueError(f"Unexpected model queried: {model}")

    db.query = query
    db._patient = patient
    db._last_opd_claim = last_opd_claim
    return db



def test_basic_opd_claim(mock_db):
    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="MED001", name="Paracetamol", quantity=2, cost=100.0,
                                       type="medicine", category="general")],
        icd_codes=["A00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM001",
        diagnosis=Diagnosis(provisional="A00")
    )
    result = prevalidate_claim(claim, db=mock_db)
    assert result["is_locally_valid"] is True
    assert result["total_approved_local"] > 0
    assert result["net_claimable"] > 0

def test_opd_ticket_expired_warning(mock_db):
    mock_db._last_opd_claim.created_at = datetime.now() - timedelta(days=10)
    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="MED001", name="Paracetamol", quantity=1, cost=100.0,
                                       type="medicine", category="general")],
        icd_codes=["A00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM002",
        diagnosis=Diagnosis(provisional="A00")
    )
    result = prevalidate_claim(claim, db=mock_db)
    assert any("OPD ticket expired" in w for w in result["warnings"])

def test_inter_department_referral_warning(mock_db):
    mock_db._last_opd_claim.department = "Cardiology"
    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="MED001", name="Paracetamol", quantity=1, cost=100.0,
                                       type="medicine", category="general")],
        icd_codes=["A00"],
        department="General",
        referral_provided=False,
        hospital_type="private",
        claim_code="CLM003",
        diagnosis=Diagnosis(provisional="A00")
    )
    result = prevalidate_claim(claim, db=mock_db)
    assert any("requires referral" in w for w in result["warnings"])

def test_same_day_submission_warning(mock_db):
    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today() - timedelta(days=1),
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="MED001", name="Paracetamol", quantity=1, cost=100.0,
                                       type="medicine", category="general")],
        icd_codes=["A00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM004",
        diagnosis=Diagnosis(provisional="A00")
    )
    result = prevalidate_claim(claim, db=mock_db)
    assert any("must be submitted on the same date" in w for w in result["warnings"])

def test_ipd_er_discharge_warning(mock_db):
    for svc in ["IPD", "ER"]:
        claim = ClaimInput(
            patient_id="patient123",
            service_type=svc,
            visit_date=date.today(),
            submit_date=date.today(),
            service_code="SVC002",
            claim_time="midstay",
            claimable_items=[ClaimableItem(item_code="MED002", name="Injection", quantity=1, cost=100.0,
                                           type="medicine", category="general")],
            icd_codes=["B00"],
            department="General",
            referral_provided=True,
            hospital_type="private",
            claim_code="CLM005",
            diagnosis=Diagnosis(provisional="B00")
        )
        result = prevalidate_claim(claim, db=mock_db)
        assert any("must be submitted at discharge" in w for w in result["warnings"])

def test_no_remaining_balance_raises(mock_db):
    mock_db._patient.allowed_money = 100
    mock_db._patient.used_money = 100
    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="MED001", name="Paracetamol", quantity=1, cost=50.0,
                                       type="medicine", category="general")],
        icd_codes=["A00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM006",
        diagnosis=Diagnosis(provisional="A00")
    )
    with pytest.raises(HTTPException):
        prevalidate_claim(claim, db=mock_db)

def test_non_covered_item(mock_db):
    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC003",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="SPEC01", name="Spectacles", quantity=1, cost=200.0,
                                       type="medicine", category="general")],
        icd_codes=["C00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM007",
        diagnosis=Diagnosis(provisional="C00")
    )
    result = prevalidate_claim(claim, db=mock_db)
    assert any("not covered" in w.lower() for w in result["items"][0]["warnings"])

def test_surgery_and_medical_percentages(mock_db):
    import app.services.local_validator as validator_module
    validator_module.get_med = lambda code: {"type": "surgery", "rate_npr": 1000.0} if code.startswith("SURG") else {"type": "medical_management", "rate_npr": 100.0}

    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC004",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="SURG01", name="Surgery1", quantity=1, cost=1000.0,
                                       type="surgery", category="general")],
        icd_codes=["D00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM008",
        diagnosis=Diagnosis(provisional="D00")
    )
    result = prevalidate_claim(claim, db=mock_db)
    assert result["total_approved_local"] > 0

    claim.claimable_items[0].item_code = "MEDMG01"
    claim.claimable_items[0].type = "medical_management"
    result2 = prevalidate_claim(claim, db=mock_db)
    assert result2["total_approved_local"] > 0

def test_bed_charge_cap(mock_db):
    claim = ClaimInput(
        patient_id="patient123",
        service_type="IPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC005",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="BED01", name="Bed charge", quantity=1, cost=10000.0,
                                       type="bed", category="general")],
        icd_codes=["E00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM009",
        diagnosis=Diagnosis(provisional="E00")
    )
    result = prevalidate_claim(claim, db=mock_db)
    assert result["items"][0]["approved_amount"] <= 5000
    assert any("capped" in w.lower() for w in result["items"][0]["warnings"])
