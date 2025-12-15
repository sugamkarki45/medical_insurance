from dotenv import load_dotenv
import os

# Load .env into environment variables
load_dotenv()

def get_valid_api_keys() -> set[str]:
    keys = os.getenv("MY_API_KEYS", "")
    return {k.strip() for k in keys.split(",") if k.strip()}
