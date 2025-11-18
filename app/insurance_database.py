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
    #  other eligibility logic
    eligibility = Column(JSON, nullable=True)

    # Relationships
    claims = relationship("Claim", back_populates="patient")
    imis_responses = relationship("ImisResponse", back_populates="patient")
    eligibility_cache = relationship("EligibilityCache", uselist=False, back_populates="Patient")



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
    patient_uuid = Column(String, ForeignKey("patients.patient_uuid"), index=True)
    response = Column(JSON, nullable=False)
    checked_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="eligibility_cache")


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    opd_code = Column(String, nullable=True)  # for OPD claims need to save this as well from previous calims
    claim_code = Column(String, nullable=False, unique=True)
    patient_id = Column(Integer,ForeignKey("patients.id"), nullable=False)  # store IMIS patient ID
    amount_claimed = Column(Float, nullable=False)
    claim_date = Column(Date)
    status = Column(String, default="draft")  # draft, pending, approved, rejected
    prevalidation_result = Column(JSON, nullable=True)  # warnings, approved items
    imis_validation_result = Column(JSON, nullable=True)  # full IMIS response
    # Relationships
    patient = relationship("Patient", back_populates="claims")



class ImisResponse(Base):
    __tablename__ = "imis_responses"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    response_type = Column(String)  # 'info' or 'eligibility'
    response_data = Column(JSON)
    fetched_at = Column(Date)


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
