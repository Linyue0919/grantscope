# GrantScope — Evaluation & Field Notes

**Event:** UNC Solve-A-Thon 2026 — Federal Funds Matchmaker  
**Status:** Living evaluation log; evidence and fixes must be checked before the final submission.  
**Source of observations:** Local Streamlit Search screenshots and Grants.gov official detail text, November 7, 2026.  
**Scope:** NC agency profiles against federal funding opportunities. Topic relevance is NOT eligibility or likelihood of award.

## Evaluation protocol

For each test, record (1) selected NC agency and user search, (2) grant title/official link or opportunity ID, (3) system output, (4) official source evidence, (5) expected behavior, (6) severity, (7) proposed fix, and (8) post-fix retest. Do not mark a fix as verified without a rerun.

| ID | Area | Status | Severity | Observed issue / evidence | Expected behavior / fix | Retest |
| --- | --- | --- | --- | --- | --- | --- |
| E-001 | Semantic matching | **Observed; fix pending** | High | With NC Department of Environmental Quality (DEQ) selected, “F26AS00030 Cooperative Endangered Species Conservation Fund: Recovery Land Acquisition Grant Program” received **17/100**. Explanation matched generic **“recovery”** to DEQ's *disaster recovery / flood resilience* goal. Here “recovery” concerns endangered species, not disaster recovery. Screenshot: local Search, Nov 7. | Avoid ambiguous standalone keywords; require context (e.g., “disaster recovery” or “flood recovery”), and test unrelated meanings. A match must be supported by the relevant goal context. | Not run |
| E-002 | Applicant eligibility | **Official restriction verified; classifier fix pending** | **Critical** | With NC DEQ selected, the Geological Survey **Water Resources Research Act Program National Competitive Grants FY2026 (104g General)** appeared in water-related results. Grants.gov detail response showed **award floor $0**, **ceiling $120,000**, applicant type **“Others (see text field entitled 'Additional Information on Eligibility' for clarification)”**. Official eligibility notes say **“Only Water Resources Research Institutes established under the Water Resources Research Act of 1984 are eligible to apply.”** Thus NC DEQ is not an eligible *direct applicant* under that stated restriction. | Surface **Ineligible for direct application** with quoted official restriction and source. Keep strategic relevance separate from eligibility. Do not recommend as directly actionable for DEQ; preserve possibility of research partnership only if separately supported. | Not run |
| E-003 | Search completeness | **Known limitation** | Medium | Search requests only the first **100** Grants.gov search records; UI warns results are **not exhaustive**. | Add pagination and transparent result counts; test that later pages are not silently omitted. | Not run |
| E-004 | Deadline completeness | **Observed; fix pending** | Medium | In a local search, the UI warned **18 records had missing or unrecognized deadlines**. | Preserve unknown deadlines as unknown, never infer a date; test sorting and the include-unknown toggle. | Not run |
| E-005 | Award coverage | **Partial success; limitation remains** | Medium | Clicking **Load official award & eligibility details** successfully returned a real award floor/ceiling for E-002. The amount filter applies only to grants whose details have already been loaded, not the entire result set. | Make filter scope explicit; eventually fetch verified details for all candidates or use a clearly labeled partial-data mode. | Not run |
| E-006 | Agency strategic-plan coverage | **Incomplete** | High | Agency selector currently has **33 manually entered directory records**, but only **DEQ and OSBM** have preliminary goal records. The 33-record snapshot and goal paraphrases have **not yet been comprehensively cross-checked against all official OSBM plan PDFs**. | Reconcile the full agency list against the official directory; extract source-grounded goals for every available plan, with plan URLs/page citations; mark unavailable plans explicitly. | Not run |

## Successful functional checks (observed, not automated)

- **T-001 Search:** Local Streamlit Search returned live Grants.gov records and displayed federal agency and closing date (e.g., Geological Survey closing Nov 12, 2026; Fish and Wildlife Service closing Nov 20, 2026). **Observed working.**
- **T-002 Matching UI:** DEQ result card displayed a preliminary strategic relevance score, matched terms, and plan source link. **UI working; relevance quality failed E-001.**
- **T-003 Details API:** Clicking the official detail button displayed award floor **$0**, ceiling **$120,000**, applicant category, and full eligibility notes for the Water Resources Research Act example. **Observed working; classification not implemented.**

## AI-assisted development / error attribution

The assistant helped draft code for Search, official API detail retrieval, initial keyword matching, and strategic goal records. E-001 is a **deterministic keyword-matching failure**, not proof of an LLM hallucination. E-002 is a **missing eligibility-classification safeguard**, not a demonstrated incorrect response from Grants.gov. Earlier design incorrectly scoped agency profiles to three pilot agencies; the user explicitly corrected this to **all agencies**, and the selector was expanded to 33 unverified snapshot entries. These distinctions matter for accurate GenAI Field Notes.

