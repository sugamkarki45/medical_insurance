import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from insurance_database import SessionLocal,PatientInformation

async def prune_old_patients(db: Session):
    while True:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        old_records = db.query(PatientInformation).filter(PatientInformation.created_at < cutoff).all()
        for record in old_records:
            db.delete(record)
        db.commit()
        await asyncio.sleep(3600)  
