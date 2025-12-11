import json
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parent / "data"


_cached_rules = None

_cached_meds_list = None
_cached_meds_map = None

_cached_packages_list = None
_cached_packages_map = None



def load_json(file_name: str):
    file_path = DATA_PATH / file_name
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_rules():
    """Load validation_rules.json once and return it."""
    global _cached_rules
    if _cached_rules is None:
        _cached_rules = load_json("validation_rules.json")
    return _cached_rules



def get_all_items():
    """Load large medicine list once."""
    global _cached_meds_list, _cached_meds_map
    if _cached_meds_list is None:
        _cached_meds_list = load_json("items.json")
        # Convert to dict for fast lookup
        _cached_meds_map = {str(m["code"]): m for m in _cached_meds_list}
    return _cached_meds_list


def get_items(item_code: str):
    """O(1) fast lookup of a medicine by code."""
    if _cached_meds_map is None:
        get_all_items()  # initialize cache
    return _cached_meds_map.get(str(item_code))



def get_all_services():

    global _cached_packages_list, _cached_packages_map
    if _cached_packages_list is None:
        _cached_packages_list = load_json("services.json")
        _cached_packages_map = {str(p["code"]): p for p in _cached_packages_list}
    return _cached_packages_list


def get_services(item_code: str):

    if _cached_packages_map is None:
        get_all_services()  # initialize cache
    return _cached_packages_map.get(str(item_code))






# import json
# from pathlib import Path

# DATA_PATH = Path(__file__).resolve().parent / "data"

# def load_json(file_name):
#     file_path = DATA_PATH / file_name
#     with open(file_path, "r", encoding="utf-8") as f:
#         return json.load(f)

# def get_rules():
#     return load_json("validation_rules.json")

# def get_med(item_code: str):
#     meds = load_json("claimable_medicines.json")
#     for med in meds:
#         if med["code"] == item_code:
#             return med
#     return None

# def get_package(item_code: str):
#     packages = load_json("packages.json")
#     for pkg in packages:
#         if pkg["code"] == item_code:
#             return pkg
#     return None

# def get_all_medicines():
#     rules = load_json("claimable_medicines.json")        
#     return rules

# def get_all_packages():
#     rules = load_json("packages.json")
#     return rules

