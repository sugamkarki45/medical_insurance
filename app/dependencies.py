# app/dependencies.py
from fastapi import Header, HTTPException, status
from app.config import get_valid_api_keys
import logging

logger = logging.getLogger("X-API-Key")

def get_api_key(api_key: str = Header(..., alias="X-API-Key")) -> str:
    valid_keys = get_valid_api_keys()
    if api_key not in valid_keys:
        logger.warning("Unauthorized API access attempt: %s", api_key)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    return api_key
