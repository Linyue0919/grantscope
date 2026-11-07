"""NC agency profiles built from official OSBM-listed strategic plans.

Data lives in data/agency_strategic_plans.json. Every goal is a verbatim quote
with its PDF page; see that file's "method" field and
scripts/verify_agency_plans.py. Agencies whose goals have not been extracted
are listed separately and are never given invented goals.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "agency_strategic_plans.json"


@lru_cache(maxsize=1)
def load_plan_data(path=None):
    with open(path or DATA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def list_profiled_agencies():
    return [agency["name"] for agency in load_plan_data()["agencies"]]


def list_unprofiled_agencies():
    return list(load_plan_data().get("unprofiled_agencies", []))


def _canonical(name):
    text = str(name or "").strip().lower()
    text = re.sub(r"^(nc|n\.c\.|north carolina)\s+", "", text)
    return re.sub(r"\s+", " ", text)


def resolve_agency_name(name):
    """Map labels such as 'NC Department of Transportation' to a profiled name."""
    wanted = _canonical(name)
    for agency in load_plan_data()["agencies"]:
        if wanted in {_canonical(agency["name"]), agency["short_name"].lower()}:
            return agency["name"]
    return None


def get_agency_profile(name):
    """Return the profile dict for a profiled agency, or None."""
    resolved = resolve_agency_name(name)
    for agency in load_plan_data()["agencies"]:
        if agency["name"] == resolved:
            return agency
    return None


def find_unprofiled_plan(name):
    """Return the official plan link for an agency that is not yet profiled."""
    wanted = _canonical(name)
    for entry in list_unprofiled_agencies():
        if _canonical(entry["name"]) == wanted:
            return entry
    return None
