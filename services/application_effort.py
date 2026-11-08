"""Evidence-based application effort / readiness assessment.

Looks for common application requirements in *official* text only:
the Grants.gov synopsis, eligibility notes, the cost-sharing field, supporting
document names and, when the user asks for it, the full announcement (NOFO)
PDF. Every requirement found carries a short quote and its source. Nothing is
estimated in hours, and the absence of a match is never reported as
"no requirements": it is reported as insufficient evidence.
"""
import io
import re

import requests

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PDF_PAGES = 120

# (key, label, pattern, substantive) - substantive items count toward effort.
REQUIREMENT_RULES = [
    ("cost_sharing", "Cost sharing / matching funds",
     r"cost[- ]shar\w*|matching (?:funds|contribution|requirement)|non-federal (?:share|match)", True),
    ("partnership", "Partnership or consortium",
     r"partnership (?:is |are )?required|consorti\w+|memorand\w+ of (?:understanding|agreement)|"
     r"formal (?:partner|collaborat)\w*|lead applicant", True),
    ("letters", "Letters of support / commitment", r"letters? of (?:support|commitment)", True),
    ("budget", "Detailed budget / budget narrative",
     r"budget (?:narrative|justification)|sf-?424a|detailed budget|budget detail", True),
    ("narrative", "Project narrative / technical proposal",
     r"project narrative|technical (?:proposal|narrative)|statement of work|work plan", True),
    ("pre_application", "Letter of intent / pre-application",
     r"letters? of intent|pre-?application|concept paper|white paper|pre-?proposal", True),
    ("data_plan", "Data management plan", r"data management (?:plan|and sharing plan)", True),
    ("personnel", "Biographical sketches / current & pending support",
     r"biographical sketch\w*|current and pending support|curriculum vitae|resumes? of key", True),
    ("environmental", "Environmental review (e.g., NEPA)", r"\bnepa\b|environmental review|environmental compliance", True),
    ("evaluation", "Evaluation or performance-measurement plan",
     r"evaluation plan|performance measure\w* plan|logic model", True),
    ("registration", "SAM.gov / UEI registration", r"sam\.gov|unique entity identifier|\buei\b", False),
]
_COMPILED = [(k, label, re.compile(p, re.IGNORECASE), sub) for k, label, p, sub in REQUIREMENT_RULES]
PAGE_LIMIT = re.compile(r"(?:not (?:to )?exceed|no more than|maximum of|limited to)\s+(\d{1,3})\s+pages|"
                        r"(\d{1,3})[- ]page (?:limit|maximum)", re.IGNORECASE)


NEGATION_BEFORE = re.compile(r"\b(?:does not|do not|not|no|without|none)\b", re.IGNORECASE)
NEGATION_AFTER = re.compile(r"not (?:be )?required|\boptional\b|not mandatory|does not have any|do not have any|"
                            r"\bis not\b|\bare not\b|\bnot applicable\b", re.IGNORECASE)


def _is_negated(text, start, end):
    """True when the mention is stated as absent or optional in the same sentence."""
    before = text[max(0, start - 60):start].rsplit(".", 1)[-1]
    after = text[end:end + 90].split(".", 1)[0]
    return bool(NEGATION_BEFORE.search(before) or NEGATION_AFTER.search(after))


def _first_affirmative(pattern, text):
    for match in pattern.finditer(text):
        if not _is_negated(text, match.start(), match.end()):
            return match
    return None


class EffortAnalysisError(RuntimeError):
    pass


def _snippet(text, start, end, width=90):
    left = max(0, start - width)
    right = min(len(text), end + width)
    snippet = re.sub(r"\s+", " ", text[left:right]).strip()
    return ("…" if left else "") + snippet + ("…" if right < len(text) else "")


def _sources_from_details(details):
    sources = []
    if details.get("description"):
        sources.append(("Grants.gov synopsis", details["description"]))
    if details.get("eligibility_text"):
        sources.append(("Grants.gov eligibility notes", details["eligibility_text"]))
    # File names use separators like "Biographical-sketch-form_v2.pdf"; make them readable words.
    names = [re.sub(r"[-_]+", " ", a["name"]) for a in details.get("attachments") or [] if a.get("name")]
    if names:
        sources.append(("Supporting document names", " | ".join(names)))
    return sources


