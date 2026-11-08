"""Eligibility assessment from BOTH structured applicant types and official eligibility notes.

Statuses (never "guaranteed eligible"):
  likely_eligible    Appears eligible to apply directly; still verify.
  needs_review       Unclear or conflicting evidence.
  likely_ineligible  Official text points to other applicant categories (interpretation).
  ineligible         Confirmed by an explicit official restriction (structured field or
                     an explicit "state governments are not eligible" statement).
  not_checked        Official details not loaded.

Certainty: "confirmed" (explicit official restriction), "interpretation" (reasoned
from official text by rules or validated AI), "uncertain".

An optional AI interpretation (services/ai_eligibility.py) can resolve unclear cases,
but it can never override a confirmed restriction, and when it disagrees with a
rule-based interpretation the result becomes needs_review.
"""
import re
import unicodedata

LIKELY_ELIGIBLE, NEEDS_REVIEW, LIKELY_INELIGIBLE, INELIGIBLE, NOT_CHECKED = (
    "likely_eligible", "needs_review", "likely_ineligible", "ineligible", "not_checked",
)
LABELS = {
    LIKELY_ELIGIBLE: "Appears eligible — verify",
    NEEDS_REVIEW: "Needs eligibility review",
    LIKELY_INELIGIBLE: "Likely not eligible to apply directly",
    INELIGIBLE: "Not eligible (official restriction)",
    NOT_CHECKED: "Eligibility not yet checked",
}
CERTAINTY_LABELS = {
    "confirmed": "Confirmed restriction",
    "interpretation": "Interpretation of official text",
    "uncertain": "Uncertain",
}
RANK = {LIKELY_ELIGIBLE: 0, NEEDS_REVIEW: 1, NOT_CHECKED: 2, LIKELY_INELIGIBLE: 3, INELIGIBLE: 4}

APPLICANT_TYPE_IDS = {
    "State governments": "00",
    "County governments": "01",
    "City or township governments": "02",
    "Special district governments": "04",
    "Independent school districts": "05",
    "Public and State controlled institutions of higher education": "06",
}
UNRESTRICTED_ID, OTHERS_ID = "99", "25"
CATEGORY_NAMES = {
    "state_government": "state governments", "local_government": "local governments",
    "tribal": "tribal governments/organizations", "higher_education": "institutions of higher education",
    "nonprofit": "nonprofits", "for_profit": "for-profit/commercial organizations",
    "federal": "federal agencies", "individuals": "individuals", "school_district": "school districts",
    "public_housing": "public housing authorities", "foreign": "foreign entities",
}
CATEGORY_PATTERNS = {
    "state_government": (
        r"\bstate (?:governments?|agenc(?:y|ies)|departments?|government agencies|entities|offices?)\b|"
        r"\bstates?,? (?:and |or )?(?:local|territor\w*|trib\w*|the district|count\w*|cit\w*|municipal\w*)|"
        r"\b(?:the )?50 states\b|\beligible states\b|\bstate,? (?:and )?local\b|"
        r"(?:^\s*|[:;,]\s*|\binclude\s+|\bare\s+)states\b"
    ),
    "local_government": (r"\b(?:count(?:y|ies)|cit(?:y|ies)|municipal\w*|townships?|local governments?|"
                         r"local government agencies|special districts?|units of local government)\b"),
    "tribal": r"\btrib(?:al|es)\b|\bindian tribes?\b|\bnative american\b",
    "higher_education": r"institutions? of higher (?:education|learning)|\buniversit(?:y|ies)\b|\bcolleges?\b",
    "nonprofit": r"\bnon-?profits?\b|not-for-profit|501\s?\(c\)",
    "for_profit": (r"commercial organizations?|for-profit|\bsmall business\w*|\bbusinesses\b|"
                   r"private sector|\bcompanies\b|\bindustry\b"),
    "federal": r"\bfederal (?:agenc(?:y|ies)|entities|laboratories|government agencies)\b",
    "individuals": r"\bindividuals\b",
    "school_district": r"\bschool districts?\b|local education(?:al)? agenc",
    "public_housing": r"public housing (?:authorit|agenc)",
    "foreign": r"\bforeign\b|international (?:institutions|organizations)",
}
_CATEGORY_RX = {k: re.compile(v, re.IGNORECASE) for k, v in CATEGORY_PATTERNS.items()}

