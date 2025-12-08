import os
from fastapi import Header, HTTPException

# Load keys from environment
VALID_API_KEYS = set(os.getenv("MY_API_KEYS", "").split(","))

def get_api_key(api_key: str = Header(...)):
    if api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
