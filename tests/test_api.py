# tests/test_api.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from app.main import app  # ← change this if your file is named differently (e.g. api.py)

client = TestClient(app)

def test_prevalidate_endpoint():
    payload = {
        "patient_id": "patient123",
        "service_type": "OPD",
        "visit_date": "2025-12-08",
        "submit_date": "2025-12-08",
        "service_code": "SVC001",
        "claim_time": "discharge",
        "claimable_items": [
            {
                "item_code": "MED001",
                "name": "Paracetamol",
                "quantity": 10,
                "cost": 100,
                "type": "medicine",
                "category": "general"
            }
        ],
        "icd_codes": ["A00"],
        "department": "General",
        "referral_provided": True,
        "hospital_type": "private",
        "claim_code": "CLM001",
        "diagnosis": {"provisional": "A00"}
    }

    # CHANGE THIS TO YOUR ACTUAL ENDPOINT PATH
    response = client.post("/prevalidate-claim", json=payload)
    # or try: /api/v1/prevalidate, /claim/prevalidate, etc.

    assert response.status_code == 200
    data = response.json()
    assert data["is_locally_valid"] is True
    assert data["net_claimable"] == 900.0