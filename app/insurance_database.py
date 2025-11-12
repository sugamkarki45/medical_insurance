from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    Date, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session

Base = declarative_base()

#patient table
class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    patient_code = Column(String, unique=True, nullable=False)
    # name = Column(String, nullable=False)
    # dob = Column(Date)
    # gender = Column(String)
    # phone = Column(String)
    # address = Column(String)

    # Store IMIS fetched info
    imis_info = Column(JSON, nullable=True)
    eligibility = Column(JSON, nullable=True)

    claims = relationship("Claim", back_populates="patient")
    imis_responses = relationship("ImisResponse", back_populates="patient")

#hospital table
class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # 'phc', 'government', 'private'
    address = Column(String)
    contact_number = Column(String)

    claims = relationship("Claim", back_populates="hospital")


# prevalidation result table
class PrevalidationResult(Base):
    __tablename__ = "prevalidation_results"
    id = Column(Integer, primary_key=True, index=True)
    claim_id = Column(Integer, ForeignKey("claims.id"))
    result = Column(JSON)
    created_at = Column(Date, nullable=False)

    claim = relationship("Claim")


 
# Claim Table
class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    claim_code = Column(String, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    hospital_id = Column(Integer, ForeignKey("hospitals.id"))
    amount_claimed = Column(Float, nullable=False)
    status = Column(String, default="pending")  # e.g., pending/approved/rejected
    claim_date = Column(Date)

    # Relationships
    patient = relationship("Patient", back_populates="claims")
    hospital = relationship("Hospital", back_populates="claims")


class ImisResponse(Base):
    __tablename__ = "imis_responses"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    response_type = Column(String)  # 'info' or 'eligibility'
    response_data = Column(JSON)
    fetched_at = Column(Date)

    patient = relationship("Patient", back_populates="imis_responses")




# Engine & Session
engine = create_engine("sqlite:///insurance_database.db", echo=True)
SessionLocal = sessionmaker(autocommit=False,autoflush=False, bind=engine)
session = SessionLocal()
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# Create all tables
Base.metadata.create_all(engine)
