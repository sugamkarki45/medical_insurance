import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import pytest
from decimal import Decimal
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

from app.services.local_validator import prevalidate_claim, ClaimInput
from app.model import ClaimableItem, Diagnosis
from app.insurance_database import PatientInformation, ImisResponse


@pytest.fixture(autouse=True)
def patch_external_functions(monkeypatch):
    import app.services.local_validator as validator_module

    monkeypatch.setattr(validator_module, "get_rules", lambda: {
        "claim_categories": {
            "OPD": {
                "rules": {
                    "ticket_valid_days": 7,
                    "submit_daily_after_service": True,
                    "require_referral_for_inter_department": True
                }
            },
            "IPD": {"rules": {"submit_at_discharge": True}},
            "ER": {"rules": {"submit_at_discharge": True}},
        },
        "non_covered_services": {"items": []},
        "general_rules": {
            "surgery": {"claim_percentage": {"first_disease": 100}},
            "medical_management": {"claim_percentage": {"first_disease": 100}},
            "max_bed_charge_per_day": 5000
        },
        "rules_version": "1.0"
    })

    monkeypatch.setattr(validator_module, "get_med", lambda code: {"type": "medical_management", "rate_npr": 100})
    monkeypatch.setattr(validator_module, "get_package", lambda code: None)


@pytest.fixture
def mock_db():
    db = MagicMock()


    patient = MagicMock()
    patient.patient_uuid = "uuid123"
    patient.copayment = Decimal("0.1")       
    patient.allowed_money = Decimal("1000")  
    patient.used_money = Decimal("0")        


    class LastOPDClaim:
        service_code = "SVC001"
        service_type = "OPD"
        status = "approved"
        created_at = datetime.now() - timedelta(days=3)
        department = "General"
        claim_code = "CLM001"

    last_opd_claim = LastOPDClaim()

    def query_side_effect(model):
        mock_query = MagicMock()
        if model is PatientInformation:
            mock_query.filter.return_value.first.return_value = patient
        elif model is ImisResponse:
            mock_query.filter.return_value.filter.return_value.order_by.return_value.first.return_value = last_opd_claim
        return mock_query

    db.query.side_effect = query_side_effect
    db.patient = patient
    db.last_opd_claim = last_opd_claim
    return db


def test_prevalidate_claim_basic(mock_db):
    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[
            ClaimableItem(
                item_code="MED001",
                name="Paracetamol",
                quantity=2,
                cost=Decimal("100"),
                type="medicine",
                category="general"
            )
        ],
        icd_codes=["A00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM001",
        diagnosis=Diagnosis(provisional="A00")
    )

    result = prevalidate_claim(claim, db=mock_db)

    assert result["rules_version"] == "1.0"
    assert result["is_locally_valid"] is True
    assert result["total_approved_local"] == Decimal("180")  
    assert result["net_claimable"] == Decimal("180")
    assert result["total_cost"] == Decimal("200")
    assert result["copayment_amount"] == Decimal("20")


def test_prevalidate_claim_no_remaining_balance(mock_db):
    mock_db.patient.allowed_money = Decimal("1000")
    mock_db.patient.used_money = Decimal("1000")

    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[
            ClaimableItem(item_code="MED001", name="Paracetamol", quantity=1, cost=Decimal("100"),
                          type="medicine", category="general")
        ],
        icd_codes=["A00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM002",
        diagnosis=Diagnosis(provisional="A00")
    )

    with pytest.raises(ValueError, match=r"(?i)insufficient.*balance|coverage.*exhausted|no remaining|limit reached"):
        prevalidate_claim(claim, db=mock_db)


def test_prevalidate_claim_zero_allowed_limit(mock_db):
    mock_db.patient.allowed_money = Decimal("0")
    mock_db.patient.used_money = Decimal("0")

    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[
            ClaimableItem(item_code="MED001", name="Paracetamol", quantity=1, cost=Decimal("100"),
                          type="medicine", category="general")
        ],
        icd_codes=["A00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM003",
        diagnosis=Diagnosis(provisional="A00")
    )

    with pytest.raises(ValueError, match=r"(?i)insufficient.*balance|coverage.*exhausted|no remaining|limit reached"):
        prevalidate_claim(claim, db=mock_db)

def test_prevalidate_claim_exactly_at_limit(mock_db):
    mock_db.patient.allowed_money = Decimal("200")
    mock_db.patient.used_money = Decimal("20")

    claim = ClaimInput(
        patient_id="patient123",
        service_type="OPD",
        visit_date=date.today(),
        submit_date=date.today(),
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[
            ClaimableItem(item_code="MED001", name="Paracetamol", quantity=2, cost=Decimal("100"),
                          type="medicine", category="general")
        ],
        icd_codes=["A00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM004",
        diagnosis=Diagnosis(provisional="A00")
    )

    result = prevalidate_claim(claim, db=mock_db)
    assert result["is_locally_valid"] is True
    assert result["net_claimable"] == Decimal("180")  