def assess_effort(details, announcement_text=None, announcement_url=None):
    """Return an effort assessment dict from official evidence only."""
    if not details:
        return {"level": "unknown", "label": "Not assessed",
                "summary": "Official details not loaded.", "requirements": [], "not_required": [],
                "page_limit": None, "sources_checked": [], "announcement_analyzed": False}

    sources = _sources_from_details(details)
    if announcement_text:
        sources.append(("Full announcement (NOFO)", announcement_text))

    found, not_required = {}, []
    if details.get("cost_sharing") is True:
        found["cost_sharing"] = {"key": "cost_sharing", "label": "Cost sharing / matching funds",
                                 "evidence": "Grants.gov field 'Cost Sharing or Matching Requirement' = Yes",
                                 "source": "Grants.gov listing field", "substantive": True}
    elif details.get("cost_sharing") is False:
        # The official structured field takes precedence over text mentions.
        not_required.append("Cost sharing / matching funds (Grants.gov field = No)")
    for source_name, text in sources:
        for key, label, pattern, substantive in _COMPILED:
            if key in found or (key == "cost_sharing" and details.get("cost_sharing") is False):
                continue
            match = _first_affirmative(pattern, text)
            if match:
                found[key] = {"key": key, "label": label, "evidence": _snippet(text, match.start(), match.end()),
                              "source": source_name, "substantive": substantive}

    page_limit = None
    for source_name, text in sources:
        match = PAGE_LIMIT.search(text)
        if match:
            page_limit = {"pages": int(match.group(1) or match.group(2)),
                          "evidence": _snippet(text, match.start(), match.end()), "source": source_name}
            break

    requirements = [found[k] for k, *_ in REQUIREMENT_RULES if k in found]
    substantive = sum(1 for r in requirements if r["substantive"])
    heavy = {"cost_sharing", "partnership"} <= set(found)
    text_volume = sum(len(t) for _, t in sources)

    if substantive >= 4 or heavy:
        level, label = "higher", "Higher effort"
    elif substantive >= 2:
        level, label = "moderate", "Moderate effort"
    elif announcement_text:
        level, label = "fewer_found", "Few requirements found"
    elif text_volume < 1500:
        level, label = "insufficient", "Insufficient evidence"
    else:
        level, label = "unclear", "Unclear from summary"

    if level == "insufficient":
        summary = "Grants.gov summary text is too short to judge effort. Review the full announcement."
    elif level == "unclear":
        summary = ("The Grants.gov summary mentions few common requirements; most requirements are usually "
                   "in the full announcement.")
    elif requirements:
        summary = f"{substantive} application requirement(s) identified in official text."
    else:
        summary = "No common requirements matched in the text checked; the full announcement may list more."
    if not announcement_text and level != "insufficient":
        summary += " Based on the Grants.gov summary only."

    return {"level": level, "label": label, "summary": summary, "requirements": requirements,
            "not_required": not_required,
            "page_limit": page_limit, "sources_checked": [name for name, _ in sources],
            "announcement_analyzed": bool(announcement_text), "announcement_url": announcement_url}


def find_announcement(details):
    """Pick the full-announcement PDF attachment, if Grants.gov lists one."""
    attachments = (details or {}).get("attachments") or []
    pdfs = [a for a in attachments if "pdf" in a.get("mime_type", "").lower() or a["name"].lower().endswith(".pdf")]
    for attachment in pdfs:
        if "full announcement" in attachment["folder"].lower():
            return attachment
    return pdfs[0] if len(pdfs) == 1 else None


def fetch_announcement_text(details, timeout=45):
    """Download the full announcement PDF and extract text (on demand only)."""
    attachment = find_announcement(details)
    if not attachment:
        raise EffortAnalysisError("No full-announcement PDF is attached on Grants.gov.")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise EffortAnalysisError("PDF analysis requires the 'pypdf' package.") from exc
    try:
        response = requests.get(attachment["url"], timeout=timeout, stream=True)
        response.raise_for_status()
        content = response.raw.read(MAX_PDF_BYTES + 1, decode_content=True)
    except requests.RequestException as exc:
        raise EffortAnalysisError(f"Could not download the announcement: {exc}") from exc
    if len(content) > MAX_PDF_BYTES:
        raise EffortAnalysisError("Announcement PDF is too large to analyze here; open it on Grants.gov.")
    try:
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES])
    except Exception as exc:  # noqa: BLE001 - malformed PDFs are common
        raise EffortAnalysisError(f"Could not read the announcement PDF: {exc}") from exc
    if len(text.strip()) < 200:
        raise EffortAnalysisError("The announcement PDF has no extractable text (it may be scanned).")
    return text, attachment["url"]
