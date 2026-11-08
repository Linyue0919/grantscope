# Merge notes: `dashboard-redesign` → your branches

For Linyue, from Zirou. These notes cover what will conflict when `dashboard-redesign` is merged with your latest work, and a suggested fix for each conflict. None of your files were changed. Every decision below is yours.

Checked against `origin` as fetched on Nov 8, 2026, around 6:45 AM ET.

## 1. Which branch to merge into

| Branch | Contains | Notes |
|---|---|---|
| `release/final-demo` (894e11e) | `main`, `feature/dashboard`, `feature/search-reliability`, `fix/release-search-precision` | Newest, so these notes target it |
| `feature/unified-search-analysis` (ab464a4) | 6 commits not in release | Same sidebar `app.py` and the same 4 pages |
| `fix/demo-search-precision` (87f6d52) | 22 commits not in release | Same sidebar `app.py` and the same 4 pages |

`dashboard-redesign` branched from `feature/dashboard` at **9c02d3f**. Your release branch already contains that commit.

> ⚠️ **Deploy trigger:** the workflow on `release/final-demo` runs on every push to `main` **and** `release/final-demo`. Merging into either one starts a build, which runs `pytest` and deploys if your environment gate allows. I suggest merging into a throwaway branch first, for example `integration/brief`, then running the app and tests there.

## 2. Files changed on both sides since 9c02d3f

Only five files overlap:

| File | Your change | Our change | Suggested resolution |
|---|---|---|---|
| `app.py` | Sidebar radio; adds **My Grants**; removes AI Help | Top navigation (`st.navigation(position="top")`) | Section 3 |
| `modules/dashboard.py` | `_ai_config()` → `load_ai_config(st.secrets)` (10 lines) | Rewritten into the **Brief** page | Take ours, then re-apply your `_ai_config` and add one import (section 4) |
| `modules/profile.py` | Agency directory, custom agency, custom priorities | Rewritten into the **Alerts** page (Zirou now owns this file) | Take ours. Note what still reads `get_preferences()` (section 5) |
| `requirements.txt` | Exact pins, plus `azure-identity` and `cryptography` | Adds `fpdf2` (PDF export) | Your pins plus `fpdf2==2.9.0` |
| `README.md` | Full rewrite | Added "Running locally", the Saved note and "Demo prep" | Keep yours, and append our Brief and Demo prep sections |

Nothing else overlaps. Our other changes are new files only:
- `ui/`
- `tests/test_brief_sections.py`, `tests/test_alerts.py`
- `scripts/brief_section_counts.py`
- `docs/DASHBOARD_REDESIGN.md`, `docs/mockup/`
- `.streamlit/config.toml` (theme)

We didn't touch any `services/*`, `modules/search.py`, `modules/grant_card.py` or workflow file.

**Your backend changes are compatible with our UI.** The new `run_matching` keyword arguments, the `all_records` key, the zero-AI-fit rule, and `opportunity_status` / `deadline_note` are all additive. `ui/view_model.py` reads the same result keys as before.

**Streamlit 1.51 (your pin) is checked:**
- Our UI originally used one newer API: `st.Page(visibility="hidden")` for the hidden AI Help page. Commit 3dad05f makes that page optional, so on 1.51 it's simply not linked.
- With that fix, all pages render without errors on 1.51.
- Our 95 tests pass under Python 3.11, Streamlit 1.51 and pytest, which matches your CI.

## 3. `app.py`: suggested resolution

This keeps the top navigation and adds **My Grants as its own nav item**. Both My Grants and Saved stay until you decide (section 6). `show_my_grants(store=None)` works as an `st.Page` callable as is.

```python
import streamlit as st

from modules.dashboard import show_dashboard
from modules.my_grants import show_my_grants
from modules.profile import show_profile          # Alerts page
from modules.search import show_search
from ui import saved_store
from ui.how_it_works import show_ai_help, show_how_it_works
from ui.nav import PAGES
from ui.saved_page import show_saved
from ui.styles import inject_css

st.set_page_config(page_title="GrantScope", page_icon="ui/assets/nc.svg", layout="wide")
inject_css()
st.logo("ui/assets/logo.svg", size="large")

PAGES.update({
    "brief": st.Page(show_dashboard, title="Brief", url_path="brief", default=True),
    "browse": st.Page(show_search, title="Browse all", url_path="browse"),
    "my_grants": st.Page(show_my_grants, title="My Grants", url_path="my-grants"),
    "saved": st.Page(show_saved, title=f"Saved ({saved_store.count_all()})", url_path="saved"),
    "alerts": st.Page(show_profile, title="Alerts", url_path="alerts"),
    "how": st.Page(show_how_it_works, title="How it works", url_path="how-it-works"),
})
try:  # hidden pages need a newer Streamlit than 1.51; there, AI Help is simply not linked
    PAGES["ai_help"] = st.Page(show_ai_help, title="AI Help", url_path="ai-help", visibility="hidden")
except TypeError:
    pass
st.navigation(list(PAGES.values()), position="top").run()
```

What changes compared with your version:
- `st.title`, `st.caption` and the sidebar radio go away. The logo carries the name and tagline.
- Pages get stable URLs: `/brief`, `/browse`, `/my-grants`, `/saved`, `/alerts`, `/how-it-works`.
- **"Search" becomes "Browse all."** The Brief links to that label ("Try a custom search in Browse all"). If you'd rather keep "Search", rename it in `PAGES` and in two link labels in `modules/dashboard.py`.
- AI Help stays off the nav, matching your removal.

## 4. `modules/dashboard.py`

Take our version, then apply two small edits:

