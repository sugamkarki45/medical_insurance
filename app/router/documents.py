from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from insurance_database import Claim, get_db, ClaimDocument
import uuid,os
from typing import List



router = APIRouter(tags=["Document Management"])
UPLOAD_DIR = "uploads/claim_upload/"
BASE_URL = "https://ourdomaintostorethefiles.com/uploads/claims/"
@router.post("/upload_documents/{claim_id}")
async def upload_multiple_documents(
    claim_id: str,
    files: List[UploadFile] = File(..., description="Multiple files allowed (max 10)"),
    db: Session = Depends(get_db)
):
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files allowed at once")

    claim = db.query(Claim).filter(Claim.claim_id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    claim_folder = os.path.join(UPLOAD_DIR, claim_id)
    os.makedirs(claim_folder, exist_ok=True)

    uploaded_docs = []

    for file in files:
        if file.size == 0:
            continue  
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "file"
        if ext not in {"pdf", "jpg", "jpeg", "png", "doc", "docx"}:
            raise HTTPException(status_code=400, detail=f"File type not allowed: {file.filename}")

        filename = f"{uuid.uuid4()}.{ext}"
        file_path = os.path.join(claim_folder, filename)

        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        file_url = f"{BASE_URL}/uploads/{claim_id}/{filename}"

        doc = ClaimDocument(
            claim_id=claim_id,
            file_url=file_url,
            original_filename=file.filename,
            document_type="general",
            file_size=len(contents)
        )
        db.add(doc)
        uploaded_docs.append({
            "document_id": doc.id,
            "file_url": file.filename,
            "file_url": file_url
        })

    db.commit()

    for doc in uploaded_docs:
        db.refresh(db.query(ClaimDocument).filter(ClaimDocument.id == doc["document_id"]).first())

    return {
        "message": f"{len(uploaded_docs)} document(s) uploaded successfully",
        "claim_id": claim_id,
        "documents": uploaded_docs
    }

#endpoint to delete the uploaded files
@router.delete("/document/{document_id}")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    doc = db.query(ClaimDocument).filter(ClaimDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Optional: restrict deletion to same hospital/user
    # claim = doc.claim
    # if claim.facility_id != current_user.facility_id:
    #     raise HTTPException(status_code=403, detail="Not authorized")

    try:
        file_path = doc.file_url.replace(f"{BASE_URL}/uploads/", os.path.join(UPLOAD_DIR, ""))
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"Failed to delete file from disk: {e}")


    db.delete(doc)
    db.commit()

    return {
        "message": "Document deleted successfully",
        "document_id": document_id,
        "file_url": doc.file_url
    }