LIST_TRIGGER = re.compile(
    r"(?:eligible applicants?(?: for this [^.:]{0,40})?(?:\s+(?:are|include|is))?|"
    r"eligibility (?:for this [^.:]{0,40})?is (?:limited|restricted) to|"
    r"applicants? (?:are |is )?(?:limited|restricted) to|"
    r"(?:only )?the following[^.:]{0,40}?(?:are |is )?eligible(?: to apply)?|"
    r"eligible (?:entities|organizations|recipients)(?:\s+(?:are|include))?|"
    r"eligible to apply(?:\s+(?:are|include))?|may be submitted (?:only )?by)\s*:?",
    re.IGNORECASE,
)
STATE_EXCLUSION = re.compile(
    r"state (?:governments?|agenc(?:y|ies)|departments?)[^.]{0,80}?\b(?:are|is) (?:not |in)eligible|"
    r"(?:not |in)eligible[^.]{0,40}?:?[^.]{0,100}?\bstate (?:governments?|agenc(?:y|ies)|departments?)\b",
    re.IGNORECASE,
)
STATE_POSITIVE = re.compile(
    r"state (?:governments?|agenc(?:y|ies))[^.]{0,60}?\b(?:are|is) eligible|"
    r"state (?:governments?|agenc(?:y|ies)) may apply",
    re.IGNORECASE,
)
ONLY_RESTRICTION = re.compile(
    r"\bonly\b[^.]{0,160}?\b(?:eligible|may apply|can apply|are eligible)\b", re.IGNORECASE
)
OTHER_REGION_HINTS = (
    "great lakes", "great plains", "colorado river", "pacific", "alaska", "hawaii",
    "puerto rico", "guam", "chesapeake", "gulf of maine", "rocky mountain", "mississippi river",
    "california", "texas", "florida", "puget sound", "columbia river", "new england",
)
MAX_QUOTE = 280


def _norm(text):
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def _clip(text, start, end):
    """Exact substring (whitespace-collapsed), clipped at a word boundary."""
    quote = re.sub(r"\s+", " ", text[start:end]).strip().rstrip(";,")
    if len(quote) <= MAX_QUOTE:
        return quote, False
    cut = quote[:MAX_QUOTE].rsplit(" ", 1)[0].rstrip(";,")
    return cut, True


def categories_in(text):
    cleaned = re.sub(r"united states", " ", text, flags=re.IGNORECASE)
    return [k for k, rx in _CATEGORY_RX.items() if rx.search(cleaned)]


def parse_notes(notes):
    """Rule-based reading of the eligibility notes."""
    notes = _norm(notes)
    found = {"listed": None, "state_exclusion": None, "state_positive": None, "only": None}
    if not notes:
        return found
    m = STATE_EXCLUSION.search(notes)
    if m:
        found["state_exclusion"] = _clip(notes, m.start(), m.end())
    m = STATE_POSITIVE.search(notes)
    if m:
        found["state_positive"] = _clip(notes, m.start(), m.end())
    for trigger in LIST_TRIGGER.finditer(notes):
        # "Other/Additional eligible applicants include ..." (common in NIH notices) adds to the
        # structured applicant types; it is not an exclusive list.
        lead_in = notes[max(0, trigger.start() - 15):trigger.start()].lower()
        if re.search(r"\b(?:other|additional|also)\s*$", lead_in) or re.search(
                r"\b(?:also|additionally|in addition)\b", notes[trigger.start():trigger.end() + 20], re.I):
            continue
        tail = notes[trigger.end():trigger.end() + 700]
        stop = re.search(r"\.\s+(?=[A-Z0-9])|\.$", tail)
        list_text = tail[:stop.start()] if stop else tail
        cats = [c for c in categories_in(list_text) if c != "foreign"]
        if cats:
            quote, truncated = _clip(notes, trigger.start(), trigger.end() + len(list_text))
            found["listed"] = {"categories": cats, "quote": quote, "truncated": truncated}
            break
    m = ONLY_RESTRICTION.search(notes)
    if m:
        found["only"] = _clip(notes, m.start(), m.end())
    return found


def _result(status, certainty, basis, reasoning, quote=None, truncated=False, quote_source=None,
            to_verify=(), checks=(), types=(), listed=(), source_url=None, region_flags=(), ai=None):
    verify = list(to_verify)
    if region_flags:
        verify.insert(0, f"Title mentions {', '.join(region_flags)}: confirm North Carolina applicants are in scope.")
    if status not in (INELIGIBLE, NOT_CHECKED):
        verify.append("Read the eligibility section of the full announcement before investing effort.")
    return {
        "status": status, "label": LABELS[status],
        "certainty": certainty, "certainty_label": CERTAINTY_LABELS[certainty],
        "basis": basis, "reasoning": reasoning, "summary": reasoning,
        "quote": quote, "quote_truncated": truncated, "quote_source": quote_source,
        "source_url": source_url, "to_verify": verify, "checks": list(checks),
        "applicant_types": list(types), "listed_categories": [CATEGORY_NAMES[c] for c in listed],
        "region_flags": list(region_flags), "evidence": quote, "ai": ai,
    }


