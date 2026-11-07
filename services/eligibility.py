"""Conservative evidence-based screening; not legal eligibility determination."""
import re


def screen_eligibility(details, agency_name):
    """Only classify clear exclusion patterns; otherwise require human review."""
    notes = str(details.get("eligibility_description") or "")
    types = " ".join(details.get("applicant_types") or [])
    combined = (notes + " " + types).lower()
    if not notes.strip() and not types.strip():
        return {"status": "Needs Review", "reason": "No applicant eligibility information returned."}

    # Explicit exclusive institute-only applicant language from official details.
    institute_only = re.search(
        r"\bonly\s+water\s+resources\s+research\s+institutes\b.{0,120}?\b(?:eligible|may apply|can apply)\b",
        notes, re.IGNORECASE | re.DOTALL,
    )
    if institute_only and agency_name == "Department of Environmental Quality":
        return {
            "status": "Ineligible",
            "reason": "Official rules limit direct applicants to Water Resources Research Institutes; the selected agency is NC DEQ.",
            "evidence": institute_only.group(0).strip(),
        }
    return {
        "status": "Needs Review",
        "reason": "Applicant categories and notes require agency-specific human verification.",
    }
