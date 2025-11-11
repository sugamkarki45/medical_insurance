from fastapi import FastAPI
from pydantic import BaseModel
from router.claim import router as claim_router

app = FastAPI(title="Insurance Claim Validation API")

app.include_router(claim_router, prefix="/api")