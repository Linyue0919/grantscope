# GrantScope — NC Federal Funding Matchmaker

GrantScope is a Streamlit prototype that helps North Carolina agencies discover and review federal funding opportunities using live Grants.gov records.

## Evidence and human oversight
- Live search and official opportunity details come from Grants.gov.
- Agency selection covers the statewide directory snapshot; **verified strategic-plan goal extraction is currently partial**. Agencies without verified goals are explicitly unscored.
- Deterministic strategic-topic overlap is **not** an award-probability score.
- Eligibility screening is conservative; missing information remains **Needs Review**. A human must confirm all requirements before applying.
- Azure OpenAI review is an **optional second-stage explanation** based on loaded official details and cited strategic-plan goals. It cannot certify eligibility, and model-generated claims must be checked against primary sources.

## Cost-aware model design ($500 team Azure budget)
We selected an affordable, task-appropriate model strategy for a realistic public-sector workflow rather than sending every grant to the largest model. First, use inexpensive deterministic search, deadline filtering, goal matching, and eligibility flags. Then fetch official details only for selected candidates. Only after a user clicks **Analyze with Azure AI (one paid request)** does GrantScope make one bounded model call (short evidence context, max 450 output tokens). Results are cached in the Streamlit session by agency and opportunity. No bulk background AI calls are made.

The currently verified Azure deployment is **grantscope-gpt4o (GPT-4o)**; the design is model-deployment configurable. We have **not yet validated a cheaper model's quality or measured production token costs**, so no unverified savings or quality claims are made. Before a real pilot, compare lower-cost models against a human-labeled set of relevant/irrelevant grants, especially eligibility false positives, and establish Azure cost alerts and spending controls. The $500 is a project budget, not a guaranteed hard usage cap.

## Local development
```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
streamlit run app.py
```

For optional Azure analysis, create a local **.streamlit/secrets.toml** (never commit):
```toml
AZURE_OPENAI_ENDPOINT = "https://YOUR-RESOURCE.openai.azure.com/"
AZURE_OPENAI_API_KEY = "YOUR-LOCAL-KEY"
AZURE_OPENAI_DEPLOYMENT = "grantscope-gpt4o"
AZURE_OPENAI_API_VERSION = "2024-10-21"
```
Run the optional connectivity smoke test manually with `python scripts/azure_openai_smoke.py`. Do not put credentials in issues, commits, screenshots, or chat.

## Evaluation and limitations
Run `python -m unittest discover -s tests -v`. Regression tests cover generic title-only matches, official description evidence, and restricted-applicant eligibility. Official plan coverage, API pagination, applicant restrictions, and model quality need further validation before statewide operational use.
