"""Print how many opportunities land in each Funding Brief section, per agency.

Uses the same backend call and adapter as the Brief page. With AI on (default), the
Azure OpenAI settings are loaded exactly as the app loads them and are never printed.

Usage:
  python scripts/brief_section_counts.py            # AI on (if configured)
  python scripts/brief_section_counts.py --no-ai    # rules + keyword heuristic only; no credentials loaded
  python scripts/brief_section_counts.py --agencies NCDHHS DEQ NCWRC --days 30
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.agency_profiles import get_agency_profile  # noqa: E402
from services.application_effort import find_announcement  # noqa: E402
from services.grants_api import get_grants  # noqa: E402
from services.match_engine import MatchSettings, run_matching  # noqa: E402
from services.opportunity_details import fetch_opportunity_details  # noqa: E402
from ui.brief_sections import SECTIONS, group_views  # noqa: E402
from ui.view_model import build_views  # noqa: E402


def arg_list(flag, default):
    if flag not in sys.argv:
        return default
    values = []
    for item in sys.argv[sys.argv.index(flag) + 1:]:
        if item.startswith("--"):
            break
        values.append(item)
    return values or default


def main():
    use_ai = "--no-ai" not in sys.argv
    agencies = arg_list("--agencies", ["NCDHHS", "DEQ", "NCWRC"])
    days = int(arg_list("--days", ["30"])[0])
    fit_ai = elig_ai = None
    if use_ai:
        from scripts.check_ai_config import load_settings
        from services.ai_eligibility import AzureEligibilityEvaluator
        from services.ai_matching import AzureFitEvaluator, load_ai_config
        config = load_ai_config(load_settings()[0])
        if config:
            cache = {}
            fit_ai, elig_ai = AzureFitEvaluator(config, cache=cache), AzureEligibilityEvaluator(config, cache=cache)
        else:
            print("AI not configured; counting with rules + keyword heuristic only.")
    print(f"Mode: {'GPT-4o ON' if fit_ai else 'AI off'} · at least {days} days left\n")
    details_cache = {}
    for name in agencies:
        profile = get_agency_profile(name)
        if not profile:
            print(f"{name}: not a profiled agency")
            continue
        start = time.time()
        result = run_matching(profile, MatchSettings(min_days_left=days), search_fn=get_grants,
                              details_fn=fetch_opportunity_details, details_cache=details_cache,
                              ai_evaluator=fit_ai, eligibility_evaluator=elig_ai)
        groups = group_views(build_views(result, profile, details_cache, find_announcement))
        counts = " · ".join(f"{s}={len(groups[s])}" for s in SECTIONS)
        print(f"{profile['name']:<45} {counts}   ({time.time() - start:.0f}s)")
        for view in groups["top"][:3]:
            print(f"    top   {view.fit_score:>3} {view.fit_tier:<8} {view.short_name}")
        for view in groups["check"][:3]:
            print(f"    check {view.fit_score:>3} {view.fit_tier:<8} {view.short_name} — unclear: {view.unclear_reason[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
