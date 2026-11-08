# Dashboard citation repair — November 8, 2026

## Historical evidence and limits

The public deployment reported 9 rejected strategic-fit responses out of 12, and one rejected eligibility response. The production evaluator retained only shortened error strings, not complete raw rejected responses. The original nine raw outputs cannot be reconstructed faithfully; no claim is made that a later response is the original one. Private public-browser evidence contains five visible fit rejection messages and the eligibility rejection.

A controlled real-Azure reproduction captured complete prompts, source texts, raw outputs, completion status and usage outside Git. It used the normal Dashboard matching path (DEQ, default 30-day filter, eight queries, 60 detail lookups, 12 fit assessments and 15 eligibility assessments). This reproduced eight fit rejections and one eligibility rejection. Model variability and the different retrieval time explain why this is not an exact replay of the historical nine.

| Fit opportunity | Reproduction before fix |
|---|---|
| 361080 | Accepted |
| 362034 | Accepted |
| 362715 | Rejected: rewritten grant excerpt and goal punctuation |
| 362755 | Accepted |
| 362978 | Accepted |
| 362979 | Rejected: added sentence-ending period to a partial goal excerpt |
| 363616 | Rejected: added sentence-ending period to a partial goal excerpt |
| 363699 | Rejected: rewritten grant wording and goal punctuation |
| 363878 | Rejected: combined/reworded grant and goal excerpts |
| 363958 | Rejected: added sentence-ending period to a partial goal excerpt |
| 364099 | Rejected: replaced goal continuation with a period |
| 364144 | Rejected: replaced grant and goal continuations with periods |

All 12 fit responses finished normally (`stop`). Their full descriptions were below the 5,000-character input cap; none was truncated. Rejected quotes were absent even from the full official fields. Agency goals were supplied in full. For example, the source continues `standards and by providing ...`; the model returned `standards.`. Accepting that by fuzzy matching or stripping arbitrary punctuation would misrepresent the source. The existing validator was correct to reject it.

The eligibility reproduction for 363844 combined category labels and changed quotation punctuation inside the official Others label. It was not a missing-source or transport failure.

## Targeted fix

The fit model now selects one supplied grant excerpt ID and at most two goal/excerpt pairs. The application resolves each selection to an exact, overlapping span of the original source. Goals cannot be claimed independently of their evidence. The full supplied context remains available; a truncated-summary flag explicitly discloses the existing 5,000-character cap. This is strategic summary screening, not full NOFO research.

Eligibility uses the same exact-source selection principle for complete applicant labels and bounded notes excerpts. Existing eligibility verdicts and conservative rule precedence are unchanged.

No quote-matching rule was weakened. Unknown IDs, wrong-source pairs, invented quote overrides, unsupported goals and title-only high fit when an official description exists are rejected. Existing exact legacy quote responses still pass only through the original source validator. Source selection does not itself establish semantic entailment; model relevance and explanations still require human review.

An intermediate retest correctly rejected a model response claiming two goals but supplying evidence for only one. The final paired response structure removes that redundant unsupported-goal path rather than discarding the claim or relaxing validation.

## Actual validation

- Same captured official inputs, real Azure GPT-4o, no historical scores/conclusions supplied to the model: final **12/12 fit assessments accepted**.
- Real Azure eligibility retest: **15/15 accepted**, including the previously rejected category quotation.
- The final fit retest did not repeat the already-passing eligibility calls.
- New regression tests cover punctuation invention, unknown/wrong-source selections, quote overrides, missing goal evidence, paired-contract conflicts, source-span fidelity, truncation disclosure and eligibility-label punctuation.
- Full local offline suite: **250 passed, 25 skipped** for absent optional archived evidence. Compilation and diff checks pass.
- Raw prompts/responses remain private under `/tmp/grantscope-citation-diagnosis-07e9607`, `/tmp/grantscope-citation-selection-live` and `/tmp/grantscope-citation-paired-live`. They are not committed or packaged. Authentication used Entra CLI locally; public deployment continues to use managed identity. The compromised key was not used.

These are operational citation acceptance counts, not human-labeled accuracy, precision or recall metrics. Public deployment and remaining Sol/cache/My Grants acceptance must be checked on the resulting release commit.
