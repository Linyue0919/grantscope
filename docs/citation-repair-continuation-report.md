# Citation repair and bounded continuation report

November 7, 2026. **Stopped after two new paid calls: one validated Sol decision and one rejected fresh GPT-5.5 analysis.** No retry, redeployment, other case, production edit, cache rewrite, credential change, commit or push. Historical results remain unchanged.

## Offline diagnosis of the original rejected responses

Both original analysis requests completed with HTTP 200. Under their original strict validator, both remained failed; they were not retroactively recorded as successful calls.

| Disjoint claim/citation category | Original GPT-5.5 | Original Sol |
|---|---:|---:|
| Exact attributed-source quotation | 12 | 11 |
| Whitespace-only mismatch | 19 | 17 |
| Unknown source ID / broken source mapping | 0 | 0 |
| Wrong-source attribution | 1 | 0 |
| Missing quotation on an attributed claim | 0 | 0 |
| Uncited inference violating claim policy | 1 | 0 |
| Other semantic quotation mismatch observed | 0 | 0 |
| Explicitly labeled uncited uncertainty, allowed | 3 | 5 |
| Total claims including counterevidence | 36 | 33 |

These categories describe quotation/provenance/policy checks, not human-adjudicated truth or entailment. The uncited inference is a blocking provenance failure, not proof the project-context statement is factually false. No complete semantic claim audit is claimed.

Concrete sanitized examples:

- Formatting: the NOFO wraps `restoration of\nlandscapes`; the output quoted `restoration of landscapes`. This is now a match within that same attributed source.
- Original GPT-5.5 purpose quotation beginning “The purpose of the Landscape Scale Restoration (LSR) Program” is present in the Grants.gov synopsis but attributed to `official-364144-notice`. This remains blocked. Neither its source ID nor its text was repaired.
- GPT-5.5's statement that the project is mainly sensors/monitoring was labeled `reasoned_inference` with null source and an empty quote. The contract only allows uncited `unresolved_requirement` claims. It remains blocked, without relabeling or inventing a project citation.

## Conservative repair and safety boundary

Added `research_foundation/citations.py`, shared by independent benchmark validation. Canonicalization uses **Unicode NFC** followed by whitespace collapse. That handles CRLF/LF, nonbreaking spaces, repeated spaces and canonically equivalent composed accents. It does not use compatibility folding, case folding, punctuation substitution, synonym/fuzzy matching or word deletion. Numbers, dates, negations and eligibility qualifiers are retained.

Each quotation is checked **only against its specifically attributed source**. Unknown/duplicate source identities fail. Frozen packet construction verifies manifest/raw/text hashes. Cross-source searching was used only for offline diagnostic classification; it never accepts or rescues a claim. Raw quote, normalized quote, raw-match boolean, normalized-match boolean, category and pass/fail are retained per claim.

Uncited inferences and unqualified material eligibility/readiness/allowability assertions remain blocking. Explicit uncertainty is permitted only under the uncertainty claim policy. These are conservative deterministic checks, **not an automated general entailment judge**. An authentic quotation may still be irrelevant or fail to prove a compound claim; independent human review remains necessary.

Revalidation of complete original outputs:

| Result under corrected validator | GPT-5.5 | Sol |
|---|---|---|
| Formatting failures resolved | 19 | 17 |
| Wrong-source failures remaining | 1 | 0 |
| Uncited-inference failures remaining | 1 | 0 |
| Complete original analysis passes now | No | Yes |
| Historical original record changed | No | No |

Regression coverage includes line breaks, CRLF, NFC accents/NBSP, wrong sources, missing/unknown citations, changed dates/amounts, removed negation, changed eligibility qualifier, valid quotations, unsupported material inferences and explicit uncertainty. There is no compatibility folding of numeric characters such as circled digits/fractions. The continuation order and whole-run transport fail-stop are also mocked offline.

## Authorized continuation and provenance

The user explicitly authorized reusing an original analysis only if it passes the corrected validator, at most one new GPT-5.5 analysis, then its decision only on validation success. Four new calls were the outer limit; this path needed at most three. Before execution, the cache-aware conservative reference-price bound was **$2.57**, below $15. No extra probe was run.

