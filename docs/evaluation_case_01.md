# Evaluation case 01 — topical match, restricted applicant eligibility

**Date:** 2026-11-07  
**Agency:** North Carolina Department of Environmental Quality (NC DEQ)  
**Opportunity:** FY 2026 Funding Opportunity for Indian Tribes and Intertribal Consortia for Nonpoint Source Management Grants Under Clean Water Act Section 319 (EPA)  
**Evidence source:** Official Grants.gov opportunity detail, viewed in the live Streamlit prototype. The exact opportunity identifier should be recorded from the UI before final submission.

## Observation (live local demonstration)

1. Searching water-related opportunities returned the EPA grant.
2. The prototype gave it a preliminary strategic-topic score of **17/100** based on overlap with the NC DEQ water-quality goal. This is not an eligibility score.
3. On opening official opportunity details, the source text stated: “Eligible applicants ... are federally recognized Tribes and intertribal consortia ...” and referred to additional requirements in Section 2.A.
4. A manually triggered **Azure GPT-4o** review flagged that this restriction may exclude state agencies such as NC DEQ. This is evidence of a useful AI warning, **not** proof that the model made a definitive legal determination.
5. The official text was displayed with raw HTML tags before the formatting fix.

## Root cause and remediation

The original deterministic eligibility screen recognized an exclusive Water Resources Research Institutes rule, but not the explicitly tribal-only applicant clause. As a result, this grant could remain visible as **Needs Review** despite the strong exclusion evidence.

**Code remediation on `feature/search-reliability`:**
- Added a narrowly scoped, evidence-backed eligibility exclusion for **NC DEQ direct applications** when the official detail explicitly says eligible applicants are federally recognized Tribes and intertribal consortia.
- Preserved the source clause in the screen's `evidence` field.
- Left uncertain cases as **Needs Review**. The rule does not generalize exclusions to every state agency, tribal partnership, or grant mentioning Tribes.
- Converted official HTML-formatted description fields into readable plain text before displaying or passing them to AI.
- Added regression tests for the positive exclusion case, an incidental tribal mention, and HTML normalization.

**Expected behavior after local retest:** With official details loaded, the NC DEQ case is flagged **Ineligible for direct application** and hidden by default, while the audit-view toggle permits inspection. The app must still instruct a human to verify the full NOFO, including Section 2.A, before making a funding decision.

## Cost and real-world operating design

Team Azure budget: **$500**. The currently smoke-tested and used deployment is **`grantscope-gpt4o` (GPT-4o)**. We have **not** yet measured token costs or established that a smaller model matches its performance.

To support cost-conscious government operations, use no-cost deterministic retrieval, matching, and evidence rules first. Load official details only for selected records, and invoke paid Azure AI **only on explicit user request**; keep prompts bounded and cache per agency/opportunity in the session. Before operational rollout, benchmark cheaper available models on labeled eligibility false positives, latency, and per-review cost. A budget allocation is not a hard cap; Azure spending controls must be configured separately.

## Verification checklist (not yet executed on this GitHub-only edit)

- [ ] Run `python -m unittest discover -s tests -v` locally.
- [ ] Load the EPA opportunity details for NC DEQ; confirm direct-applicant exclusion and inspect evidence in audit view.
- [ ] Confirm descriptions display without literal `<p>` tags.
- [ ] Verify another opportunity with merely incidental tribal references remains **Needs Review**.
- [ ] Capture screenshots and the official opportunity identifier for final pitch/field notes.

**Scope limitation:** This test validates one real-world failure mode, not statewide agency eligibility or the quality of all AI recommendations.
