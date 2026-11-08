"""Full-notice application effort for the Brief, computed on demand (detail panel only).

Uses Search's own rule-based pieces unchanged:
- services.official_evidence.OfficialEvidenceClient: Grants.gov detail API plus up to a few official
  .gov documents (attachments and links in the synopsis). Network only; no Azure/LLM.
- services.official_evidence.extract_document: PDF/DOCX/HTML text extraction.
- services.application_effort.assess_effort: regex requirement rules on official text.
Adapter addition: Grants.gov "Full Announcement" HTML stubs that only meta-refresh to the real notice
(NIH posts notices on grants.nih.gov) are followed once, upgraded to https, with the same client.
No GPT or Deep Research calls. Results are cached per opportunity id for all sessions; network
failures are not cached so a later open can retry.
"""
import re
from urllib.parse import urlparse

import streamlit as st

from services.application_effort import assess_effort
from services.official_evidence import OfficialEvidenceClient, extract_document
from ui.view_model import _effort

MAX_DOCUMENTS = 3
MIN_TEXT = 200
NO_NOTICE = "The full funding notice couldn't be found from the listing, so effort is based on the listing summary."
UNREADABLE = "The full funding notice couldn't be read automatically, so effort is based on the listing summary."
REFRESH = re.compile(rb"""http-equiv=["']?refresh["']?[^>]*?url=['"]?([^'">\s]+)""", re.IGNORECASE)


@st.cache_resource
def _cache():
    return {}


def cached(opp_id):
    return _cache().get(str(opp_id))


def _follow_stub(client, item):
    """Text of the page a meta-refresh stub points to, or ''."""
    raw, _, _ = client._download(item["url"])
    match = REFRESH.search(raw)
    if not match:
        return "", None
    target = match.group(1).decode("utf-8", "replace")
    parsed = urlparse(target)
    if parsed.scheme == "http" and (parsed.hostname or "").endswith((".gov", ".mil")):
        target = "https://" + target[len("http://"):]
    raw, mime, final = client._download(target)
    text, _ = extract_document(raw, mime, parsed.path.rsplit("/", 1)[-1] or "notice.html")
    return text, final


def official_notice_text(opp_id, client=None):
    """(text, url) from the official notice documents; ('', None) if none could be read."""
    client = client or OfficialEvidenceClient(max_documents=MAX_DOCUMENTS)
    evidence = client.fetch(opp_id)
    docs = {s.get("name"): s for s in evidence.get("sources") or [] if s.get("kind") == "official_document"}
    texts, first_url = [], None
    for item in evidence.get("inventory") or []:
        if not item.get("ingested"):
            continue
        source = docs.get(item.get("name")) or {}
        text, url = source.get("text") or "", source.get("url")
        if len(text.strip()) < MIN_TEXT:
            try:
                text, url = _follow_stub(client, item)
            except Exception:  # noqa: BLE001 - an unreadable stub just adds nothing
                text = ""
        if len(text.strip()) >= MIN_TEXT:
            texts.append(text)
            first_url = first_url or url
    return "\n\n".join(texts), first_url


def compute(opp_id, details, fetch=official_notice_text):
    """Return {"effort": dict} or {"error": message}; caches successes and 'no notice' results."""
    key = str(opp_id)
    if key in _cache():
        return _cache()[key]
    if not details:
        return None  # official details weren't loaded for this grant; keep the listing value
    try:
        text, url = fetch(key)
    except Exception:  # noqa: BLE001 - network hiccup: don't cache, retry on a later open
        return {"error": UNREADABLE}
    outcome = ({"effort": assess_effort(details, announcement_text=text, announcement_url=url)}
               if text else {"error": NO_NOTICE})
    _cache()[key] = outcome
    return outcome


def apply(view, outcome):
    """Update a view's effort fields in place from a full-notice result. Returns True if changed."""
    if not outcome:
        return False
    if outcome.get("effort"):
        for name, value in _effort({"effort": outcome["effort"]}, view.cost_share_text, view.cost_share_status).items():
            setattr(view, name, value)
        return True
    if outcome.get("error") and outcome["error"] not in view.effort_note:
        view.effort_note = f"{view.effort_note} {outcome['error']}".strip()
    return False
