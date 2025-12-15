import asyncio
import re
import contextlib
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.router.claim import router as claim_router
from app.router.documents import router as documents_router
from app.tasks import prune_old_patients

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Starts the prune_old_patients task on startup and cancels it on shutdown.
    """
    task = asyncio.create_task(prune_old_patients())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Insurance Claim Validation API",
    lifespan=lifespan,
)


app.include_router(claim_router, prefix="/api")
app.include_router(documents_router, prefix="/docs")


@app.middleware("http")
async def fix_invalid_json_backslashes(request: Request, call_next):
    # Only apply to JSON requests
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        return await call_next(request)

    body = await request.body()
    if not body:
        return await call_next(request)

    try:
        raw = body.decode("utf-8")
    except UnicodeDecodeError:
        return JSONResponse(
            {"error": "Invalid UTF-8 JSON payload"},
            status_code=400,
        )


    fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)


    request._body = fixed.encode("utf-8")

    return await call_next(request)








# from fastapi import FastAPI
# from app.router.claim import router as claim_router
# from app.router.documents import router as documents
# from fastapi import Request
# from fastapi.responses import JSONResponse
# from fastapi.staticfiles import StaticFiles
# from app.tasks import prune_old_patients
# from app.insurance_database import SessionLocal
# import asyncio,re


# app = FastAPI(title="Insurance Claim Validation API")
# app.include_router(claim_router, prefix="/api")
# app.include_router(documents,prefix="/docs")


# @app.middleware("http")
# async def fix_invalid_json_backslashes(request: Request, call_next):
#     if request.headers.get("content-type") != "application/json":
#         return await call_next(request)

#     body = await request.body()
#     raw = body.decode("utf-8")
#     fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)

#     try:
#         request._body = fixed.encode("utf-8")
#     except Exception as e:
#         return JSONResponse({"error": "Failed to repair JSON", "details": str(e)}, status_code=400)

#     return await call_next(request)


# @app.on_event("startup")
# async def startup_event():
#     db = SessionLocal()
#     asyncio.create_task(prune_old_patients())







# 

# from fastapi import FastAPI, Request
# from fastapi.responses import JSONResponse
# from contextlib import asynccontextmanager
# import asyncio
# import re

# from app.router.claim import router as claim_router
# from app.router.documents import router as documents_router
# from app.insurance_database import SessionLocal
# from app.tasks import prune_old_patients


# # -----------------------------
# # Background task (safe DB use)
# # -----------------------------
# async def prune_old_patients_task():
#     """
#     Periodically prune old patients.
#     Each run creates and closes its own DB session
#     to avoid connection leaks.
#     """
#     while True:
#         db = SessionLocal()
#         try:
#             await prune_old_patients(db)
#         finally:
#             db.close()
#         # Run every hour (adjust as needed)
#         await asyncio.sleep(60 * 60)


# # -----------------------------
# # Lifespan handler (startup / shutdown)
# # -----------------------------
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # STARTUP
#     asyncio.create_task(prune_old_patients_task())
#     yield
#     # SHUTDOWN (nothing to clean up for now)


# # -----------------------------
# # App initialization
# # -----------------------------
# app = FastAPI(
#     title="Insurance Claim Validation API",
#     lifespan=lifespan,
# )

# app.include_router(claim_router, prefix="/api")
# app.include_router(documents_router, prefix="/docs")


# # -----------------------------
# # Middleware: fix malformed JSON
# # (restricted to claim endpoints only)
# # -----------------------------
# @app.middleware("http")
# async def fix_invalid_json_backslashes(request: Request, call_next):
#     # Only apply to claim-related endpoints
#     if not request.url.path.startswith("/api"):
#         return await call_next(request)

#     content_type = request.headers.get("content-type", "")
#     if "application/json" not in content_type:
#         return await call_next(request)

#     body = await request.body()
#     if not body:
#         return await call_next(request)

#     try:
#         raw = body.decode("utf-8")
#     except UnicodeDecodeError:
#         return JSONResponse(
#             {"error": "Invalid UTF-8 JSON payload"},
#             status_code=400,
#         )

#     # Fix invalid backslashes only
#     fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)

#     # Override request body (Starlette internal API)
#     request._body = fixed.encode("utf-8")

#     return await call_next(request)
