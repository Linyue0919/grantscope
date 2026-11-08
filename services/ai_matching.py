"""Optional Azure OpenAI (GPT-4o) semantic fit between a grant and verified goals.

* Used only for relevance. Deadline and eligibility screening stay deterministic
  in services/match_engine.py, and AI output can never override them.
* Every AI answer must cite source ids and verbatim quotes. Answers whose quotes
  are not found in the cited source, or that cite unknown goals, are rejected.
* If configuration, the `openai` package, or the service is unavailable, the
  evaluator reports that status and the keyword heuristic is used alone.

Configuration (environment variables or Streamlit secrets; never logged):
  AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY,
  AZURE_OPENAI_DEPLOYMENT (default "grantscope-gpt4o"),
  AZURE_OPENAI_API_VERSION (default "2024-10-21")
"""
import hashlib
import json
import os
import re
import unicodedata

PROMPT_VERSION = "fit-v1"
DEFAULT_DEPLOYMENT = "grantscope-gpt4o"
DEFAULT_API_VERSION = "2024-10-21"
MAX_DESCRIPTION_CHARS = 5000

SYSTEM_PROMPT = (
    "You assess how well a U.S. federal grant opportunity aligns with a North Carolina state agency's "
    "published strategic goals. Use ONLY the numbered sources provided. Do not judge eligibility, "
    "deadlines, or likelihood of award. Respond with JSON only:\n"
    '{"relevance": <integer 0-100>, "goal_ids": [<goal source ids that the grant supports>], '
    '"evidence": [{"source_id": "<id>", "quote": "<exact words copied from that source>"}], '
    '"explanation": "<one sentence, at most 35 words>"}\n'
    "Rules: quotes must be copied exactly (5-25 words). Include at least one quote from the grant "
    "(source T or D) and cite at least one goal id when relevance > 0. Use relevance 0-20 when the "
    "grant does not meaningfully support any goal. Do not invent facts."
)


class AIUnavailable(RuntimeError):
    pass


def load_ai_config(source=None):
    """Read configuration from a mapping (default: environment). None if incomplete."""
    source = os.environ if source is None else source
    endpoint = str(source.get("AZURE_OPENAI_ENDPOINT") or "").strip()
    api_key = str(source.get("AZURE_OPENAI_API_KEY") or "").strip()
    if not endpoint or not api_key:
        return None
    return {
        "endpoint": endpoint,
        "api_key": api_key,
        "deployment": str(source.get("AZURE_OPENAI_DEPLOYMENT") or DEFAULT_DEPLOYMENT).strip(),
        "api_version": str(source.get("AZURE_OPENAI_API_VERSION") or DEFAULT_API_VERSION).strip(),
    }


def _norm(text):
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip().lower()


def build_sources(record, profile, details):
    sources = [{"id": "T", "kind": "grant", "label": "Grant title", "text": record["title"]}]
    description = (details or {}).get("description") or ""
    if description:
        sources.append({"id": "D", "kind": "grant", "label": "Grants.gov synopsis",
                        "text": description[:MAX_DESCRIPTION_CHARS]})
    for goal in profile["goals"]:
        sources.append({"id": goal["goal_id"], "kind": "goal", "label": goal["label"], "text": goal["quote"],
                        "page": goal["page"], "url": profile["plan_url"]})
    return sources


