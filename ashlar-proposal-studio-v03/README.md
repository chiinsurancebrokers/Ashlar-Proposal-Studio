# Ashlar Proposal Studio

Internal, evidence-first insurance comparison and proposal workspace for Ashlar Assurance.

This is a **standalone application** intended for its own private GitHub repository and its own Railway service. It is not HAL's public quote engine and it is not the old Policy Analyzer.

## What v0.3 includes

### Modern Case Studio
- Ashlar/HAL-inspired dark navigation + clean light workspace
- One case can compare multiple providers
- Each option can be connected to a permanent provider-library source
- Applicant-specific quotation/certificate remains the highest-priority source
- Optional case-specific brochures, wordings, endorsements and correspondence can be added

### Multi-plan brochure isolation
Proposal Studio locks the selected plan first, then isolates that plan's column before LLM analysis. This is designed for brochures such as IMG Global Prima Medical Insurance where Bronze, Bronze Plus, Silver, Gold and Platinum appear side by side in the same benefit tables.

The deterministic table layer records:
- source file
- page
- section
- benefit row
- target-plan value
- evidence type (text/checkmark)

The LLM receives this target-plan evidence separately and is explicitly prohibited from borrowing a figure from a neighbouring tier.

### Admin Library
The **Admin Library** page is the permanent provider knowledge base.

Store once:
- Brochure / multi-plan Table of Benefits
- Table of Benefits
- Policy Wording / Member Guide
- Underwriting guide
- Supporting document / endorsement

Metadata is stored in SQLite and the original files are stored on persistent disk. Exact duplicate documents are detected using SHA-256.

Set `ADMIN_PASSWORD` in production to password-gate this page.

### Ask HAL — grounded case chat
After a case has been analyzed, the right-hand **Ask HAL** panel lets the broker interrogate the analysis:
- compare benefits
- explain practical trade-offs
- surface limitations
- identify points that need verification
- discuss underwriting uncertainty

HAL's case chat receives the structured analyses plus deterministic target-plan evidence. It is instructed not to invent missing policy facts and to cite source file/page when available.

## Repository layout

```text
ashlar-proposal-studio/
├── app.py
├── Dockerfile
├── railway.json
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
├── .streamlit/
│   └── config.toml
├── core/
│   ├── analyzer.py
│   ├── brochure_tables.py
│   ├── chat.py
│   ├── extract.py
│   ├── plan_selector.py
│   └── storage.py
├── data/
│   └── .gitkeep
└── tests/
    └── test_storage.py
```

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

Environment variables:

```env
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-haiku-4-5-20251001
HAL_CHAT_MODEL=claude-haiku-4-5-20251001
ADMIN_PASSWORD=choose-a-strong-password
DATA_DIR=./data
```

## Railway deployment

1. Create a **private** GitHub repository, recommended name: `ashlar-proposal-studio`.
2. Push this repository to GitHub.
3. Railway → **New Project → Deploy from GitHub repo**.
4. Add the environment variables above.
5. Add a **Railway Volume** mounted at:

```text
/app/data
```

6. In Railway set:

```env
DATA_DIR=/app/data
```

The included Dockerfile starts Streamlit on Railway's supplied `$PORT` and `railway.json` uses Streamlit's health endpoint.

## Data boundary

**GitHub:** application code only.

**Railway Volume:** provider PDFs/TXT files + `proposal_studio.db`.

Client quotations are used in the case workspace and are not automatically promoted into the permanent provider library.

## Evidence rules

1. Applicant-specific quote/certificate beats generic brochure examples for applicant-specific facts.
2. Target-plan table extraction beats ambiguous full-table LLM reading.
3. Policy wording governs exclusions, definitions and contractual conditions.
4. “Available” is not the same as “selected”. Optional benefits remain optional unless the client quote confirms selection.
5. If a plan cannot be locked confidently, the broker must provide the selected-plan override rather than allowing the system to guess.

## Current milestone

v0.3 establishes:

**Provider Library → Client quote → exact plan lock → plan-column isolation → structured analysis → evidence audit → grounded HAL chat.**

The next logical milestone is the **Broker Review / Confirmed Facts layer**, followed by Ashlar-branded PPTX/PDF proposal generation.
