"""Optional GPT-4o interpretation of complex eligibility notes.

The model reads ONLY the official applicant types and eligibility notes and says
whether an NC state agency appears eligible to apply directly. Its answer must
include an exact quote from that official text; otherwise it is rejected. The
result is merged by services.eligibility_assessment.apply_ai, which never lets
the AI override a confirmed restriction.
"""
import hashlib
import json
import re

from services.ai_matching import AzureJSONEvaluator, _norm

PROMPT_VERSION = "elig-v1"
MAX_NOTES_CHARS = 6000
VERDICTS = {"likely_eligible", "likely_ineligible", "uncertain"}

SYSTEM_PROMPT = (
    "You interpret U.S. federal grant eligibility rules for a North Carolina STATE GOVERNMENT agency "
    "(a department of the State of North Carolina, i.e., the applicant category 'State governments'). "
    "Decide whether this agency appears eligible to apply DIRECTLY as the lead applicant, using ONLY the "
    "official text provided. Respond with JSON only:\n"
    '{"verdict": "likely_eligible" | "likely_ineligible" | "uncertain", '
    '"reasoning": "<one or two sentences, at most 50 words>", '
    '"quote": "<exact words copied from the official text that support the verdict, 5-40 words>", '
    '"listed_applicant_categories": ["<categories the text says are eligible>"], '
    '"to_verify": ["<up to 3 short, specific items the agency should confirm>"]}\n'
    "Rules: State agencies are covered only by 'State governments' (or equivalent wording such as 'States' "
    "or 'state agencies'). Public universities, local governments, tribes, and nonprofits are different "
    "applicant categories. If the text lists eligible categories and none covers state governments, answer "
    "likely_ineligible. If eligibility depends on facts not in the text, answer uncertain. Never state or "
    "imply that eligibility is guaranteed. Copy the quote exactly."
)


def official_text(details):
    types = "; ".join(t.get("description", "") for t in (details or {}).get("applicant_types") or [])
    notes = ((details or {}).get("eligibility_text") or "")[:MAX_NOTES_CHARS]
    return types, notes


def make_cache_key(profile, details, config):
    types, notes = official_text(details)
    raw = "|".join([profile.get("name", ""), ",".join(profile.get("applicant_categories") or []),
                    hashlib.sha256((types + "\n" + notes).encode()).hexdigest(),
                    config["deployment"], config["api_version"], PROMPT_VERSION])
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_eligibility_response(raw, details):
    """Parse and validate. Returns (result, errors)."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None, ["Response was not valid JSON."]
    if not isinstance(data, dict):
        return None, ["Response was not a JSON object."]
    verdict = str(data.get("verdict") or "").strip()
    if verdict not in VERDICTS:
        return None, [f"Invalid verdict '{verdict[:30]}'."]
    reasoning = re.sub(r"\s+", " ", str(data.get("reasoning") or "")).strip()
    if not reasoning:
        return None, ["Missing reasoning."]
    if re.search(r"\bguarantee", reasoning, re.IGNORECASE) and not re.search(r"not (?:a )?guarantee", reasoning, re.I):
        return None, ["Reasoning implies guaranteed eligibility."]
    quote = str(data.get("quote") or "").strip().strip('"“”')
    types, notes = official_text(details)
    if len(quote.split()) < 3:
        return None, ["Quote too short or missing."]
    if _norm(quote) in _norm(notes):
        source = "Grants.gov eligibility notes"
    elif _norm(quote) in _norm(types):
        source = "Grants.gov applicant types field"
    else:
        return None, [f"Quote not found in the official text: \"{quote[:80]}\""]
    words = reasoning.split()
    if len(words) > 60:
        reasoning = " ".join(words[:60]) + "…"
    to_verify = [re.sub(r"\s+", " ", str(v)).strip() for v in (data.get("to_verify") or [])][:3]
    listed = [str(c).strip() for c in (data.get("listed_applicant_categories") or []) if str(c).strip()][:10]
    return {"verdict": verdict, "reasoning": reasoning, "quote": quote, "quote_source": source,
            "to_verify": [v for v in to_verify if v], "listed_categories": listed}, []


class AzureEligibilityEvaluator(AzureJSONEvaluator):
    """Callable used by match_engine.run_matching(eligibility_evaluator=...)."""

    prompt_version = PROMPT_VERSION

    def __call__(self, record, profile, details):
        types, notes = official_text(details)
        key = make_cache_key(profile, details, self.config)

        def call():
            if not types and not notes:
                return {"status": "skipped", "errors": ["No official eligibility text."]}
            user = (f"Agency: {profile['name']} (North Carolina state government agency; applicant category: "
                    f"{', '.join(profile.get('applicant_categories') or ['State governments'])})\n"
                    f"Grant: {record['title']}\n\nOfficial applicant types: {types or 'none listed'}\n\n"
                    f"Official eligibility notes: {notes or 'none provided'}")
            result, errors = validate_eligibility_response(self.complete_json(SYSTEM_PROMPT, user, 450), details)
            if result is None:
                return {"status": "rejected", "errors": errors}
            return dict(status="ok", errors=[], **result)

        return self._guarded(key, call)