Executed order:

1. Revalidate Sol's original analysis offline; send it unchanged with the original packet to Sol's decision stage.
2. Send one fresh GPT-5.5 analysis with the same frozen project/agency/evidence packet and a generic prospective citation-policy instruction. No historical mistakes, GPT-4o scores, Sol answers or reviewer conclusions were included.
3. GPT-5.5 failed a real source-attribution check; skip its decision and stop its path. No retries.

This is a continuation, **not a symmetric fresh paired benchmark**: Sol reused an older analysis, while GPT-5.5 received a generic updated citation instruction. It cannot establish comparative model superiority.

Continuation contract:
`c5b06e5396216e2bc6a943c58a0c102112f9f3048cf2cb36905b170f7fc850c9`

The contract binds the validator, harness, smoke helper, continuation driver, source packet and original artifact hashes. Original events/requests/contract hashes still match. Both existing benchmark deployments and production deployment metadata were identical before and after; no Azure PUT/DELETE was performed in this continuation. API remained v1 Chat Completions, medium reasoning effort, caps 25,000 analysis / 8,000 decision including reasoning, concurrency one, 10-second connect / 180-second read timeout, no redirects or automatic retry.

## Final model results

| Outcome | GPT-6.1 Sol | GPT-5.5 |
|---|---|---|
| Analysis used | Original, separately revalidated under corrected contract | One fresh analysis |
| Analysis quotation checks | 28/28 cited quotations match the attributed source; 5 allowed uncertainty claims | 27/28 cited quotations match; 9 allowed uncertainty claims; 1 wrong-source quotation blocks the whole analysis |
| Decision stage | Completed and structurally/consistency validated | Not called |
| Application viability | **CONDITIONAL** | **No final classification** |
| Can Apply | `needs_review` | No final answer |
| Should Apply | `conditional_lead` | No final answer |
| Act in Time | `potentially_in_time`, with readiness explicitly unproven | No final answer |
| Project / strategy relevance | 45 / 75 | No scores generated |
| Confidence | Medium relevance confidence, not confirmed eligibility | No decision confidence generated |

Sol explicitly says this is a lead for targeted verification, not a recommendation to submit the current project. Its conditions include:

- Confirm DEQ meets the full notice's “appropriate/equivalent State agency” requirement; the broad state-government synopsis is insufficient.
- Define a qualifying measurable forest-restoration accomplishment and show how monitoring supports it. Sensor deployment alone does not establish suitability.
- Verify rural forest land, ownership and site eligibility; generic rural watershed geography is insufficient.
- Establish State Forest Action Plan/equivalent strategy alignment and agreed partner roles.
- Obtain State Forester sponsorship/capacity and send draft narrative/budget by **December 17, 2026**, before **January 26, 2027, 11:59 p.m. Eastern** final submission.
- Prepare a **$100,000–$300,000** single-state federal request and allowable **1:1 nonfederal match**.
- Review equipment/restoration nexus, installation costs, registrations, application materials, three-year implementation and missing amendments/forms.

It does not invent an eligible alternate lead; it recommends verifying whether such a route is permissible. It distinguishes future dates from application readiness. Its verified strategy basis is limited to supplied DEQ excerpts, not a complete strategic-plan review.

Fresh GPT-5.5 independently identifies forest-land restrictions, on-the-ground outcomes, appropriate agency status, sponsorship, match and both deadlines. It corrects its earlier purpose source attribution and uncited-inference policy issue. However, it newly attributes a sentence beginning “Federal funds and cooperator match cannot be used for construction” to the NOFO; the exact sentence is in the **fact sheet**. This is not whitespace-only, and the validator correctly blocks it. No human or code relabeled that source.

Additional human-review concerns: GPT-5.5 marks activity fit `conflicting` despite unspecified restoration work, which may overstate an unresolved condition. Its fresh analysis does not explicitly extract the federal award range and three-year completion condition. Sol covers those but its compound claims/next actions still need source-entailment review; passing quote and consistency checks is not independent eligibility certification. No missing amendment was claimed reviewed.