def assess_eligibility(details, profile, title="", source_url=None):
    """Deterministic assessment (rules only)."""
    categories = (profile or {}).get("applicant_categories") or ["State governments"]
    agency = (profile or {}).get("short_name") or "The agency"
    region_flags = [r for r in OTHER_REGION_HINTS
                    if re.search(r"(?<![a-z])" + re.escape(r) + r"(?![a-z])", str(title).lower())]
    common = {"source_url": source_url, "region_flags": region_flags}

    if not details:
        return _result(NOT_CHECKED, "uncertain", "none", "Official eligibility details have not been loaded.",
                       to_verify=["Open the Grants.gov listing and check applicant types and eligibility notes."],
                       **common)

    types = details.get("applicant_types") or []
    descriptions = [t.get("description", "") for t in types if t.get("description")]
    ids = {t.get("id") for t in types}
    notes = details.get("eligibility_text") or ""
    wanted_ids = {APPLICANT_TYPE_IDS[c] for c in categories if c in APPLICANT_TYPE_IDS}
    type_listed = bool(ids & wanted_ids) or any(d.lower() in {c.lower() for c in categories} for d in descriptions)
    unrestricted = UNRESTRICTED_ID in ids or any(d.lower().startswith("unrestricted") for d in descriptions)
    others = OTHERS_ID in ids or any(d.lower().startswith("others") for d in descriptions)
    parsed = parse_notes(notes)
    listed = parsed["listed"]
    listed_cats = listed["categories"] if listed else []
    state_in_list = "state_government" in listed_cats
    type_text = "; ".join(descriptions) or "none listed"
    common.update(types=descriptions, listed=listed_cats)
    NOTES, FIELD = "Grants.gov eligibility notes", "Grants.gov applicant types field"

    checks = [{"item": "Structured applicant types", "detail": type_text,
               "status": "ok" if (type_listed or unrestricted) else "verify" if others or not types else "fail"}]
    if listed:
        checks.append({"item": "Eligible applicants listed in notes",
                       "detail": ", ".join(CATEGORY_NAMES[c] for c in listed_cats),
                       "status": "ok" if state_in_list else "fail"})
    if parsed["state_exclusion"]:
        checks.append({"item": "Explicit exclusion", "detail": parsed["state_exclusion"][0], "status": "fail"})
    if parsed["only"] and not listed:
        checks.append({"item": "'Only' restriction", "detail": parsed["only"][0], "status": "verify"})

    # 1. Confirmed restrictions.
    tribal_requirement = re.search(
        r"\bapplicants will meet all (?:the )?following eligibility requirements\s*:\s*"
        r"the tribe must be one of the following federally recognized tribes\b", notes, re.I)
    if (tribal_requirement and categories == ["State governments"] and not type_listed
            and not unrestricted and not parsed["state_positive"] and not state_in_list):
        return _result(INELIGIBLE, "confirmed", "eligibility_notes",
                       "Official notes require the direct applicant to be one of the named federally recognized tribes; "
                       "an NC state agency is not that direct applicant. A partner role is not established.",
                       tribal_requirement.group(0), False, NOTES, checks=checks, **common)
    if parsed["state_exclusion"]:
        q, t = parsed["state_exclusion"]
        return _result(INELIGIBLE, "confirmed", "eligibility_notes",
                       f"The official eligibility notes explicitly exclude state governments/agencies, so {agency} "
                       "cannot apply directly.", q, t, NOTES, checks=checks, **common)
    if types and not (type_listed or unrestricted or others):
        if parsed["state_positive"] or state_in_list:
            q, t = parsed["state_positive"] or (listed["quote"], listed["truncated"])
            return _result(NEEDS_REVIEW, "uncertain", "conflict",
                           "The structured applicant types exclude state governments, but the notes appear to "
                           "include them.", q, t, NOTES,
                           to_verify=["Ask the program contact which applicant types apply."], checks=checks, **common)
        return _result(INELIGIBLE, "confirmed", "structured_field",
                       f"The official applicant types ({type_text}) do not include {', '.join(categories)}. "
                       f"{agency} likely cannot apply directly; partnering with an eligible applicant may be possible.",
                       type_text, False, FIELD,
                       to_verify=["If partnering, confirm sub-award or partner roles are allowed."],
                       checks=checks, **common)

    # 2. State government listed in the structured field (or Unrestricted).
    if type_listed or unrestricted:
        which = ", ".join(categories) if type_listed else "Unrestricted"
        if listed and not state_in_list:
            return _result(NEEDS_REVIEW, "uncertain", "conflict",
                           f"'{which}' is a listed applicant type, but the eligibility notes list other applicant "
                           "categories without state governments.", listed["quote"], listed["truncated"], NOTES,
                           to_verify=["Confirm with the program contact whether state agencies may apply."],
                           checks=checks, **common)
        if parsed["only"] and not state_in_list and not parsed["state_positive"]:
            q, t = parsed["only"]
            return _result(NEEDS_REVIEW, "uncertain", "eligibility_notes",
                           f"'{which}' is listed, but the notes contain an 'only' restriction that may exclude {agency}.",
                           q, t, NOTES, to_verify=[f"Check whether {agency} meets this restriction."],
                           checks=checks, **common)
        return _result(LIKELY_ELIGIBLE, "interpretation", "structured_field",
                       f"Grants.gov lists '{which}' as an eligible applicant type and the notes show no conflicting "
                       f"restriction, so {agency} appears eligible to apply directly. This is not a guarantee.",
                       which if type_listed else "Unrestricted", False, FIELD,
                       to_verify=["Confirm program-specific requirements (purpose, location, prior awards, "
                                  "cost share)."], checks=checks, **common)

    # 3. "Others" or no structured types: rely on the notes.
    if listed and state_in_list:
        return _result(LIKELY_ELIGIBLE, "interpretation", "eligibility_notes",
                       f"The eligibility notes list state governments among eligible applicants, so {agency} appears "
                       "eligible to apply directly. This is not a guarantee.", listed["quote"], listed["truncated"],
                       NOTES, to_verify=["Confirm any additional conditions in the full announcement."],
                       checks=checks, **common)
    if parsed["state_positive"]:
        q, t = parsed["state_positive"]
        return _result(LIKELY_ELIGIBLE, "interpretation", "eligibility_notes",
                       f"The eligibility notes state that state governments/agencies are eligible, so {agency} appears "
                       "eligible to apply directly. This is not a guarantee.", q, t, NOTES, checks=checks, **common)
    if listed:
        names = ", ".join(CATEGORY_NAMES[c] for c in listed_cats)
        return _result(LIKELY_INELIGIBLE, "interpretation", "eligibility_notes",
                       f"The eligibility notes list the eligible applicants ({names}) and state governments are not "
                       f"among them, so {agency} likely cannot apply directly.", listed["quote"], listed["truncated"],
                       NOTES, to_verify=["Confirm with the program contact if you believe a state agency qualifies.",
                                         "Consider partnering with a listed eligible applicant (e.g., a university)."],
                       checks=checks, **common)
    if parsed["only"]:
        q, t = parsed["only"]
        return _result(LIKELY_INELIGIBLE, "interpretation", "eligibility_notes",
                       f"The notes restrict eligibility to specific applicants that do not appear to include {agency}.",
                       q, t, NOTES, to_verify=[f"Check whether {agency} is covered by this restriction."],
                       checks=checks, **common)
    quote, truncated = _clip(_norm(notes), 0, len(_norm(notes))) if notes else (None, False)
    return _result(NEEDS_REVIEW, "uncertain", "eligibility_notes",
                   "Applicant type is 'Others' or not listed, and the notes do not clearly say whether state agencies "
                   "may apply.", quote, truncated, NOTES if notes else None,
                   to_verify=["Read the eligibility notes and ask the program contact whether state agencies may "
                              "apply directly."], checks=checks, **common)


