"""Validate the GPT-4o integration end to end on live Grants.gov data.

Runs the shared engine for a few agencies twice — AI off (rules + keyword heuristic)
and AI on (fit + eligibility evaluators) — and reports how AI changed ranking and
eligibility, whether every accepted AI answer is evidence-backed, the NOAA regression,
and fallback when the service fails. Credentials are loaded exactly as the app loads
them and are never printed; output contains only sanitized results.

Usage: python scripts/validate_ai_integration.py [--agencies DEQ NCDHHS NCDOT]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_ai_config import load_settings  # noqa: E402
from services.agency_profiles import get_agency_profile  # noqa: E402
from services.ai_eligibility import AzureEligibilityEvaluator, official_text  # noqa: E402
from services.ai_matching import AzureFitEvaluator, _norm, build_sources, describe_config, load_ai_config  # noqa: E402
from services.grants_api import get_grants  # noqa: E402
from services.match_engine import MatchSettings, run_matching  # noqa: E402
from services.opportunity_details import fetch_opportunity_details  # noqa: E402

NOAA_ID = "364160"


class FlakyClient:
    """Wraps the real client and fails every other call, to exercise partial fallback."""

    def __init__(self, real):
        self._real, self._n = real, 0
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer._n += 1
                if outer._n % 2 == 0:
                    raise TimeoutError("simulated outage")
                return outer._real.chat.completions.create(**kwargs)

        self.chat = type("Chat", (), {"completions": _Completions()})()


def all_records(result):
    return result["results"] + result["low_evidence"] + result["upcoming"] + result["likely_ineligible"]


def check_evidence(result, profile, cache):
    """Re-verify every accepted AI answer against its sources (independent of the validator)."""
    problems, checked = [], 0
    for record in all_records(result):
        details = cache.get(record["id"])
        fit = record["relevance"].get("ai") or {}
        if fit.get("status") == "ok":
            checked += 1
            sources = {s["id"]: s["text"] for s in build_sources(record, profile, details)}
            for item in fit["evidence"]:
                if _norm(item["quote"]) not in _norm(sources.get(item["source_id"], "")):
                    problems.append(f"fit quote not in source for {record['id']}")
        elig = record["eligibility"].get("ai") or {}
        if elig.get("status") == "ok":
            checked += 1
            types, notes = official_text(details)
            if _norm(elig["quote"]) not in _norm(types + " " + notes):
                problems.append(f"eligibility quote not in official text for {record['id']}")
            if "guarantee" in elig["reasoning"].lower() and "not" not in elig["reasoning"].lower():
                problems.append(f"guarantee language for {record['id']}")
    return checked, problems


def summarize(name, off, on, profile, cache):
    print(f"\n=== {name} ===")
    for label, key in (("fit", "ai"), ("eligibility", "ai_eligibility")):
        s = on[key]
        print(f"AI {label:<11}: status={s['status']} evaluated={s['evaluated']} accepted={s['accepted']} "
              f"rejected={s['rejected']} errors={s['errors']}")
    so, sn = off["stats"], on["stats"]
    print(f"Sections (off -> on): priority {so['priority']} -> {sn['priority']}, likely_ineligible "
          f"{so['likely_ineligible']} -> {sn['likely_ineligible']}, low_evidence {so['low_evidence']} -> "
          f"{sn['low_evidence']}, upcoming {so['upcoming']} -> {sn['upcoming']}")

    off_rank = [r["id"] for r in off["results"]]
    print("Top priority with AI (fit = keyword | AI -> blended; eligibility):")
    for i, r in enumerate(on["results"][:8], 1):
        ai = r["relevance"].get("ai") or {}
        ai_part = f"{ai['score']}" if ai.get("status") == "ok" else ai.get("status", "-")
        moved = (f"was #{off_rank.index(r['id']) + 1}" if r["id"] in off_rank else "NEW (rescued)")
        print(f"  {i}. [{r['relevance']['keyword']['score']}|{ai_part} -> {r['fit_score']}] {r['title'][:62]} "
              f"({moved}) · {r['eligibility']['label']}")
    off_status = {r["id"]: r["eligibility"]["status"] for r in all_records(off)}
    changes = [(r, off_status.get(r["id"])) for r in all_records(on)
               if off_status.get(r["id"]) and off_status[r["id"]] != r["eligibility"]["status"]]
    print(f"Eligibility changed by AI: {len(changes)}")
    for r, before in changes[:5]:
        e = r["eligibility"]
        print(f"  - {r['title'][:55]}: {before} -> {e['status']} ({e['basis']})")
        print(f"      reason: {e['reasoning'][:160]}")
        print(f"      quote : “{(e['quote'] or '')[:140]}”")
    sample = next((r for r in on["results"] if (r["relevance"].get("ai") or {}).get("status") == "ok"), None)
    if sample:
        ai = sample["relevance"]["ai"]
        print(f"Sample AI explanation ({sample['title'][:50]}): {ai['explanation']}")
        for item in ai["evidence"][:2]:
            print(f"      evidence [{item['source_id']}]: “{item['quote'][:120]}”")
    checked, problems = check_evidence(on, profile, cache)
    print(f"Evidence re-check: {checked} accepted AI answers, {len(problems)} problems {problems[:3]}")
    return problems


def main():
    settings, _ = load_settings()
    config = load_ai_config(settings)
    if not config:
        print("AI not configured; run scripts/check_ai_config.py first.")
        return 2
    info = describe_config(config)
    print(f"Using deployment {info['deployment']} (API {info['api_version']}); credentials not displayed.")
    names = sys.argv[sys.argv.index("--agencies") + 1:] if "--agencies" in sys.argv else ["DEQ", "NCDHHS", "NCDOT"]
    cache, ai_cache, failures = {}, {}, []
    for name in names:
        profile = get_agency_profile(name)
        kwargs = dict(search_fn=get_grants, details_fn=fetch_opportunity_details, details_cache=cache)
        off = run_matching(profile, MatchSettings(), **kwargs)
        start = time.time()
        on = run_matching(profile, MatchSettings(), **kwargs,
                          ai_evaluator=AzureFitEvaluator(config, cache=ai_cache),
                          eligibility_evaluator=AzureEligibilityEvaluator(config, cache=ai_cache))
        print(f"\n(AI-on run for {name}: {time.time() - start:.1f}s)")
        failures += summarize(profile["name"], off, on, profile, cache)
        noaa = [r for r in all_records(on) if r["id"] == NOAA_ID]
        if noaa:
            r = noaa[0]
            ok = r["section"] != "priority"
            print(f"NOAA {NOAA_ID}: section={r['section']} status={r['eligibility']['status']} "
                  f"basis={r['eligibility']['basis']} -> {'PASS' if ok else 'FAIL'}")
            if not ok:
                failures.append("NOAA in priority")

    # Fallback: real service, but every other call fails -> partial, deterministic results preserved.
    profile = get_agency_profile(names[0])
    real = AzureFitEvaluator(config)._get_client()
    flaky = dict(client=FlakyClient(real), cache={})
    off = run_matching(profile, MatchSettings(), search_fn=get_grants, details_fn=fetch_opportunity_details,
                       details_cache=cache)
    on = run_matching(profile, MatchSettings(), search_fn=get_grants, details_fn=fetch_opportunity_details,
                      details_cache=cache, ai_evaluator=AzureFitEvaluator(config, **flaky),
                      eligibility_evaluator=AzureEligibilityEvaluator(config, client=FlakyClient(real), cache={}))
    errored = [r for r in all_records(on) if (r["relevance"].get("ai") or {}).get("status") == "error"]
    consistent = all(r["fit_score"] == r["relevance"]["keyword"]["score"] for r in errored)
    print(f"\n=== Fallback (simulated intermittent outage) ===\nAI fit: {on['ai']['status']} "
          f"(errors={on['ai']['errors']}), eligibility: {on['ai_eligibility']['status']} "
          f"(errors={on['ai_eligibility']['errors']}); failed items use keyword score: {consistent}; "
          f"error note sample: {errored[0]['relevance']['ai']['errors'] if errored else '-'}")
    if not consistent:
        failures.append("fallback inconsistent")
    print(f"\nRESULT: {'PASS' if not failures else 'ISSUES: ' + '; '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
