from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    Date, ForeignKey, JSON
)
from sqlalchemy.types import DateTime
from datetime import datetime
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    patient_code = Column(String, unique=True, nullable=False)
    last_visit_date = Column(Date, nullable=True)
    patient_uuid = Column(String, unique=True, nullable=True)

    # Full IMIS Bundle (JSON)
    imis_full_response = Column(JSON, nullable=True)

    # Extracted patient resource from IMIS
    imis_core_resource = Column(JSON, nullable=True)

    # Copayment
    Copayment=Column(JSON, nullable=True)

    # Relationships
    claims = relationship("Claim", back_populates="patient")
    imis_responses = relationship("ImisResponse", back_populates="patient")
    eligibility_cache = relationship("EligibilityCache", uselist=False, back_populates="patient")



class PrevalidationResult(Base):
    __tablename__ = "prevalidation_results"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"))
    result = Column(JSON)
    created_at = Column(Date, nullable=False)

#relationship
    claim = relationship("Claim")


class EligibilityCache(Base):
    __tablename__ = "eligibility_cache"


    id = Column(Integer, primary_key=True, index=True)

    # Link to patient (via UUID because IMIS uses UUID)
    patient_uuid = Column(String, ForeignKey("patients.patient_uuid"), index=True)

    # Extracted values
    category = Column(String, nullable=True)  # e.g., "OPD", "IPD"
    allowed_money = Column(Float, nullable=True)
    used_money = Column(Float, nullable=True)

    policy_id = Column(String, nullable=True)
    policy_expiry = Column(Date, nullable=True)

    # Full raw IMIS response for future audits
    raw_response = Column(JSON, nullable=False)

    checked_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="eligibility_cache")





class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    service_code = Column(String, nullable=True)  # for OPD claims need to save this as well from previous calims
    claim_code = Column(String, nullable=False)
    patient_id = Column(Integer,ForeignKey("patients.id"), nullable=False)  # store IMIS patient ID
    amount_claimed = Column(Float, nullable=False)
    claim_date = Column(Date)
    status = Column(String, default="draft")  # draft, pending, approved, rejected
    prevalidation_result = Column(JSON, nullable=True) 
    enterer_reference = Column(String, nullable=True)  # who entered the claim
    facility_reference = Column(String, nullable=True)  # health facility code
    
    # Relationships
    patient = relationship("Patient", back_populates="claims")



class ImisResponse(Base):
    __tablename__ = "imis_responses"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    raw_response = Column(JSON)
    fetched_at = Column(DateTime, default=datetime.utcnow)


#relationship
    patient = relationship("Patient", back_populates="imis_responses")


#engine and sessions
engine = create_engine("sqlite:///insurance_database.db", echo=True)
SessionLocal = sessionmaker(autocommit=False,autoflush=False, bind=engine)
session = SessionLocal()
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


#to create tables
Base.metadata.create_all(engine)
