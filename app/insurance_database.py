from sqlalchemy import (create_engine, Column, Integer, String, Float,Date, ForeignKey, JSON,Numeric)
from sqlalchemy.types import DateTime
from datetime import datetime
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
Base = declarative_base()

class PatientInformation(Base):
    __tablename__ = "patient_information"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_code = Column(String(20), unique=True, nullable=False)
    patient_uuid = Column(String(50), nullable=False)
    name = Column(String(100))
    birth_date = Column(Date)
    gender = Column(String(10))
    copayment = Column(Numeric(10, 2), default=0)
    allowed_money = Column(Numeric(12, 2), default=0)
    used_money = Column(Numeric(12, 2), default=0)
    category = Column(String(50))
    policy_id = Column(String(50))
    policy_expiry = Column(String(20))
    imis_full_response = Column(JSON)
    eligibility_raw = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    imis_responses = relationship("ImisResponse",    cascade="all, delete-orphan",passive_deletes=True,back_populates="patient")


class ImisResponse(Base):
    __tablename__ = "imis_responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(50), ForeignKey("patient_information.patient_code",ondelete="CASCADE"), nullable=False)
    claim_code = Column(String(50), nullable=False)  
    status = Column(String(50))                   
    created_at = Column(DateTime)              
    items = Column(JSON)                        
    raw_response = Column(JSON)                     
    fetched_at = Column(DateTime, default=datetime.utcnow)
    service_type = Column(String) 
    service_code= Column(String)
    item_code=Column(JSON)
    department=Column(String)

    patient = relationship("PatientInformation", back_populates="imis_responses")


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

