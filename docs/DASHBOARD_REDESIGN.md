# GrantScope Dashboard Redesign: "Funding Brief" (spec v2)

This is the source of truth for redesigning the GrantScope Dashboard UI. Read it fully before changing code, and re-read the relevant section before each phase. Mockup screenshots are in `docs/mockup/`, listed in section 15. When the screenshots and this text disagree, **this text wins**.

---

## 0. Context, ownership and boundaries (read first)

GrantScope helps North Carolina state-agency staff find federal grants (live Grants.gov data) that fit their agency's public strategic plan, using rule-based checks plus GPT-4o. Users have very little time.

**Two people work on this codebase:**

- **Partner (do not touch):** the search, matching, scoring and ranking logic. That includes how opportunities are fetched and filtered, how the strategic-fit score is computed, eligibility and AI assessment logic, quote verification, and the order results come back in. **Do not modify, refactor, rename or "improve" any of it**, even if it looks wrong. If you think something there is a problem, write it down in `docs/BACKEND_REQUESTS.md` (section 13) and tell me.
- **Me (your scope):** the Dashboard UI and new UI-side features: layout, cards, detail panel, links, Save/Saved, PDF export and calendar export.

**How to stay inside the boundary:**

- The UI only **reads** the backend's outputs through a thin adapter (`ui/view_model.py`) that converts them into the view model in section 13. Do not change backend function signatures. If you need a value the backend doesn't provide, derive it in the adapter from data that already exists, or fall back to "Not stated". Never compute a new score.
- **Keep the backend's order.** Do not re-sort results. Grouping (section 4) splits the list into sections but preserves the backend's order within each section.
- Existing filters (agency, minimum days to apply) are passed to the existing backend functions exactly as the current UI does. Only the controls look different.
- New code goes in new UI modules. Edit the existing Dashboard page file, but not backend modules.

**Out of scope:** user accounts, assigning grants to colleagues, notifications, multi-user collaboration.

---

## 1. What the redesign is and why

The current Dashboard reads like a research console. Filters, a GPT-4o toggle, metric tiles and raw fields fill the first screen, and the grants themselves sit below the fold. A green "Appears eligible — verify" check, a large "40/100 heuristic", and "Funding: Not reported" / "Effort: Unclear" give users little to decide with. Raw AI errors such as "AI interpretation rejected: Quote not found…" erode trust.

The new Dashboard is a **concise, personalized funding brief**. In about 10 minutes, a user should be able to answer:

1. Which opportunities deserve attention, and why? (fit score, plus a reason naming the plan goal)
2. Can we realistically apply? (eligibility, with evidence status)
3. Is it worth the effort? (award, cost share, effort)
4. What do we do next if we pursue it? (next steps, at the bottom of the detail panel)

**Principles. Apply everywhere, and use them to resolve any case not covered here:**

