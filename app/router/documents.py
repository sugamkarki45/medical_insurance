from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from insurance_database import get_db, ClaimDocument, ImisResponse
from pydantic import BaseModel
from typing import List

router = APIRouter(tags=["Document Management"])

class DocumentInput(BaseModel):
    file_url: str
    original_filename: str | None = None
    document_type: str = "general"

@router.post("/add_document_links/{claim_id}")
async def add_document_links(
    claim_id: str,
    documents: List[DocumentInput],
    db: Session = Depends(get_db)
):
    claim = db.query(ImisResponse).filter(ImisResponse.claim_id == claim_id).first()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    saved_docs = []

    for doc_data in documents:
        doc = ClaimDocument(
            claim_id=claim_id,
            file_url=doc_data.file_url,
            original_filename=doc_data.original_filename,
            document_type=doc_data.document_type,
            file_size=None 
        )
        db.add(doc)
        db.flush()

        saved_docs.append({
            "document_id": doc.id,
            "file_url": doc.file_url,
            "original_filename": doc.original_filename,
            "document_type": doc.document_type
        })

    db.commit()

    return {
        "message": "Document links stored successfully",
        "claim_id": claim_id,
        "documents": saved_docs
    }


#endpoint to delete the uploaded files
# @router.delete("/document/{document_id}")
# async def delete_document(
#     document_id: int,
#     db: Session = Depends(get_db)
# ):
#     doc = db.query(ImisResponse).filter(ClaimDocument.id == document_id).first()
#     if not doc:
#         raise HTTPException(status_code=404, detail="Document not found")

# #here we restrict only the authorized ho
#     claim = doc.claim
#     if claim.facility_id != current_user.facility_id:
#         raise HTTPException(status_code=403, detail="Not authorized")

#     try:
#         file_path = doc.file_url.replace(f"{BASE_URL}/uploads/", os.path.join(UPLOAD_DIR, ""))
#         if os.path.exists(file_path):
#             os.remove(file_path)
#     except Exception as e:
#         print(f"Failed to delete file from disk: {e}")


#     db.delete(doc)
#     db.commit()

#     return {
#         "message": "Document deleted successfully",
#         "document_id": document_id,
#         "file_url": doc.file_url
#     }