def apply_ai(assessment, ai):
    """Merge a validated AI interpretation. Never overrides confirmed restrictions."""
    if not ai:
        return assessment
    merged = dict(assessment, ai=ai)
    if ai.get("status") != "ok" or assessment["status"] in (INELIGIBLE, NOT_CHECKED):
        return merged
    verdict = ai["verdict"]
    current = assessment["status"]
    ai_status = {"likely_eligible": LIKELY_ELIGIBLE, "likely_ineligible": LIKELY_INELIGIBLE}.get(verdict, NEEDS_REVIEW)
    to_verify = list(dict.fromkeys(ai.get("to_verify", []) + assessment["to_verify"]))

    if current == NEEDS_REVIEW and ai_status != NEEDS_REVIEW:
        merged.update(status=ai_status, label=LABELS[ai_status], certainty="interpretation",
                      certainty_label="Interpretation (AI, verify)", basis="ai_interpretation",
                      reasoning=ai["reasoning"], summary=ai["reasoning"], quote=ai["quote"], evidence=ai["quote"],
                      quote_truncated=False, quote_source=ai["quote_source"], to_verify=to_verify)
    elif current in (LIKELY_ELIGIBLE, LIKELY_INELIGIBLE) and ai_status not in (current, NEEDS_REVIEW):
        merged.update(status=NEEDS_REVIEW, label=LABELS[NEEDS_REVIEW], certainty="uncertain",
                      certainty_label=CERTAINTY_LABELS["uncertain"], basis="conflict",
                      reasoning=(f"Rule-based reading suggests '{LABELS[current]}', but the AI interpretation "
                                 f"suggests '{LABELS[ai_status]}': {ai['reasoning']}"),
                      to_verify=to_verify)
        merged["summary"] = merged["reasoning"]
    else:
        merged["to_verify"] = to_verify
    return merged
