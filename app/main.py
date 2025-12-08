from fastapi import FastAPI
from router.claim import router as claim_router
from router.documents import router as documents
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from tasks import prune_old_patients
from insurance_database import SessionLocal
import asyncio,re


app = FastAPI(title="Insurance Claim Validation API")
# app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.include_router(claim_router, prefix="/api")
app.include_router(documents,prefix="/docs")

#to handle invalid backslashes in JSON input
@app.middleware("http")
async def fix_invalid_json_backslashes(request: Request, call_next):
    if request.headers.get("content-type") != "application/json":
        return await call_next(request)

    body = await request.body()
    raw = body.decode("utf-8")

    fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)

    try:
        request._body = fixed.encode("utf-8")
    except Exception as e:
        return JSONResponse({"error": "Failed to repair JSON", "details": str(e)}, status_code=400)

    return await call_next(request)




@app.on_event("startup")
async def startup_event():
    db = SessionLocal()
    asyncio.create_task(prune_old_patients(db))
