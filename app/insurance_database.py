from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    Date, ForeignKey, JSON
)
import uuid
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
    copayment=Column(JSON, nullable=True)

    # Relationships
    claims = relationship("Claim", back_populates="patient")
    imis_responses = relationship("ImisResponse", back_populates="patient")
    eligibility_cache = relationship("EligibilityCache", uselist=False, back_populates="patient")



class EligibilityCache(Base):
    __tablename__ = "eligibility_cache"

    id = Column(Integer, primary_key=True, index=True)
    patient_uuid = Column(String, ForeignKey("patients.patient_uuid", ondelete="CASCADE"), index=True)
    category = Column(String, nullable=True)  # e.g., "OPD", "IPD"
    allowed_money = Column(Float, nullable=True)
    used_money = Column(Float, nullable=True)
    policy_id = Column(String, nullable=True)
    policy_expiry = Column(Date, nullable=True)
    raw_response = Column(JSON, nullable=False)
    checked_at = Column(DateTime, default=datetime.utcnow)
    patient = relationship("Patient", back_populates="eligibility_cache")





class Claim(Base):
    __tablename__ = "claims"
    claim_id = Column(Integer, primary_key=True, index=True)
    claim_code = Column(String(11),nullable=False,index=True)
    icd_codes = Column(String, nullable=False)
    doctor_nmc = Column(String, nullable=True)
    service_type = Column(String, nullable=False)
    service_code = Column(String, nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    amount_claimed = Column(Float, nullable=False)
    claim_date = Column(Date)
    item_code=Column(JSON)
    status = Column(String, default="draft")
    prevalidation_result = Column(JSON, nullable=True)
    enterer_reference = Column(String, nullable=True)
    facility_reference = Column(String, nullable=True)
    
    # Relationships
    patient = relationship("Patient", back_populates="claims")

class ImisResponse(Base):
    __tablename__ = "imis_responses"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"))
    raw_response = Column(JSON)
    fetched_at = Column(DateTime, default=datetime.utcnow)


#relationship
    patient = relationship("Patient", back_populates="imis_responses")

class IMISSession(Base):
    __tablename__ = "imis_sessions"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)  
    session_cookie = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)


class ClaimDocument(Base):
    __tablename__ = "claim_documents"

    id = Column(Integer, primary_key=True)
    claim_id = Column(String, index=True)
    file_url = Column(String)
    document_type = Column(String) 

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
