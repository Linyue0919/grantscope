"""Conservative evidence-based screening; not legal eligibility determination."""
import re


def screen_eligibility(details, agency_name):
    """Only classify clear exclusion patterns; otherwise require human review."""
    notes = str(details.get("eligibility_description") or "")
    types = " ".join(details.get("applicant_types") or [])
    description = str(details.get("description") or "")
    if not notes.strip() and not types.strip() and not description.strip():
        return {"status": "Needs Review", "reason": "No applicant eligibility information returned."}

    # Observed NSF exclusive applicant list: NC state departments are neither
    # an IHE nor one of the specified non-academic nonprofit organizations.
    nsf_only = re.search(
        r"proposals may only be submitted by the following:.{0,600}?"
        r"non-profit, non-academic organizations:.{0,600}?"
        r"institutions of higher education", notes, re.IGNORECASE | re.DOTALL,
    )
    if (nsf_only and agency_name.startswith("Department of ")
            and not re.search(r"(?:state|local|county|city) governments?", notes, re.IGNORECASE)):
        return {"status": "Ineligible",
                "reason": "Official exclusive applicant list permits specified nonprofits and higher education institutions, not the selected NC state department as direct applicant. A partnership route requires separate verification.",
                "evidence": nsf_only.group(0).strip()}

    # Narrow evidence rule for the observed EPA tribal-only opportunity.
    # Do not infer exclusions from titles or incidental mentions of Tribes.
    official_text = " ".join((notes, description))
    tribal_clause = re.search(
        r"\beligible applicants\b.{0,160}?\b(?:federally recognized|eligible)\s+tribes\b"
        r".{0,100}?\b(?:intertribal consortia|tribal consortia)\b",
        official_text, re.IGNORECASE | re.DOTALL,
    )
    if tribal_clause and agency_name == "Department of Environmental Quality":
        return {
            "status": "Ineligible",
            "reason": (
                "Official applicant language restricts direct applications to "
                "Tribes and tribal consortia; NC DEQ is not among those categories. "
                "Verify the complete NOFO before any decision."
            ),
            "evidence": tribal_clause.group(0).strip(),
        }

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