## Outstanding actions before submission

- [ ] Fix E-001 with contextual terms and regression test.
- [ ] Implement conservative evidence-backed eligibility status: Eligible / Ineligible / Needs Review. Unknown must not be called eligible.
- [ ] Re-test E-002 against official details and record exact grant ID/link.
- [ ] Verify agency inventory and strategic goal evidence against OSBM official plans.
- [ ] Evaluate at least one genuine positive match and one negative match after fixes.
- [ ] Record screenshots, commit hashes, and any actual before/after results.
- [ ] Assess E-003/E-004 limitations honestly in presentation.

## Source links

- OSBM strategic plans directory: https://www.osbm.nc.gov/operational-excellence/strategic-planning/agency-strategic-plans
- Grants.gov: https://www.grants.gov/
- Development branch: https://github.com/Linyue0919/grantscope/tree/feature/search-reliability

**Evidence policy:** This log contains observed screenshot results and clearly labeled inferences. It does not claim comprehensive verification, successful fixes, or a completed eligibility engine.

## Remediation commits — November 7, 2026

| Case | Change made | Commit | Verification state |
| --- | --- | --- | --- |
| E-001 | Removed ambiguous standalone `recovery` and other overly broad disaster terms from the DEQ goal lexicon; added contextual disaster/flood recovery phrases. | `dbb03d5` | **Pending local regression execution and UI retest** |
| E-002 | Added `services/eligibility.py` conservative screening for an explicit institute-only applicant restriction when DEQ is selected; Search now displays Ineligible with quoted evidence for that specific rule, otherwise Needs Review. | `8737494`, `0f142af` | **Pending local regression execution and UI retest** |
| Both | Added five `unittest` regression cases: negative semantic match, positive contextual match, institute-only exclusion, no unsupported Eligible claim, and missing-details review. | `6b94af3` | **Tests committed, not yet executed** |

### How to reproduce and verify

```bash
git pull origin feature/search-reliability
python -m unittest discover -s tests -v
python -m streamlit run app.py
```

Then select NC DEQ, search for `water`, load official details for the Water Resources Research Act opportunity, and check whether **Ineligible for direct application** appears. Search for `recovery` and confirm that the endangered-species Recovery Land Acquisition opportunity does **not** match the disaster-recovery goal. Note that other DEQ goals could still match a different opportunity for independent reasons. Save screenshots and test output before marking E-001/E-002 as verified.

**Scope caveat:** The eligibility rule recognizes one explicit exclusion pattern only; it does not establish general applicant eligibility. The semantic matcher remains a transparent keyword heuristic, not a validated AI semantic model.

## Batch screening iteration — November 7, 2026

**Change:** Added an explicit `Screen next 10 grants using official eligibility details` action to Search. The app fetches details for at most 10 previously unscreened candidates per click, caches successful responses, reports the number checked, and retains unknown/error cases as Needs Review. Confirmed ineligible results are hidden by default unless audit view is enabled.

**Commit:** `f5e2cd8`.

**Verification status:** **Not yet locally tested.** Confirm the batch button loads official details, that progress counts update, that confirmed ineligible results disappear by default, and that audit view restores them. Inspect terminal for errors. This is bounded manual batch screening, **not** unattended or exhaustive auto-classification; the classifier still recognizes a narrow explicit-exclusion pattern.

**Future evaluation:** Measure official detail coverage, API failures, false positives, and false negatives on a manually labeled sample. Avoid claiming 100% coverage.

## E-007 — Excess zero-score results (Nov 7, 2026)

**Observed by user:** Search displayed many grants with strategic relevance **0/100**. **Root cause found in code:** matching used a strict set of keyword overlaps on grant title/short search text; a grant received zero if no configured goal term appeared, regardless of semantic relevance or missing descriptive data. The UI did not suppress or distinguish these results.

**Fix committed:** `d2cb9e8` includes official detail descriptions when available; `646d60c` hides zero-evidence results by default but preserves an audit toggle; `101a6bb` adds tests for detail-enriched matches and unscored agencies.

**Interpretation:** Zero means **no lexical evidence under this prototype**, not evidence of actual irrelevance. Agencies without loaded goal profiles have `None` (unscored), not zero. These changes improve transparency but **do not constitute semantic AI matching**.

**Verification:** Pending execution of seven regression tests and Streamlit UI retest. Check that hidden counts and audit view behave correctly, and that loading details can increase relevance when appropriate.