1. **Your `_ai_config`.** Replace the body with `return load_ai_config(st.secrets)`, which brings in your keyless and managed-identity support. `_cached_match`, `_shared_details_cache` and `_shared_ai_cache` are otherwise unchanged from 9c02d3f.
2. **Re-export `assess_effort`.** Your `tests/test_shared_search_handoff.py` asserts `dashboard.assess_effort is effort.assess_effort`. The Brief doesn't call it, so that test fails until you add:
   ```python
   from services.application_effort import assess_effort  # noqa: F401 (shared with Search; see test_shared_search_handoff)
   ```
   The same test's other checks already pass with our file: `run_matching`, `AzureFitEvaluator` and `AzureEligibilityEvaluator` are imported in it.

The Brief no longer uses `modules/grant_card.py`. Your `modules/integrated_search.py` still imports `_evidence_tab` from it, so keep the file.

## 5. `modules/profile.py` (now the Alerts page)

The old Profile form is gone. Its settings duplicated the Brief (agency, days filter) and Search (priorities, minimum award), and the award, score and notification settings weren't applied. The page now holds the weekly digest, instant alerts, saved-grant reminders and a preview. It is session-only and sends nothing yet.

**`get_preferences()` is kept** with the old keys, because two callers still read it:
- `modules/integrated_search.py:24` uses `prefs["agency"]` as Search's preferred agency.
- `modules/search.py` (legacy path) reads `agency`, `priorities`, `deadline_days`, `minimum_award` and `minimum_match_score`.

The Brief no longer reads it. It used to add the old Profile priorities as hidden extra keywords for DEQ; now it searches with strategic-plan terms only, the same for every agency.

To decide:
- **Defaults.** When resolving the conflict, use your `DEFAULT_PREFERENCES` values in our `LEGACY_DEFAULTS`. Your agency is `"Department of Environmental Quality"`; ours still says `"NC Department of Environmental Quality"`. Both resolve to the same profile.
- **Search's preferred agency.** Without a Profile form it stays fixed. One option is for `integrated_search` to read `st.session_state.get("brief_agency")` first, so Search opens on the agency chosen in the Brief.
- **Custom agency and custom priorities** from your Profile go away. Search's own agency selectbox already has `accept_new_options=True`, which covers custom agencies.

## 6. My Grants vs Saved

> **Decision (Nov 8):** we're keeping My Grants and dropping Saved. On `integration`, the Brief's "☆ Save to My Grants" calls Search's own `save_research_record()` with `LocalGrantStore` (adapter: `ui/my_grants_store.py`). Alerts reminders read My Grants, and Saved is off the nav (its files remain, unused). No Search or My Grants code changed. The comparison below is kept for reference.

| | **My Grants** (yours) | **Saved** (ours) |
|---|---|---|
| Where you save from | Search: "Save to My Grants" on result cards | Brief: "☆ Save" on cards and in the detail panel |
| Storage | `services/grant_store.LocalGrantStore`: atomic JSON file at `$GRANTSCOPE_DATA_DIR/grants.json` (default `.grantscope/`) | `ui/saved_store.py`: `st.session_state["saved_grants"]` |
| Lifetime | Survives restarts while the file exists | Lost when the browser tab closes or reloads (labelled "Saved for this session only") |
| Who sees it | **Everyone on the same server instance** (no per-user key) | Only that browser session |
| Key | `agency::opportunity_id` | `agency → opportunity_id` |
| Stored fields | title, federal agency, close date, official URL, **decision** (Pursue/Maybe/Pass), **notes**, project description, research fields | Snapshot of the view model: fit score and tier, section, eligibility, award, cost share, effort, next steps, links, `saved_at` |
| Page features | Decision and notes editing, remove, official link, .ics of selected items | Sort, details panel, Grants.gov and NOFO links, remove, "deadline changed" note, summary PDF, per-grant PDF, .ics, Google Calendar links |
| Calendar export | `services/calendar_export.grants_to_ics`: all-day DTSTART, no reminders | `ui/export_ics.build_ics`: all-day events with DTSTAMP, 14- and 3-day reminders, line folding; skips forecasts and undated items |
| Other users of the data | Search's research workflow (`search_workflow`, `search_research`) | Alerts page (deadline reminders) and the Brief's saved bar |

**Where they overlap:** both are per-agency bookmark lists with a calendar export. A user who saves from both Search and the Brief ends up with two lists and two Save buttons that mean different things. The calendar code also exists twice.

**Agency keys:** both seem to use the OSBM directory names, such as "Department of Environmental Quality", so the same grant should match across both. Worth confirming before you merge the lists.

**Options:**
- **A. Keep both.** No code changes. Consider labels that explain the difference: "My Grants" for the persistent workspace with decisions and notes, "Saved" for this session's shortlist.
- **B. Merge into one list.** Every Saved caller goes through `ui/saved_store.py` (`list_saved`, `is_saved`, `save`, `unsave`, `toggle`, `count_all`). Pointing that module at `LocalGrantStore`, with the snapshot stored in extra fields, would make the Brief write to My Grants. You could then add decision and notes to one page and drop the other nav item. Before doing this for a public deployment, consider that `LocalGrantStore` is shared by every visitor.
- **C. Drop one.** If you drop Saved, also remove its nav entry and the Brief's saved bar, and switch the Alerts reminders to My Grants. If you drop My Grants, Search's save button needs a new target.

## 7. After resolving, a quick check

```bash
python -m pytest -q                      # your suite + ours (tests/test_brief_sections.py, tests/test_alerts.py)
streamlit run app.py                     # Brief, Browse all, My Grants, Saved, Alerts, How it works
```
