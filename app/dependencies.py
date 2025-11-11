from fastapi import Header, HTTPException

def get_api_key(api_key: str = Header(...)):
    if not api_key or api_key != "fNJOr4X6ADJUobFyWoNsjWoaGGk7Pja4XegwtQZ4c6c": 
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key