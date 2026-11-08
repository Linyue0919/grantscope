# GrantScope AI Research Analyst — human rubric v1

Frozen before any new benchmark inference. Date/as-of: November 7, 2026 (America/New_York). This document defines review rules, not completed human labels. No historical GPT-4o assessment is ground truth.

## Review procedure

Two reviewers independently inspect each frozen official evidence packet and the explicitly hypothetical project scenario BEFORE seeing model outputs. They record a reference decision, material requirements, missing documents, exact source locations and a rationale. Both must distinguish what the packet supports from what would require a full NOFO. Resolve disagreements and seal the reference file/hash before inference. If reviewers cannot resolve a fact, retain unknown; do not invent a negative or positive label.

Review model outputs with model/deployment identity and numerical scores hidden initially; randomize order. Record raw reviewer decisions before adjudication. Assess the decision before revealing the model's relevance scores. Do not let a pleasing explanation or high score change the reference label without a separately documented correction to source interpretation.

## Claim classes

- **Confirmed fact:** directly supported by an identified official source and accurate in scope. A statement in a synopsis is a confirmed synopsis statement, not proof that all full-notice conditions are satisfied.
- **Reasoned inference:** an explicit, limited conclusion from cited facts; assumptions and alternate interpretations are disclosed.
- **Unresolved requirement:** evidence or project information needed to decide is absent, ambiguous, forecasted, or not checked. State what must be obtained and from whom (role, not invented person).
- **Disqualifying contradiction:** an explicit official condition conflicts with the stated applicant, project, geography, timing or other material scenario fact. Cite the condition and the conflicting scenario fact. Do not elevate silence into exclusion; do not invent a partnership exception.

## Six dimensions — review separately

| Dimension | Review questions | Material errors |
|---|---|---|
| A. Project activity fit | Does the answer identify actual activities, beneficiaries, location and intended outcomes? Does it distinguish monitoring/sensors from physical restoration, and cybersecurity staff training from research or youth diplomacy? | Treating shared topics/outcomes as proof that the actual activity is funded. |
| B. Verified agency strategy | Are claims tied to supplied source-checked goals, page and text? Where goals are unavailable, does it say unavailable and use null rather than zero? | Invented goals, fabricated pages, or project relevance substituted for strategic relevance. |
| C. Funding purpose / allowable activities | What does the program actually fund? Are proposed expenditures supported, conditional or unverified? Does the answer separate eligible landscape/target audience from a shared thematic benefit? | Asserting sensor costs or infrastructure construction are allowed without supporting rules; ignoring restrictions in funding-activity fields. |
| D. Applicant / partnership route | Is the selected government entity an allowed direct applicant, a possible subapplicant, an unverified partner, or excluded? Are sponsorship and lead-applicant conditions distinguished? | Saying eligible because a grant is relevant; presenting an imagined university/tribal partnership as authorized. |
| E. Status / deadlines / match / readiness | Does it use the frozen as-of date? Identify forecast vs posted vs archived/closed, intermediate deadlines, geography, matching funds, application preparation and unknown project conditions? | Calling a forecast open, missing an earlier sponsorship deadline, wrong single-state cap, ignoring 1:1 match, or declaring readiness without evidence. |
| F. Evidence / counterevidence / next action | Do quotes match AND support their specific claims? Does the answer seek conditions that could overturn suitability, identify missing full documents, and give concrete next actions? | Exact but irrelevant quotation used to justify an inference; no counterevidence; unconditional proceed language while material conditions remain unresolved. |

## Dimension ratings and decision labels

Rate each dimension independently: **3 = accurate, complete for available evidence and appropriately qualified; 2 = substantially correct with a nonmaterial omission; 1 = material omission or unsupported inference; 0 = contradiction/fabrication or materially misleading conclusion.** Use unavailable for B when no source-checked agency goals exist; do not convert it to zero or include it in a total. Do not collapse six ratings into an unexplained overall score.

Separately assign the human reference action: **pursue**, **conditional_lead**, **reject**, or **insufficient_evidence**. Pursue means worth proceeding under the reviewed evidence, not guaranteed legal eligibility or funding success. A conditional lead requires naming unresolved material conditions; insufficient evidence means the packet cannot sustain a suitability judgment. Correct abstention is success, not a model failure.

Mark **critical over-recommendation** independently if an output says pursue/apply-ready despite a disqualifying contradiction or unresolved material requirement. High thematic relevance cannot cancel it. Also record unsupported rejection, invented eligibility, missing intermediate deadline, and source-entailment error as separate failure flags.

## Reporting rules (no results yet)

- Report action agreement with adjudicated reference labels, per-dimension ratings/disagreements, critical error counts, appropriate abstentions, quote-match rate and HUMAN-reviewed claim-support rate separately.
- Separate HTTP/provider failures, JSON/schema failures, quotation failures and decision-consistency failures from research correctness. Include attempted, completed, validated and paired-case denominators; never drop failures to inflate accuracy.
- Compare three models on the same case packets. If one model fails, retain the failure and report both all-attempt and complete-pair results.
- This is ten distinct project/opportunity cases, not a representative retrieval benchmark. Do not report Precision@K, statistical superiority, population false-negative rate, funding likelihood or staff time saved from this sample.
- Scores are secondary diagnostics. Compare whether materially different activities receive appropriately different decisions, not whether models agree on a number.
- Keep exploratory observations, proposed fixes and preregistered results separate in GenAI Field Notes. A follow-up repaired run is a new version, not a replacement for the original failures.

## Reference label file

`docs/ai-research-benchmark/human-review-template.json` intentionally has null reviewer identities, decisions and ratings. It must be completed independently and sealed before an approved run. No labels were created by this preparation. Reviewers should read the full official NOFO/amendments when establishing real-world eligibility; the current summary-only arm can only test reasoning and abstention under incomplete evidence.


## Three-case primary-notice pilot registration

The November 7 pilot uses only 364144, 357554 and 347707, the same scenarios, this same rubric and full primary-notice text with disclosed gaps. It is a distinct evidence arm, not a replacement for summary-only results. Blank sheets are in `docs/ai-research-benchmark/pilot/human-review-template.json`. Neither reference actions nor six-axis findings have been filled. The harness requires both reviewer identifiers, an adjudicated action, all A–F reference findings, source locations and adjudication rationale before any paid call. This cannot prove reviewers actually worked independently; preserve their separate original reviews.

For each material claim, reviewers must record the exact source/version/page or section, whether its quote entails the claim, whether contradictory conditions were omitted, and whether the decision would change. Source silence is not evidence of permission or exclusion. Mark incomplete document extraction or an unverified amendment chain explicitly. Review the frozen packet first; if external evidence is needed, record it as missing and freeze a new version for **all** model arms before inference. Do not silently use extra documents to grade one model.

This pilot deliberately concentrates on difficult prior cases and has no human-established positive control. It can expose decision errors but cannot establish retrieval coverage, ranking quality or false-negative rates. In a later expansion, add human-confirmed suitable cases and evaluate keyword baseline and AI on the same candidate set; do not use historical GPT-4o scores as labels.
