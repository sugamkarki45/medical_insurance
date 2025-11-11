import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data"

def load_json(file_name):
    file_path = DATA_PATH / file_name
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_rules():
    return load_json("validation_rules.json")

def get_med(item_code: str):
    meds = load_json("claimable_medicines.json")
    for med in meds:
        if med["code"] == item_code:
            return med
    return None

def get_package(item_code: str):
    packages = load_json("packages.json")
    for pkg in packages:
        if pkg["code"] == item_code:
            return pkg
    return None