- **Answer first, evidence on demand.** Cards show conclusions; the detail panel shows reasons; collapsibles show raw evidence.
- **Missing information can lower a recommendation, never raise it.**
- **Every fact carries an evidence status:** **● Confirmed** (found in official text), **◐ Likely** (inferred from listing fields), **○ Not stated** (couldn't find it). This is how we communicate uncertainty without technical language.
- **Hide machinery.** No model names, "heuristic", "semantic", raw AI errors, or duplicated raw fields in the UI.
- **Plain language.** Full dates next to day counts. Name the specific strategic plan goal, never just "Goal 2".
- **Accessible.** Never use color alone: marks are shapes plus text labels. Text contrast at least 4.5:1. Real buttons and links. Visible focus.

---

## 2. Navigation and page map

Top navigation bar (replaces the sidebar radio):

- **Brief:** the new Dashboard (this spec).
- **Browse all:** the existing Search page, unchanged in logic. This is where custom, criteria-based searching lives.
- **Saved (N):** a new page (section 8). N is the number of saved grants.
- **Agency profile:** the existing Profile page.
- **How it works:** a short static page explaining how GrantScope assesses opportunities: data sources, what the fit score means, what ●◐○ mean, the AI's role, and that GrantScope never guarantees eligibility. If the existing "AI Help" page is a chat assistant, keep it reachable (e.g. as a nav item or a link on How it works) and ask me where it should go.

On the left of the top bar: a small filled NC state silhouette (simple inline SVG, **not** the official seal), a thin vertical divider, **GrantScope** in bold, then a smaller muted tagline "Federal Grants Matcher for NC Agencies".

---

## 3. Brief header (screenshot: `01-full-page.png`, top area)

Order and purpose of each element:

1. **Eyebrow "FUNDING BRIEF"** (small, uppercase, muted). Tells users this page is a curated brief, not a raw search.
2. **H1 = selected agency's full name** (e.g. "NC Department of Environmental Quality") with a **"Change agency ▾"** button right next to it. Users sometimes work for several agencies; switching must be one click from the place where the agency is shown. It opens a small list of agencies (from the existing agency list) with the current one marked. Selecting one re-runs the existing pipeline for that agency.
3. **Scope sentence:** "Open federal opportunities matched to your agency's **public strategic plan ↗**, with at least **[ 30 ]** days to apply."
   - "public strategic plan ↗" is a blue, underlined link to the agency's published plan (new tab). It tells users where the matching comes from and lets them check it.
   - **[ 30 ]** is an editable number input (minimum days left, default 30). Changing it immediately re-filters using the **existing** time-to-apply filter. It replaces the old "Time to apply" dropdown, so the filter is readable as a sentence.
   - If the new value excludes opportunities that would otherwise appear, show one muted line below: "3 opportunities have fewer than 70 days left and are not shown." This keeps the filter honest: nothing disappears silently.
4. **Custom search line:** "Looking for a specific program or requirement? **Try a custom search in Browse all**" (underlined link to Browse all). Strategic-plan matching is the default; this is the escape hatch for specific needs. It replaces the old "Advanced filters" panel.
5. **Right side, small and muted:** "Updated today, 5:25 PM ET" with a **"⟳ Refresh data"** button beside it, and below it "142 open opportunities from **Grants.gov** reviewed" (Grants.gov is a link). The number is the count of open opportunities the backend considered. This shows the brief is current and broad, which builds trust. Refresh clears the existing data cache and re-runs the existing fetch; show "Refreshing…" while it runs.

**Removed from the current Dashboard:** the stacked "GrantScope" + "Dashboard" titles; the Agency and Time-to-apply dropdown row (replaced above); the "Advanced filters" expander and the "AI semantic assessment (GPT-4o)" toggle (keep backend defaults); the four metric tiles; the "Live data as of … heuristic" caption; and any summary or count bar above the list.

---

## 4. Groups (sections of the brief)

The brief is split into four sections, in this order:

| Section | Default | Meaning shown to the user |
|---|---|---|
| **Top candidates** | expanded | "Strong fit with your plan, eligibility confirmed, no major facts missing. Sorted by fit score." |
| **Needs a quick check** | expanded | "Good fit, but something important isn't confirmed yet, so the score alone isn't enough. Each one names exactly what to check." |
| **Opening soon (N)** | collapsed | Forecasted opportunities that aren't accepting applications yet. |
| **Lower priority (N) · mostly indirect fit or a known blocker** | collapsed | Everything else that the backend returned. |

**Why groups instead of one ranked list:** a score answers "how well does it match?", but users also need "can we apply, and is anything missing?". Grouping by readiness answers that at a glance, while the score stays visible on every card.

**How to assign groups. This is a presentation-only function; it does not change scores or order:**

- Implement `assign_section(view) -> "top" | "check" | "soon" | "lower"` in `ui/brief_sections.py` as a pure function with unit tests.
- It may only read fields already in the view model (section 13). Rules:
  - **soon:** status is forecasted / not yet open.
  - **top:** fit tier is Strong (≥ 70) AND eligibility is Confirmed AND deadline known AND award known AND no known blocker.
  - **lower:** fit tier is Weak (< 50), OR a known blocker exists (e.g. agency can't be lead applicant, cost share ≥ 1:1).
  - **check:** everything else.
- **If the backend already provides an equivalent classification or priority label, use it instead and tell me.** Keep the thresholds in one config dict so they're easy to adjust with my partner.
- Within each section, keep the backend's order.

**Empty states:**

- No top candidates: show "No top candidates right now. N opportunities need a quick check." in the Top candidates section.
- Nothing at all: "No opportunities match these settings. Try fewer days to apply."

---

## 5. Opportunity card anatomy (screenshot: `01-full-page.png`, left column)

Cards in **Top candidates** and **Needs a quick check** share one layout. Elements, top to bottom:

1. **Title** (bold, about 18px). Left side of the first row.
2. **Federal agency full name**, e.g. "U.S. Environmental Protection Agency (EPA)", under the title. **Do not show the opportunity number on the card**; users told us it carries no meaning. It lives in Sources & method.
3. **Right side of the first row:**
   - "Due Dec 12, 2026" (bold) with "35 days left" (muted) below. For rolling deadlines, show "Rolling through {date}" instead of a huge day count.
   - **Score badge:** a rounded box with a large number "82" plus a small "/100", and below it the tier "Strong fit". Tier colors: Strong is navy text on a light blue tint; Possible is dark text on a neutral gray-blue; Weak is muted text on light gray. The score is the most direct summary, so it stays prominent. The tier word means it doesn't rely on color.
4. **Reason sentence** (about 16px): one sentence explaining the match and **naming the specific plan goal and page**, e.g. "Funds assessment and cleanup of contaminated sites, directly supporting Goal 2: Waste Management and Land Restoration (Strategic plan p. 6)." Use the backend's existing rationale or matched goal data; don't invent goals.
5. **Fact chips** (small pills): `Award: Up to $800K ●`, `Cost share: None ●`, `Effort: Moderate ◐`. Each has its evidence mark plus a screen-reader-only label ("Confirmed"). These answer "is it worth it?" without opening anything.
6. **Needs a quick check only:** an amber box reading **"Unclear ○:** whether a state agency can be the lead applicant, or only a partner." There is exactly **one** primary unknown. It tells users precisely what to check, which turns a vague "verify" into a 2-minute task.
7. **Action row:**
   - **[View details]**: primary, filled navy. Opens this grant in the right panel. When selected, the label becomes "Showing details" and the card gets a navy border.
   - **[☆ Save]**: secondary, outlined. Toggles to **[★ Saved]**. See section 8.
   - **[Grants.gov listing ↗]**: secondary, outlined, opens in a new tab.
   - **[Funding notice (NOFO) ↗]**: secondary, outlined, opens the full Notice of Funding Opportunity (usually the PDF attached to the listing). If no NOFO URL is available, link to the listing's "Related Documents" section or hide the button. Never show a broken link.
   - **Not relevant**: a quiet underlined text button. It hides the card for this session and replaces it with a dashed one-line placeholder: "**{short name}** is hidden from this brief. [Undo]". The placeholder also offers optional one-tap reasons (Not our mission · Award too small · Cost share · No capacity). Reasons are session-only; just keep them in session state. Hiding lets users clear what they've ruled out without changing the backend.
8. **No "Next step" on cards.** Next steps belong at the bottom of the detail panel, because they only matter once the user decides to pursue.

**Opening soon (expanded):** each item shows title, agency, "Forecast only, not yet open", a one-line fit sentence naming the goal, the expected posting date if known, and "View forecast on Grants.gov ↗".

**Lower priority (expanded):** compact rows. Each shows the title, then " · Fit 40/100" in muted text, then "**Why lower:** {one short reason}" on the next line, then a "Grants.gov listing ↗" link on the right. Showing these, rather than hiding them, lets users see what was considered and why it ranked low.

---

## 6. Detail panel (screenshot: `01-full-page.png`, right column)

This is a right-hand column for the selected grant. The first top candidate is selected by default, and ✕ closes the panel. **The section order is deliberate: decision info first, evidence second, action last.**

1. **Header:** grant title (bold, about 20px), agency full name, then two small links: "Grants.gov listing ↗" and "Funding notice (NOFO) ↗". A ✕ close button (aria-label "Close details") sits top right.
2. **Recommendation box.** The background is light blue for Top candidate and light amber for Needs a quick check.
   - Label "RECOMMENDATION · TOP CANDIDATE" (small, uppercase).
   - One or two sentences, e.g. "Strong, direct fit and no blockers found. Worth starting now: the deadline is 35 days away and registration checks take time."
   - On the right, a white score block: "82/100, Strong fit".
   - This is the one-glance verdict. **No explanatory caption under it**; scoring is explained in Sources & method.
3. **"At a glance"**: a 2×2 grid of gray tiles, each with a small uppercase label, a bold value and a muted sub-line:
   - **DEADLINE:** "Dec 12, 2026", sub-line "35 days left"
   - **ELIGIBILITY:** "State agencies eligible" or "Lead role unclear", sub-line "● Confirmed" / "◐ Likely" / "○ Not stated"
   - **EFFORT:** "Moderate" (or Light / Heavy / Not enough info), sub-line the evidence mark
   - **AWARD:** "Up to $800K", sub-line "● Confirmed · about 50 nationally expected" (or "number of awards not stated")

   These four answer "can we, and is it worth it?" before any reading.
4. **"Why it matches your strategic plan · Direct fit"** (or "Related fit"):
   - 1–2 bullets, each naming the goal and page.
   - Below them, a collapsible "See the evidence from both documents". It shows two side-by-side boxes: **YOUR PLAN** (goal title, verbatim plan quote, "Strategic plan p. 6 ↗" link) and **THIS OPPORTUNITY** (program purpose quote, link to the NOFO section).
   - Putting both quotes side by side lets users judge the match themselves, which builds trust.
5. **"Details behind this assessment"**: three collapsibles, all closed by default:
   - **Eligibility · ● Confirmed:** a plain conclusion, a verbatim quote (blockquote), "Source: {where} · view" link, then **What could disqualify you** as bullets (match requirements, lead-applicant rules, geography). Show each fact once; no duplicated raw fields.
   - **Application effort · Moderate:** one sentence on what drives effort, then label/value/mark rows. **Cost share / match** and **Submission process** (single round vs. LOI first) come first, then narrative length, registrations (SAM.gov/UEI, Grants.gov), partners, and so on. Unknown rows show ○ with where to look.
   - **Sources & method:** a plain-language statement: "An AI model drafted this summary. Every quoted fact is checked against the official text; anything we couldn't verify is marked 'Not stated.' Placement in the brief follows fixed rules: missing information can lower a recommendation but never raise it." Then: fit score with a one-line description of what it's based on, the **opportunity number**, the listing retrieval time, the strategic plan reference, and a link to How it works.
6. **"If you decide to pursue"** (light gray box at the bottom):
   - "Suggested next steps, in order." as 2–3 checklist items (session-only checkboxes).
   - Collapsible "Questions for the program officer" listing questions about whatever is unconfirmed.
   - A **[Copy next steps]** button (filled navy).
   - These come last because they're only useful after the user decides to pursue.

**Where the text comes from:** use existing backend outputs where they exist (eligibility reasoning, quotes, verified facts). If the backend doesn't produce recommendation sentences, next steps or questions, generate them in the UI adapter with **simple templates from known facts**. For example, an unknown cost share produces the question "Is a non-federal cost share required?", and a confirmed eligibility plus near deadline produces a "Confirm SAM.gov registration is active" step. Do not add new GPT calls in this phase unless I approve; list them as an option.

**Never show** "AI interpretation rejected…", raw tracebacks, or model names. If the backend's AI reading failed verification, show only the rule-based, verified facts and mark the rest ○ Not stated.

---

## 7. Interaction summary (session state)

| Action | Result |
|---|---|
| View details | sets `selected_id`, highlights the card, fills the panel |
| ✕ in the panel | clears `selected_id`, hides the panel, list goes full width |
| Save / Saved | toggles persistent saved state (section 8); the nav counter updates |
| Not relevant | adds to `hidden` (session); shows placeholder with Undo + reasons |
| Days input | re-runs the existing filter; shows "not shown" line if needed |
| Change agency | switches agency, clears `selected_id` and `hidden` |
| Refresh data | clears cache, re-fetches, updates timestamp |
| Copy next steps | copies the checklist as plain text |

---

## 8. Save and the Saved page (new feature)

**Why:** users want to keep a short list of grants they're seriously considering, come back to it later, share it, and put deadlines on their calendar. This replaces the mockup's session-only "Add to summary" tray. **One concept, "Saved", instead of two**, to avoid confusing users.

**Save button (cards + detail panel header):** outlined "☆ Save" becomes filled-style "★ Saved". Clicking again unsaves it.

**Bottom bar on the Brief:** when at least one grant is saved, show a slim dark bar at the bottom of the brief (or the closest Streamlit equivalent). It reads "{N} saved: {short names}" with buttons **[View saved]** and **[Download summary (PDF)]**.

**Persistence:** saved grants must survive a page reload. There are no user accounts, so store them locally:

- Use a small SQLite file or JSON file under the app's data directory (e.g. `data/saved_grants.json`), keyed by agency.
- Save a **snapshot** of the view-model fields needed for display and export (title, agency, deadline, award, cost share, effort, eligibility, fit score and tier, section, reason, next steps, questions, links), plus `saved_at`. The Saved page then works even if the listing changes or closes.
- When the item is present in fresh backend data, show the fresh values. If the deadline changed since saving, show a small "Deadline changed" note. If it's no longer in the data, show "No longer listed as open".
- Put this in `ui/saved_store.py` with simple functions: `list_saved(agency)`, `save(agency, view)`, `unsave(agency, id)`, `is_saved(agency, id)`.
- Add a note in the README that saved data is local to this deployment.

**Saved page layout:**

- H1 "Saved opportunities", with a subtitle "{agency} · {N} saved".
- Toolbar: **[Download PDF]** (all saved) · **[Export to calendar (.ics)]** (all saved) · sort by **Deadline (soonest first)** (default) or **Date saved**.
- One compact card per saved grant: title, agency, deadline and days left (or "Closed"), score badge, section label (Top candidate / Needs a quick check / …), the award/cost share/effort chips, and the reason sentence. Actions: [View details] opens the same detail panel layout on the right, [Grants.gov ↗], [NOFO ↗], [Add to Google Calendar ↗], and [Remove].
- Optional checkboxes to select a subset, so users can export only the selected items.
- Empty state: "Nothing saved yet. Use ☆ Save on any opportunity in your brief."

---

## 9. Export: PDF summary

Generated on demand from the Brief bottom bar (all saved) or from the Saved page (all or selected). **Multi-page is fine.**

- Library: `fpdf2` or `reportlab` (pick whichever installs cleanly; prefer `fpdf2` for simplicity).
- **Font:** embed a TTF that supports the characters used (e.g. DejaVu Sans), **or** replace ●◐○ with words in the PDF ("Confirmed", "Likely", "Not stated"). Don't let the PDF show missing-glyph boxes.
- **Cover/header:** "GrantScope · Funding summary", agency name, generated date and time, data source line ("Grants.gov, retrieved {time}"), number of opportunities.
- **Overview table:** one row per grant with title, deadline, award, fit score/tier, and section.
- **Per grant:**
  - title, agency, recommendation label and sentence, fit score
  - the at-a-glance facts with evidence words
  - why it matches (goal + page)
  - what's unclear (if any)
  - next steps (numbered) and questions for the program officer
  - links (Grants.gov, NOFO, strategic plan) as clickable links
- Footer on every page: "GrantScope never guarantees eligibility. Confirm with the official announcement." plus page numbers.
- Filename: `GrantScope_{AgencyShort}_saved_{YYYY-MM-DD}.pdf`. Serve with `st.download_button`.

---

## 10. Export: calendar

- **Export to calendar (.ics):** one `.ics` file with a VEVENT per saved grant that has a known deadline.
  - Use the `icalendar` package, or hand-write valid iCalendar text.
  - Summary: "Deadline: {short title} ({agency abbreviation})"
  - Date: the deadline. Use the time if known, in America/New_York; otherwise make it an all-day event.
  - Description: the award, the reason sentence, and the Grants.gov and NOFO URLs. URL field: the Grants.gov listing.
  - Two VALARM reminders: 14 days and 3 days before.
  - Stable UID per opportunity (e.g. `{opportunity_id}@grantscope`), so re-importing updates rather than duplicates where calendars support it.
  - This works with Outlook, Apple Calendar and Google Calendar (import).
- **Per-grant "Add to Google Calendar ↗":** a template link: `https://calendar.google.com/calendar/render?action=TEMPLATE&text=...&dates=YYYYMMDD/YYYYMMDD&details=...`. URL-encode all parameters.
- Grants without a known deadline (rolling, forecast) are skipped, with a note: "2 saved items have no fixed deadline and weren't added."

---

## 11. Writing guidelines

| Avoid | Use |
|---|---|
| 40/100 Strategic fit · heuristic | 40/100 · Weak fit, with a plain reason |
| ✓ Appears eligible — verify | ◐ Likely eligible: state agencies are listed; confirm program-specific rules |
| Funding: Not reported | Award: Not stated ○ (say where to look, e.g. NOFO §II) |
| Effort: Unclear from summary | Effort: Not enough info ○, naming the unknown drivers |
| 693 days left (rolling BAA) | Rolling through Sep 30, 2028 |
| Opportunity number on cards | Full federal agency name |
| "Full announcement" | "Funding notice (NOFO)" |
| "Supports DEQ Goal 1" | "Supports Goal 1: Environmental and Public Health Protection (p. 4)" |

Write at about an 8th-grade reading level. Say "the listing says" rather than "you are eligible". Never use "guaranteed".

---

## 12. Visual style

- **Font:** Public Sans (Google Fonts) with a `system-ui, sans-serif` fallback. Body 15px. Card titles 18px. H1 30px.
- **Colors:**
  - text #1B2230; secondary #3A4352; muted #4B5565
  - borders #D9DEE5; page background #F5F6F8; cards #FFFFFF
  - accent navy #1F4E9C (hover #163A75); accent tint #EAF0FA
  - amber text #7A4300 on #FDF1DC (Needs a quick check, Unclear)
  - neutral tint #EEF1F5 (Possible fit)
  - focus ring 3px #E59A00
- **Shapes and spacing:**
  - Cards: 1px border, 12px radius, 20–24px padding, 12px gap between rows. The selected card has a navy border.
  - Buttons: at least 40–44px tall, 8px radius. Primary is filled navy with white text; secondary is a white background with a 1px #B8C0CC border.
  - Chips: pill shape, #F5F6F8 fill, 1px #E3E7EC border, 14px text.
- No emoji (no ✅). Use the text marks ● ◐ ○ ★ ☆ and simple inline SVG icons.

---

## 13. Data contract (view model)

`ui/view_model.py` converts backend output into an `OpportunityView` dataclass. **This is the only place the UI touches backend data.**

```
id, title, short_name, agency_full_name, opportunity_number
status: "open" | "forecasted" | "closed"
deadline_date (date|None), days_left (int|None), is_rolling (bool), rolling_until (date|None)
submission_type + status            # single round / rolling / LOI first
fit_score (0-100), fit_tier ("Strong"|"Possible"|"Weak"), fit_level ("Direct"|"Related"|"Indirect")
matched_goals: [ {number, title, page} ], fit_reasons: [str], plan_quote, grant_purpose_quote
eligibility_status ("Confirmed"|"Likely"|"Not stated"), eligibility_short, eligibility_conclusion,
eligibility_quote, eligibility_source, disqualifiers: [str]
award_text + status, expected_awards_text + status, cost_share_text + status
effort_level ("Light"|"Moderate"|"Heavy"|"Not enough info") + status, effort_note,
effort_drivers: [ {label, value, status} ]
section ("top"|"check"|"soon"|"lower"), recommendation_label, recommendation_sentence,
unclear_reason (check only), why_lower (lower only)
next_steps: [str], officer_questions: [str]
grants_gov_url, nofo_url (optional), plan_url, plan_page
retrieved_at
```

**Rules:**

- Every field that can't be filled from existing data gets a safe fallback (`"Not stated"`, `None`, or an empty list), and the UI handles it gracefully: hide the element or show ○ Not stated. **Never fabricate values.**
- Quotes must come from the backend's verified quotes only.
- Create `docs/BACKEND_REQUESTS.md` listing every field that is currently missing or weak, why the UI needs it, and the fallback in use. I'll share it with my partner. Do not implement those backend changes yourself.

---

## 14. Streamlit implementation notes

Check the installed version first and adapt.

- **Page setup:** `st.set_page_config(layout="wide")`.
- **Navigation:** top navigation via `st.navigation(..., position="top")` if supported; otherwise the closest option. Show the Saved count in the label.
- **Layout:** brief + panel via `st.columns([3, 2], gap="large")`. When no grant is selected, render the brief full width.
- **Cards:** `st.container(border=True)` + `st.markdown(html, unsafe_allow_html=True)` for title/agency/date/score/reason/chips. Use real `st.button` for View details, Save and Not relevant, and `st.link_button` for external links. Use widget keys like `f"view_{id}"`.
- **Agency switcher:** `st.popover("Change agency")`, falling back to a compact `st.selectbox`.
- **Days filter:** `st.number_input(min_value=0, step=1, label_visibility="collapsed")` in a columns row, to approximate the inline sentence.
- **Collapsibles:** `st.expander` for Opening soon, Lower priority, the evidence block, the three "Details behind" items and the officer questions.
- **Copy:** `st.code(text, language=None)` (has a copy button) or a tiny `components.html` clipboard helper.
- **Downloads:** `st.download_button` for PDF and ICS.
- **CSS:** one `ui/styles.py` with `inject_css()`, called once per page. Prefer your own classes inside markdown HTML; avoid depending on fragile internal Streamlit class names where possible.
- **Bottom bar:** a true sticky footer is fragile in Streamlit. Acceptable fallback: render it at the end of the brief column, and also show a "Saved (N)" counter in the nav.
- **Caching:** reuse the existing caching. Rendering must not trigger new backend or LLM calls. Building view models must be cheap.
- **Module layout (suggested):**
  - `ui/view_model.py`, `ui/brief_sections.py`, `ui/components/card.py`, `ui/components/detail_panel.py`
  - `ui/saved_store.py`, `ui/export_pdf.py`, `ui/export_ics.py`, `ui/styles.py`
  - pages: `brief.py`, `saved.py`, `how_it_works.py`
- **Tests:**
  - `tests/test_brief_sections.py` (every rule, including "missing info never upgrades")
  - `tests/test_view_model.py` (fallbacks)
  - `tests/test_exports.py` (PDF builds with unicode text; ICS is valid and skips no-deadline items)
  - `tests/test_saved_store.py`

---

## 15. Screenshots and acceptance checklist

**Screenshots in `docs/mockup/`:**

- `01-full-page.png`: the full Brief with the detail panel open (header, Top candidates, Needs a quick check, panel)
- (optional) `02-panel-expanded.png`: detail panel with Eligibility / Application effort / Sources & method / evidence expanded
- (optional) `03-collapsed-sections.png`: Opening soon and Lower priority expanded, plus a hidden-card placeholder
- (optional) `04-change-agency.png`: the agency menu open

**Acceptance checklist:**

- [ ] **No changes to backend search, matching, scoring, ranking or eligibility modules** (verify with `git diff --stat`).
- [ ] At 1440×900, the first screen shows the brief header, the first top candidate card, and the detail panel. No filter panels or metric tiles.
- [ ] Sections and empty states behave as in section 4, and the backend order is preserved within each section.
- [ ] Cards follow section 5 exactly: full agency name, goal named in the reason, score badge with tier, chips with marks, Unclear box for check items, and the actions row. No next step on cards.
- [ ] The detail panel follows section 6, in that exact order.
- [ ] Grants.gov, NOFO and strategic plan links open correctly or are hidden when unavailable.
- [ ] Save persists across reload; the Saved page works with sorting, View details and Remove.
- [ ] PDF exports (multi-page) with no missing glyphs and with clickable links.
- [ ] The .ics file imports into Google/Outlook with reminders; the Google Calendar link works.
- [ ] Days input, Change agency, Refresh, Not relevant/Undo and Copy next steps all work.
- [ ] No raw AI errors, duplicated fields or model names in the UI.
- [ ] Browse all (Search), Agency profile and AI Help still work.
- [ ] `docs/BACKEND_REQUESTS.md` exists and lists missing fields with fallbacks.

Notes on these mockup screenshots. Where they differ from DASHBOARD_REDESIGN.md, the spec wins.

1. Cards show "Add to summary" / "In summary ✓". This is replaced by "☆ Save" / "★ Saved" (spec section 8). There is no session summary tray; use the Saved bottom bar and the Saved page instead.
2. Text in [square brackets], e.g. "[Excerpt from DEQ Strategic Plan …]", is placeholder text. Real quotes must come from the backend's verified quotes; if none exists, hide the quote.
3. All grant names, amounts, dates, scores and goals are sample data. Never hard-code them. The goal names (e.g. "Goal 2: Waste Management and Land Restoration") are placeholders for the agency's real plan goals.