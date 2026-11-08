"""Presentation-only grouping of opportunities into brief sections.

Reads only OpportunityView fields; never changes scores or order. Thresholds are
provisional and kept here so they can be tuned with the backend owner. Tier names
match the backend's levels (Strong / Moderate / Low).
"""

SECTION_RULES = {
    "strong_min": 60,      # backend "strong" level
    "moderate_min": 30,    # backend "moderate" level; below this is Low
    "top_min_fit": 30,     # Moderate fits reach Top only with a stated award; Strong fits don't need one
    "top_cap": 5,          # Top shows at most this many before "Show N more"
    "lower_cap": 15,       # Lower priority shows at most this many rows
}
SECTIONS = ("top", "check", "soon", "lower")
SECTION_TITLES = {
    "top": "Top candidates",
    "check": "Needs a quick check",
    "soon": "Opening soon",
    "lower": "Lower priority",
}
SECTION_DESCRIPTIONS = {
    "top": ("Strong fit with your plan (or a good fit with a stated award), state governments listed as eligible "
            "applicants, and a known deadline. Sorted by fit score."),
    "check": ("Good fit, but something important isn't confirmed yet, so the score alone isn't enough. "
              "Each one names exactly what to check."),
    "soon": "Forecasted opportunities that aren't accepting applications yet.",
    "lower": "mostly indirect fit or a known blocker",
}


def fit_tier(score):
    """Backend level names: Strong >= 60, Moderate 30-59, Low < 30 (or unscored)."""
    if score is None:
        return "Low"
    if score >= SECTION_RULES["strong_min"]:
        return "Strong"
    if score >= SECTION_RULES["moderate_min"]:
        return "Moderate"
    return "Low"


def assign_section(view):
    """Return "top" | "check" | "soon" | "lower". Missing information can lower, never raise."""
    if view.status == "forecasted" or view.backend_section == "upcoming":
        return "soon"
    if (view.backend_section in ("likely_ineligible", "low_evidence", "screened_out")
            or view.fit_score is None or view.fit_score < SECTION_RULES["moderate_min"]
            or view.known_blocker):
        return "lower"
    if (view.eligibility_restricted or not view.eligibility_positive or view.region_flags
            or view.deadline_date is None):
        return "check"
    if view.fit_score >= SECTION_RULES["strong_min"]:
        return "top"  # Strong fit: an unstated award is shown as "Not stated", not a reason to hold back
    if view.fit_score >= SECTION_RULES["top_min_fit"] and view.award_status == "Confirmed":
        return "top"  # Moderate fit needs a stated award
    return "check"


def group_views(views, hidden_ids=()):
    """Split views into sections, preserving the incoming (backend) order within each."""
    groups = {name: [] for name in SECTIONS}
    for view in views:
        groups[view.section].append(view)
    return groups
