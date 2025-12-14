import json
from pathlib import Path
from fastapi.responses import Response

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


_cached_items_response = None
_cached_services_response = None


def get_items_response():
    global _cached_items_response
    if _cached_items_response is None:
        data = get_all_items()
        payload = {
            "count": len(data),
            "medicines": data
        }
        _cached_items_response = Response(
            content=json.dumps(payload),
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=3600"}
        )
    return _cached_items_response


def get_services_response():
    global _cached_services_response
    if _cached_services_response is None:
        data = get_all_services()
        payload = {
            "count": len(data),
            "packages": data
        }
        _cached_services_response = Response(
            content=json.dumps(payload),
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=3600"}
        )
    return _cached_services_response