def make_cache_key(profile, record, details, config):
    goals = json.dumps([[g["goal_id"], g["quote"]] for g in profile["goals"]], sort_keys=True)
    content = json.dumps([record["title"], (details or {}).get("description", "")[:MAX_DESCRIPTION_CHARS]])
    raw = "|".join([profile["name"], hashlib.sha256(goals.encode()).hexdigest(), record["id"],
                    hashlib.sha256(content.encode()).hexdigest(), config["deployment"],
                    config["api_version"], PROMPT_VERSION])
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_response(raw, sources):
    """Parse and validate a model response. Returns (result, errors)."""
    errors = []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None, ["Response was not valid JSON."]
    if not isinstance(data, dict):
        return None, ["Response was not a JSON object."]

    by_id = {s["id"]: s for s in sources}
    try:
        relevance = int(data.get("relevance"))
    except (TypeError, ValueError):
        return None, ["Missing or non-numeric relevance."]
    if not 0 <= relevance <= 100:
        return None, ["Relevance outside 0-100."]

    goal_ids = [g for g in data.get("goal_ids") or [] if isinstance(g, str)]
    unknown = [g for g in goal_ids if by_id.get(g, {}).get("kind") != "goal"]
    if unknown:
        errors.append(f"Unknown goal id(s): {', '.join(unknown)}")

    evidence = []
    for item in data.get("evidence") or []:
        if not isinstance(item, dict):
            continue
        sid, quote = str(item.get("source_id") or ""), str(item.get("quote") or "").strip()
        source = by_id.get(sid)
        if not source:
            errors.append(f"Evidence cites unknown source '{sid}'.")
        elif len(_norm(quote)) < 8 or _norm(quote) not in _norm(source["text"]):
            errors.append(f"Quote not found in source {sid}: \"{quote[:80]}\"")
        else:
            evidence.append({"source_id": sid, "source_label": source["label"], "quote": quote,
                             "page": source.get("page"), "url": source.get("url")})

    if relevance > 20:
        if not goal_ids:
            errors.append("Relevance above 20 without any cited goal.")
        if not any(by_id[e["source_id"]]["kind"] == "grant" for e in evidence):
            errors.append("No verified quote from the grant text.")
    if errors:
        return None, errors

    explanation = re.sub(r"\s+", " ", str(data.get("explanation") or "")).strip()
    words = explanation.split()
    if len(words) > 45:
        explanation = " ".join(words[:45]) + "…"
    return {"score": relevance, "goal_ids": goal_ids, "evidence": evidence, "explanation": explanation}, []


def describe_config(config):
    """Safe, credential-free description of the AI configuration (for UI and checks)."""
    if not config:
        return {"configured": False}
    host = re.sub(r"^https?://", "", config["endpoint"]).split("/")[0]
    first = host.split(".")[0]
    masked = (first[:3] + "***" + first[-2:] if len(first) > 6 else "***") + host[len(first):]
    return {"configured": True, "endpoint": masked, "deployment": config["deployment"],
            "api_version": config["api_version"], "api_key": "set (hidden)"}


class AzureJSONEvaluator:
    """Shared Azure OpenAI chat client with caching; subclasses define the task."""

    def __init__(self, config, client=None, cache=None, timeout=20):
        self.config = config
        self.cache = {} if cache is None else cache
        self.timeout = timeout
        self._client = client

    @property
    def model_label(self):
        return self.config["deployment"]

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AzureOpenAI
            except ImportError as exc:
                raise AIUnavailable("The 'openai' package is not installed.") from exc
            self._client = AzureOpenAI(azure_endpoint=self.config["endpoint"], api_key=self.config["api_key"],
                                       api_version=self.config["api_version"], max_retries=1)
        return self._client

    def complete_json(self, system, user, max_tokens=400):
        """Return the raw JSON text. Raises on transport/auth errors."""
        response = self._get_client().chat.completions.create(
            model=self.config["deployment"],
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0, max_tokens=max_tokens, response_format={"type": "json_object"}, timeout=self.timeout,
        )
        return response.choices[0].message.content

    def _guarded(self, key, call):
        """Run call() with caching and uniform, credential-free error handling."""
        base = {"model": self.config["deployment"], "prompt_version": self.prompt_version}
        if key in self.cache:
            return dict(self.cache[key], cached=True)
        try:
            outcome = dict(base, **call())
        except AIUnavailable as exc:
            return dict(base, status="unavailable", errors=[str(exc)])
        except Exception as exc:  # noqa: BLE001 - network/auth/rate-limit errors fall back to rules
            from services.ai_diagnostics import classify_exception, secrets_from_config
            info = classify_exception(exc, secrets_from_config(self.config))
            detail = ", ".join(x for x in (f"HTTP {info['http_status']}" if info["http_status"] else None,
                                           info["error_code"], info["cause"]) if x)
            return dict(base, status="error", errors=[info["exception"] + (f" ({detail})" if detail else "")])
        self.cache[key] = outcome
        return outcome


class AzureFitEvaluator(AzureJSONEvaluator):
    """Callable used by match_engine.run_matching(ai_evaluator=...)."""

    prompt_version = PROMPT_VERSION

    def __call__(self, record, profile, details):
        key = make_cache_key(profile, record, details, self.config)
        sources = build_sources(record, profile, details)

        def call():
            user = "\n\n".join(f"[{s['id']}] ({s['label']}) {s['text']}" for s in sources)
            result, errors = validate_response(self.complete_json(SYSTEM_PROMPT, user), sources)
            if result is None:
                return {"status": "rejected", "errors": errors}
            return dict(status="ok", errors=[], **result)

        return self._guarded(key, call)