Official sources: [NOFO](https://apply07.grants.gov/grantsws/rest/opportunity/att/download/355360) pp4–14, [fact sheet](https://apply07.grants.gov/grantsws/rest/opportunity/att/download/355402), and [opportunity 364144](https://www.grants.gov/search-results-detail/364144). Local provenance and originals remain unchanged under `docs/ai-research-benchmark/pilot/sources/`.

## Actual incremental telemetry and cache-aware cost

| New call | UTC start → end | Elapsed | Input | Output including reasoning | Reasoning subset | Cache writes | Reference estimate |
|---|---|---:|---:|---:|---:|---:|---:|
| Sol decision | 23:46:51.628380 → 23:47:10.194785 | 18.563 s | 19,425 | 1,001 | 71 | 19,422 | $0.058571 |
| GPT-5.5 fresh analysis | 23:47:10.843666 → 23:47:56.591688 | 45.746 s | 16,510 | 5,205 | 2,108 | 0 reported | $0.238700 |
| Total | Both HTTP 200 / finish `stop` | 64.309 s summed request time | 35,935 | 6,206 | 2,179 | 19,422 | **$0.297271** |

Reasoning is already included in output counts; no double charge. Neither request timed out or truncated. Cache-aware costs partition ordinary input, cache reads and cache writes at replacement rates; cache writes are not charged on top of ordinary input for the same tokens. At public short-context reference rates, Sol uses $2 ordinary input/$2.50 default 30-minute cache-write/$10 output; GPT-5.5 uses $5 input/$30 output per million tokens. Cache reads were zero in both calls. Actual subscription tariffs/taxes/credits remain unverified.

Including the original smoke calls: GPT-5.5 totals **$0.432920** across two rejected analyses; Sol totals **$0.1346695** across its original analysis and accepted decision; all four actual paid calls total approximately **$0.5675895**. These are usage-based estimates, not an invoice. No numerical quality or accuracy claim follows from cost differences.

Cost helper/reservation now includes cache-write pricing and rejects invalid/ambiguous counters or cost above reservation. [Microsoft cache accounting/default TTL](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching), [Sol public rates](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/introducing-gpt-6-1-sol-in-microsoft-foundry-advanced-intelligence-optimized-for/4560811), [cache-write replacement accounting](https://developers.openai.com/api/docs/guides/prompt-caching).

## Artifacts and validation

Historical artifacts and their original failure statuses are untouched at `/tmp/grantscope-smoke-20261107-results/`. New contract, full raw responses, requests, per-claim comparisons, usage, latency, derived summary and deployment snapshots are private at `/tmp/grantscope-citation-continuation-20261107/`. Directory 0700/files 0600 verified; authorization headers and known token values are not stored. No exposed key was tested or changed.

**113 offline tests passed before inference**, including all normalization, negative-evidence and continuation tests. Compilation/diff checks passed. Protected app, Dashboard, production semantic service and recommendation-cache SHA-256 match the prior snapshots; no production Search/service file was edited.

Changed files this task: `research_foundation/citations.py`, `scripts/benchmark_ai_research.py`, `scripts/continue_ai_research.py`, `tests/test_citation_normalization.py`, `tests/test_continue_ai_research.py`, cache-aware assertions in `tests/test_benchmark_ai_research.py` and `tests/test_smoke_ai_research.py`, plus this report. Full-benchmark old approval hashes are invalidated; no full benchmark was enabled or run.

## Stop and interpretation

Sol's conditional brief and both raw analyses are suitable for independent human evaluation with limitations attached. GPT-5.5 has no validated final decision. Neither model is declared the winner; no measured accuracy, recall, time savings or impact is claimed. Quote fidelity, compound-claim entailment, missing restrictions and final viability must be evaluated separately.

No further inference or deployment work is authorized by unused call slots. A broader experiment would need a new explicit scope/contract, completed human reference labels and prospective handling of source attribution. Production integration remains out of scope; existing Search/Dashboard demo risks and owner-coordinated key rotation remain unresolved. No browser/product acceptance claim is made.
