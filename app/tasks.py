import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.insurance_database import SessionLocal,PatientInformation

async def prune_old_patients():
    while True:
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            db.query(PatientInformation)\
              .filter(PatientInformation.created_at < cutoff)\
              .delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        await asyncio.sleep(3600)
