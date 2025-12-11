import pytest
from unittest.mock import MagicMock
from datetime import date, datetime, timedelta
from decimal import Decimal
from app.services.local_validator import prevalidate_claim
from app.model import ClaimInput, ClaimableItem, Diagnosis
from app.insurance_database import PatientInformation, ImisResponse


@pytest.fixture(autouse=True)
def patch_rules_and_helpers(monkeypatch):
    """
    Patch rule loader functions and helpers used inside prevalidate_claim.
    Keep rules simplified but matching your provided rules JSON.
    """
    rules = {
        "rules_version": "1.0",
        "claim_categories": {
            "OPD": {
                "rules": {
                    "ticket_valid_days": 7,
                    "single_ticket_per_episode": True,
                    "use_same_claim_code_within_validity": True,
                    "allow_multiple_consultations": True,
                    "require_referral_for_interdepartmental_consultation": True,
                    "submit_daily_after_service": True,
                    "map_followup_to_same_claim_within_validity": True,
                    "require_nmc_and_diagnosis": True
                }
            },
            "IPD": {
                "rules": {
                    "submit_at_discharge": True,
                    "package_based_claim_only": True
                }
            },
            "ER": {
                "rules": {"submit_at_discharge": True}
            }
        },
        "general_rules": {
            "max_bed_charge_per_day": 250,
            "surgery": {"claim_percentage": {"first_disease": 100, "second_disease": 50}},
            "medical_management": {"claim_percentage": {"first_disease": 100, "second_disease": 50}}
        },
        "non_covered_services": {
            "items": [
                {"name": "Spectacles", "claimable": False, "annual_cost_threshold_npr": 1000},
                {"name": "Hearing Instruments", "claimable": False, "annual_cost_threshold_npr": 5000},
            ],
            "ceiling_rule": {"enforcement": "remaining_balance_overrides"}
        },
        "co-payment_method": {
            "co_payment_percentage": 10,
            "exempt_categories": ["ultra_poor", "fchv"]
        }
    }

    monkeypatch.setattr("app.services.local_validator.get_rules", lambda: {
        "rules_version": "1.0",
        "claim_categories": {"OPD": {"rules": {"ticket_valid_days": 7, "submit_daily_after_service": True}}},
        "general_rules": {
            "max_bed_charge_per_day": 250,
            "surgery": {"claim_percentage": {"first_disease": 100, "second_disease": 50}},
            "medical_management": {"claim_percentage": {"first_disease": 100, "second_disease": 50}}
        },
        "non_covered_services": {
            "items": [{"name": "Spectacles", "claimable": False}],
            "ceiling_rule": {"enforcement": "remaining_balance_overrides"}
        },
        "co_payment_method": {}
    })



    def fake_get_med(code):
        code = (code or "").upper()
        if code.startswith("SURG"):
            return {"type": "surgery", "rate_npr": 1000.0}
        if code.startswith("BED"):
            # bed has high rate to test cap
            return {"type": "medical_management", "rate_npr": 10000.0}
        if code.startswith("SPEC"):
            return {"type": "medical_management", "rate_npr": 200.0}
        # default
        return {"type": "medical_management", "rate_npr": 100.0}
    monkeypatch.setattr("app.services.local_validator.get_med", fake_get_med)
    monkeypatch.setattr("app.services.local_validator.get_package", lambda code: None)


@pytest.fixture
def mock_db():
    """
    MagicMock-based DB fixture for prevalidate_claim.
    Provides:
    - a patient with remaining balance
    - previous OPD claim for ticket and same-day checks
    """
    db = MagicMock()

    # Patient row
    patient = MagicMock()
    patient.patient_code = "patient123"
    patient.copayment = 0.1
    patient.allowed_money = 1000.0
    patient.used_money = 0.0

    patient_query = MagicMock()
    patient_query.filter.return_value.first.return_value = patient

    # Last OPD claim for ticket & same-day checks
    last_opd = MagicMock()
    last_opd.service_code = "SVC001"
    last_opd.service_type = "OPD"
    last_opd.status = "approved"
    last_opd.department = "General"
    last_opd.created_at = datetime.now() - timedelta(days=1)  # within ticket
    last_opd.fetched_at = datetime.now() - timedelta(days=1)
    last_opd.item_code = []
    last_opd.claim_code = "CLM001"
    last_opd.patient_id = "patient123"

    imis_query = MagicMock()
    imis_query.filter.return_value = imis_query
    imis_query.order_by.return_value = imis_query
    imis_query.first.return_value = last_opd
    imis_query.all.return_value = [last_opd]  # used for previous_claims sum

    def query(model):
        if model is PatientInformation:
            return patient_query
        if model is ImisResponse:
            return imis_query
        raise ValueError("Unexpected model queried during tests")

    db.query = query
    db._patient = patient
    db._last_opd = last_opd
    return db



def make_claim(**kwargs):
    """Helper to produce ClaimInput with sane defaults, override with kwargs."""
    base = dict(
        patient_id="patient123",
        visit_date=date.today(),
        submit_date=date.today(),
        service_type="OPD",
        service_code="SVC001",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="MED001", name="Paracetamol", quantity=1, cost=100.0,
                                       type="medicine", category="general")],
        icd_codes=["A00"],
        department="General",
        referral_provided=True,
        hospital_type="private",
        claim_code="CLM001",
        diagnosis=Diagnosis(provisional="A00")
    )
    base.update(kwargs)
    return ClaimInput(**base)



def test_basic_opd_claim_passes(mock_db):
    claim = make_claim()
    result = prevalidate_claim(claim, db=mock_db, allowed_money=Decimal("500.00"), used_money=Decimal("100.00"))
    assert result["is_locally_valid"] is True
    assert result["total_approved_local"] > 0
    assert result["net_claimable"] > 0


