"""NC OSBM agency strategic-plan directory snapshot.

Source: https://www.osbm.nc.gov/operational-excellence/strategic-planning/agency-strategic-plans
Names are transcribed from the official directory. These are directory entries,
NOT extracted strategic goals or proof of grant eligibility.
"""
SOURCE_URL = "https://www.osbm.nc.gov/operational-excellence/strategic-planning/agency-strategic-plans"
AGENCY_BY_AREA = {
    "Education": [
        "Department of Public Schools",
        "State Board of Education",
        "NC Community College System",
        "University of North Carolina System",
    ],
    "General Government": [
        "Office of State Budget and Management",
        "Department of Information Technology",
        "NC Housing Finance Agency",
        "Department of Military and Veterans Affairs",
        "Office of State Human Resources",
        "Department of Secretary of State",
        "Office of the State Auditor",
        "Department of State Treasurer",
        "Department of Insurance",
        "Office of State Fire Marshal",
        "Department of Administration",
        "Office of the State Controller",
        "Department of Revenue",
        "State Board of Elections",
        "Office of Administrative Hearings",
    ],
    "Health and Human Services": [
        "Department of Health and Human Services",
    ],
    "Justice and Public Safety": [
        "Judicial Branch - Indigent Defense",
        "Department of Adult Correction",
        "Department of Justice",
        "Department of Public Safety",
        "State Bureau of Investigation",
        "State Highway Patrol",
    ],
    "Natural and Economic Resources": [
        "Department of Agriculture and Consumer Services",
        "Department of Labor",
        "Department of Natural and Cultural Resources",
        "Department of Environmental Quality",
        "Wildlife Resources Commission",
        "Department of Commerce",
    ],
    "Transportation": [
        "Department of Transportation",
    ],
}
AGENCIES = [name for names in AGENCY_BY_AREA.values() for name in names]
assert len(AGENCIES) == len(set(AGENCIES)) == 33


def get_agency_directory():
    """Return records in a stable schema shared by Search and Dashboard."""
    return [
        {
            "agency_id": name.lower().replace(" ", "-"),
            "name": name,
            "policy_area": area,
            "directory_source_url": SOURCE_URL,
            "strategic_goals": [],  # Must be populated from the actual plan.
            "strategic_goals_verified": False,
        }
        for area, names in AGENCY_BY_AREA.items()
        for name in names
    ]
