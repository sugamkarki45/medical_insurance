from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import date
import uuid
from enum import Enum


class PatientCategory(str, Enum):
    general = "general"
    poor = "poor"
    ultra_poor = "ultra_poor"
    fchv = "fchv"
    hiv_aids = "hiv_aids"
    severe_tb = "severe_tb"
    severe_disability = "severe_disability"
    leprosy = "leprosy"


class ItemType(str, Enum):
    medicine = "medicine"
    lab_test = "lab_test"
    surgery = "surgery"  
    procedure = "procedure"
    diagnostic_imaging = "diagnostic_imaging"
    other = "other"


class ClaimableItem(BaseModel):
    type: ItemType = Field(..., description="Type of item (medicine, lab_test, surgery, etc.)")
    item_code: str
    quantity: int 
    cost: float
    name: str

    @validator("type", pre=True)
    def normalize_item_type(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v
    
    @validator("item_code", "name", pre=True)
    def normalize_strings(cls, v):
        if isinstance(v, str):
            return v.upper().strip()
        return v


class Diagnosis(BaseModel):
    icd_code: str
    provisional: Optional[str] = None
    differential: Optional[str] = None
    final: Optional[str] = None
    is_chronic: bool = False


class HospitalType(str, Enum):
    phc = "phc"
    government = "government"
    private = "private"


class ClaimInput(BaseModel):
    patient_id: str
    visit_date: date
    service_type: str  # e.g., 'OPD', 'ER', 'IPD'
    service_code: Optional[str] = None
    claim_code: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doctor_nmc: Optional[str] = None
    diagnosis: Diagnosis
    claimable_items: List[ClaimableItem]
    hospital_type: HospitalType = Field(..., description="Type of health facility (phc, government, private)")
    enterer_reference: Optional[str] = None  # who is entering the claim
    facility_reference: Optional[str] = None  # health facility code

    @validator("service_type", pre=True)
    def normalize_service_type(cls, v):
        if isinstance(v, str):
            return v.upper().strip()  # service types appear coded, so using upper
        return v

    @validator("hospital_type", pre=True)
    def normalize_hospital_type(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v


class ClaimResponse(BaseModel):
    is_locally_valid: bool
    warnings: List[str]
    items: List[dict]
    total_approved_local: float
    # co_payment_applied: Optional[float] = None


class FullClaimValidationResponse(BaseModel):
    local_validation: Dict[str, Any]
    imis_patient: Dict[str, Any]
    eligibility: Dict[str, Any]
    warnings: Optional[List[str]] = []