def test_opd_ticket_expired_warning(mock_db):
    # make last OPD older than ticket window
    mock_db._last_opd.created_at = datetime.now() - timedelta(days=10)
    claim = make_claim(service_code="SVC001", claim_code="CLM002")
    result = prevalidate_claim(claim, db=mock_db)
    # message should mention ticket expired (case-insensitive in checks)
    assert any("ticket expired" in w.lower() for w in result["warnings"])


def test_inter_department_referral_warning(mock_db):
    mock_db._last_opd.department = "Cardiology"
    claim = make_claim(referral_provided=False)
    result = prevalidate_claim(claim, db=mock_db)
    assert any("referral" in w.lower() for w in result["warnings"])




def test_same_day_submission_warning(mock_db):
    claim = make_claim(
        submit_date=date.today() - timedelta(days=1),
        service_code="SVC_NEW"  
    )
    result = prevalidate_claim(claim, db=mock_db)
    assert "Previous OPD ticket still valid" in result["warnings"][0]



def test_non_covered_item_warning(mock_db, monkeypatch):
    monkeypatch.setattr("app.services.local_validator.get_rules", lambda: {
        "rules_version": "1.0",
        "claim_categories": {"OPD": {"rules": {"ticket_valid_days": 7, "submit_daily_after_service": True}}},
        "general_rules": {
            "max_bed_charge_per_day": 250,
            "medical_management": {"claim_percentage": {"first_disease": 100, "second_disease": 50}}
        },
        "non_covered_services": {
            "items": [{"name": "Spectacles", "claimable": False}],
            "ceiling_rule": {"enforcement": "remaining_balance_overrides"}
        },
        "co_payment_method": {}
    })

    claim = make_claim(
        service_type="OPD",
        claimable_items=[ClaimableItem(item_code="SPEC01", name="Spectacles", quantity=1, cost=200.0,
                                       type="medicine", category="general")]
    )
    result = prevalidate_claim(claim, db=mock_db)
    item_warnings = result["items"][0]["warnings"]
    assert any("not covered" in w.lower() or "spectacles" in w.lower() for w in item_warnings), \
        f"Item warnings: {item_warnings}"




def test_ipd_er_discharge_warning(mock_db):
    for svc in ["IPD", "ER"]:
        claim = make_claim(service_type=svc, service_code="SVC002", claim_time="midstay", claim_code="CLM005")
        result = prevalidate_claim(claim, db=mock_db)
        assert any("must be submitted at discharge" in w.lower() for w in result["warnings"])


def test_no_remaining_balance_raises(mock_db):
    # set allowed == used so no available money
    mock_db._patient.allowed_money = 100.0
    mock_db._patient.used_money = 100.0
    claim = make_claim()
    with pytest.raises(Exception):
        # expecting HTTPException raised by validator when available_money <= 0
        prevalidate_claim(claim, db=mock_db)





def test_surgery_and_medical_percentages(mock_db, monkeypatch):
    # Patch get_med to return surgery type for SURG codes
    import app.services.local_validator as validator_mod
    monkeypatch.setattr(validator_mod, "get_med", lambda code: {"type": "surgery", "rate_npr": 1000.0} if code.upper().startswith("SURG") else {"type": "medical_management", "rate_npr": 100.0})

    claim = make_claim(service_code="SVC_SURG", claimable_items=[ClaimableItem(item_code="SURG01", name="Surgery", quantity=1, cost=1000.0, type="surgery", category="general")])
    result = prevalidate_claim(claim, db=mock_db)
    assert result["total_approved_local"] > 0

    # Now medical_management
    claim2 = make_claim(service_code="SVC_MED", claimable_items=[ClaimableItem(item_code="MEDMG01", name="MedMgmt", quantity=1, cost=200.0, type="medicine", category="general")])
    result2 = prevalidate_claim(claim2, db=mock_db)
    assert result2["total_approved_local"] > 0


def test_bed_charge_cap_applies(mock_db):
    # Bed item with huge rate should be capped by rules["general_rules"]["max_bed_charge_per_day"] = 250
    claim = make_claim(
        service_type="IPD",
        service_code="SVC_BED",
        claim_time="discharge",
        claimable_items=[ClaimableItem(item_code="BED01", name="Bed charge", quantity=1, cost=10000.0,
                                       type="medicine", category="general")],
        claim_code="CLM_BED"
    )
    result = prevalidate_claim(claim, db=mock_db,allowed_money=Decimal(500))
    item = result["items"][0]
    assert item["approved_amount"] <= 250.0
    assert any("capped" in w.lower() for w in item["warnings"])


from fastapi import HTTPException

def test_time_window_quantity_limit_raises_or_caps(monkeypatch, mock_db):
    import app.services.local_validator as validator_mod

    def fake_med_with_capping(code):
        return {
            "type": "medical_management",
            "rate_npr": 100.0,
            "capping": {"max_per_visit": 2, "max_days": 30}
        }
    monkeypatch.setattr(validator_mod, "get_med", fake_med_with_capping)


    prev_claim = MagicMock()
    prev_claim.fetched_at = datetime.now() - timedelta(days=1)
    prev_claim.item_code = [{"item_code": "TIME01", "qty": 2}]


    monkeypatch.setattr(
        validator_mod,
        "_get_previous_claims_for_patient",
        lambda db, patient_id: [prev_claim]
    )

    claim = make_claim(
        claimable_items=[ClaimableItem(
            item_code="TIME01",
            name="Time-window item",
            quantity=1,
            cost=100.0,
            type="medicine",
            category="general"
        )]
    )

    with pytest.raises(HTTPException):
        validator_mod.prevalidate_claim(claim, db=mock_db)




