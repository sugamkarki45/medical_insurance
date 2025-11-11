from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    Date, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

# -----------------------------
# Hospital Table
# -----------------------------
class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # e.g., govt/private
    address = Column(String)
    contact_number = Column(String)

    # Relationships
    claims = relationship("Claim", back_populates="hospital")


# -----------------------------
# Patient Table
# -----------------------------
class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    dob = Column(Date)
    gender = Column(String)
    phone = Column(String)
    address = Column(String)

    # Relationships
    claims = relationship("Claim", back_populates="patient")


# -----------------------------
# Benefit Package Table
# -----------------------------
class BenefitPackage(Base):
    __tablename__ = "benefit_packages"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    rules = Column(JSON)  # e.g., co-pay, limits, frequency

    # Relationships
    claims = relationship("Claim", back_populates="benefit_package")


# -----------------------------
# Claim Table
# -----------------------------
class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, index=True)
    claim_code = Column(String, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    hospital_id = Column(Integer, ForeignKey("hospitals.id"))
    package_id = Column(Integer, ForeignKey("benefit_packages.id"))
    amount_claimed = Column(Float, nullable=False)
    status = Column(String, default="pending")  # e.g., pending/approved/rejected
    claim_date = Column(Date)

    # Relationships
    patient = relationship("Patient", back_populates="claims")
    hospital = relationship("Hospital", back_populates="claims")
    benefit_package = relationship("BenefitPackage", back_populates="claims")


# -----------------------------
# Validation Rule Table (optional, if you want separate rules)
# -----------------------------
class ValidationRule(Base):
    __tablename__ = "validation_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    rule_json = Column(JSON)  # Stores detailed JSON rules
    active = Column(Boolean, default=True)

# -----------------------------
# Engine & Session
# -----------------------------
engine = create_engine("sqlite:///insurance_local.db", echo=True)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

# Create all tables
Base.metadata.create_all(engine)
