# grantscope
AI-powered federal grant matching platform for North Carolina agencies

## Running locally
```bash
pip install -r requirements.txt
streamlit run app.py
```
Azure OpenAI is optional: put credentials in `.streamlit/secrets.toml` (gitignored; see `secrets.toml.example`).
Without them, GrantScope uses its rule-based checks and keyword matching only.

**Saved opportunities** are kept for the current browser session only (no accounts, nothing stored on the server).

## Demo prep
Pre-warm the cache 15–20 minutes before a demo: open the Brief and switch to **NC Department of Health and Human
Services**, **NC Department of Environmental Quality** and **NC Wildlife Resources Commission** once each. Results are
cached for 30 minutes, so the demo then loads instantly. To check how many grants land in each section (with GPT-4o on,
if configured): `python scripts/brief_section_counts.py`.
