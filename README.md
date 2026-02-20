# Caregiver Handoff (Rule-Based Demo)

A small Streamlit app for an AI-assisted coding workshop.
It turns caregiver free-text notes into a structured handoff summary using ONLY rule-based logic (regex + keywords).

## Safety / Scope
- Non-diagnostic: no medical diagnosis, no treatment advice
- No medication changes: only logs meds/vitals mentioned
- Demo-only: no OpenAI or external API keys

---

## Run locally

### 1) Create a folder and add files
Create a folder and add:
- app.py
- requirements.txt
- README.md

### 2) Install & run
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
