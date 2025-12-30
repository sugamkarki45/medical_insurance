from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any,Literal
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
    lab_test = "lab"
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
    category:str=Field(..., description="Enter the category of the item i.e item or service")

    @field_validator("type" )
    def normalize_item_type(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v
    
    @field_validator("item_code", "name" )
    def normalize_strings(cls, v):
        if isinstance(v, str):
            return v.upper().strip()
        return v
    @field_validator("category" )
    def normalize_category(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v


class Diagnosis(BaseModel):
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
    service_type: Literal['OPD','IPD','ER','Referral']
    service_code: Optional[str] = None
    doctor_nmc: Optional[str] = None
    diagnosis: Diagnosis
    icd_codes: List[str] = Field(default_factory=list,min_length=1)
    claimable_items: List[ClaimableItem]
    hospital_type: HospitalType = Field(..., description="Type of health facility (phc, government, private)")
    enterer_reference: Optional[str] = None  # who is entering the claim
    facility_reference: Optional[str] = None  # health facility code
    claim_time: Optional[str] = Field(..., description="Enter the time of claim: discharge,same day")# e.g., 'discharge', 'same_day', etc.
    claim_code:Optional[str]
    department:Optional[str]=Field(..., description="this is optional as so but in case of OPD this is required as the inter departmental consuntation shall be checked.")

    @field_validator("service_type" )
    def normalize_service_type(cls, v):
        if isinstance(v, str):
            return v.upper().strip() 
        return v

    @field_validator("hospital_type" )
    def normalize_hospital_type(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v


class LocalValidation(BaseModel):
    is_locally_valid: bool
    warnings: list
    items: list
    total_approved_local: float
    total_copay: float
    net_claimable: float
    allowed_money: float
    used_money: float
    available_money: float

class ClaimResponse(BaseModel):
    claim_code: str
    status: str
    local_validation: LocalValidation


class FullClaimValidationResponse(BaseModel):
    local_validation: Dict[str, Any]
    imis_patient: Dict[str, Any]
    eligibility: Dict[str, Any]
    # claim_id:str
    # claim_code:str


class PatientInfo(BaseModel):
    imis_patient: Dict[str, Any]
    eligibility: Dict[str, Any]




class LoginInput(BaseModel):
    username: str
    password: str

class PatientFullInfoRequest(BaseModel):
    patient_identifier: str
    username: str
    password: str