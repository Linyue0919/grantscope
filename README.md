# GrantScope — NC Federal Funding Matchmaker

GrantScope is a Streamlit prototype that helps North Carolina agencies discover and review federal funding opportunities using live Grants.gov records.

## Evidence and human oversight
- Live search and official opportunity details come from Grants.gov.
- Agency selection covers the statewide directory snapshot; **verified strategic-plan goal extraction is currently partial**. Agencies without verified goals are explicitly unscored.
- Deterministic strategic-topic overlap is **not** an award-probability score.
- Eligibility screening is conservative; missing information remains **Needs Review**. A human must confirm all requirements before applying.
- Azure OpenAI review is an **optional second-stage explanation** based on loaded official details and cited strategic-plan goals. It cannot certify eligibility, and model-generated claims must be checked against primary sources.

## Final demo integration

The local `release/final-demo` branch combines Dashboard strategic-plan matching and project-first Search. Search shows up to five screened **Potential Matches**; they are not verified AI recommendations. Candidate-specific **Deep Research** runs the real Azure Sol analysis/decision pipeline with source-specific citation and consistency validation. Unknown eligibility remains unresolved; confirmed exclusions cannot be overridden by relevance.

Dashboard uses the existing GPT-4o deployment when its AI option is enabled and can make paid calls during matching. Deep Research uses the existing Sol deployment only after the explicit action. Failed or incomplete research remains unverified. Real Azure AI is enabled by valid environment or optional local secrets configuration; keyless CLI and managed-identity authentication are supported. Never commit credentials.

Search currently retrieves at most 100 records per query and screens official details for 80 candidates. More candidates may remain uninspected, so zero results is not proof of no funding. Progressive screening and coverage caching are planned, not implemented. See [release instructions, exact configuration and coverage limits](docs/final-demo-release.md).

## Local development
```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest -q
streamlit run app.py
```

For optional Azure analysis, create a local **.streamlit/secrets.toml** (never commit):
```toml
AZURE_OPENAI_ENDPOINT = "https://YOUR-RESOURCE.openai.azure.com/"
AZURE_OPENAI_API_KEY = "YOUR-LOCAL-KEY"
AZURE_OPENAI_DEPLOYMENT = "grantscope-gpt4o"
AZURE_OPENAI_API_VERSION = "2024-10-21"
```
The optional `python scripts/azure_openai_smoke.py` makes an inference call; run it only when a paid check is intended. Do not put credentials in issues, commits, screenshots, or chat.

## Evaluation and limitations
See [actual live Dashboard and Sol acceptance results, failures and fixes](docs/live-ai-acceptance.md).
Run `python -m pytest -q` after installing `requirements-dev.txt`. Regression tests cover generic title-only matches, official description evidence, and restricted-applicant eligibility. Official plan coverage, API pagination, applicant restrictions, and model quality need further validation before statewide operational use.
