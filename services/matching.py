"""Explainable, deterministic topic relevance. NOT eligibility or award likelihood."""
import re
from services.verified_goals import VERIFIED_GOALS


def _tokens(value):
    return set(re.findall(r"[a-z0-9]+", str(value).lower()))


def rank_grants(grants, agency_name):
    """Return results in descending relevance; unverified agencies get no score."""
    profile = VERIFIED_GOALS.get(agency_name)
    results = []
    for grant in grants:
        row = dict(grant)
        row["eligibility_status"] = "Needs Review"
        row["match_score"] = None
        row["match_reasons"] = []
        row["plan_url"] = profile["plan_url"] if profile else None
        row["plan_verified"] = bool(profile)
        if profile:
            title = str(row.get("title") or "")
            description = str(row.get("synopsis") or row.get("description") or "")
            text = f"{title} {description}".lower()
            tokens = _tokens(text)
            matched = []
            for goal in profile["goals"]:
                found = [term for term in goal["terms"] if
                         (term in text if " " in term else term in tokens)]
                if found:
                    matched.append({"goal": goal["text"], "page": goal["page"], "keywords": found})
            # A conservative topic-overlap heuristic; no false precision about
            # likelihood of award, and no claims of eligibility.
            row["match_score"] = min(100, round(100 * len(matched) / len(profile["goals"])))
            row["match_reasons"] = matched
        results.append(row)
    return sorted(results, key=lambda r: (r["match_score"] is not None, r["match_score"] or 0), reverse=True)
