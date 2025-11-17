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
    remaining_balance: float = Field(..., description="Remaining insurance balance")
    visit_date: date
    service_type: str  # e.g., 'OPD', 'ER', 'IPD'
    opd_code: Optional[str] = None
    claim_code: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doctor_nmc: Optional[str] = None
    diagnosis: Diagnosis
    claimable_items: List[ClaimableItem]
    hospital_type: HospitalType = Field(..., description="Type of health facility (phc, government, private)")
    # referral_slip_code: Optional[str] = None
    # first_service_point: Optional[str] = None

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
    co_payment_applied: Optional[float] = None


class FullClaimValidationResponse(BaseModel):
    local_validation: Dict[str, Any]
    imis_patient: Dict[str, Any]
    eligibility: Dict[str, Any]
    warnings: Optional[List[str]] = []



# from pydantic import BaseModel, Field
# from typing import List, Optional,Dict, Any
# from datetime import date
# import uuid
# from enum import Enum

# class PatientCategory(str, Enum):
#     general = "general"
#     poor = "poor"
#     ultra_poor = "ultra_poor"
#     fchv = "fchv"
#     hiv_aids = "hiv_aids"
#     severe_tb = "severe_tb"
#     severe_disability = "severe_disability"
#     leprosy = "leprosy"

# class ItemType(str, Enum):
#     medicine = "medicine"
#     lab_test = "lab_test"
#     surgery = "surgery"  
#     procedure = "procedure"
#     diagnostic_imaging = "diagnostic_imaging"
#     other = "other"

# class ClaimableItem(BaseModel):
#     type: ItemType = Field(..., description="Type of item (medicine, lab_test, surgery, etc.)")
#     item_code: str
#     quantity: int = 1
#     cost: float
#     name: str

# class Diagnosis(BaseModel):
#     icd_code: str
#     provisional: Optional[str] = None
#     differential: Optional[str] = None
#     final: Optional[str] = None
#     is_chronic: bool = False

# # Enum for health facility types
# class HospitalType(str, Enum):
#     phc = "phc"  # Primary Health Care
#     government = "government"
#     private = "private"

# class ClaimInput(BaseModel):
#     patient_id: str
#     remaining_balance: float = Field(..., description="Remaining insurance balance")  # this will be extracted from IMIS according to patient info 
#     visit_date: date
#     service_type: str  # 'OPD', 'ER', 'IPD'
#     opd_code: Optional[str] = None
#     claim_code: str = Field(default_factory=lambda: str(uuid.uuid4()))
#     doctor_nmc: Optional[str] = None
#     diagnosis: Diagnosis
#     claimable_items: List[ClaimableItem]
#     #total_billed: float
#     hospital_type: HospitalType = Field(..., description="Type of health facility (phc, government, private)")
#     #health_record: Optional[dict] = None
#     #attachments: Optional[List[str]] = None


# class ClaimResponse(BaseModel):
#     is_locally_valid: bool
#     warnings: List[str]
#     items: List[dict]
#     total_approved_local: float
#     co_payment_applied: Optional[float] = None
#     # deductible_applied: Optional[float] = None
#     # patient_category: Optional[PatientCategory] = None



# class FullClaimValidationResponse(BaseModel):
#     local_validation: Dict[str, Any]
#     imis_patient: Dict[str, Any]
#     eligibility: Dict[str, Any]



