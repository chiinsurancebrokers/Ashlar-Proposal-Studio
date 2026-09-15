# Ashlar Proposal Studio

Internal AI workspace for insurance brokers: combine client-specific quotations with a persistent provider document library, isolate the correct plan from multi-plan brochures, compare propositions, and later generate client-ready Ashlar presentations.

## Core safety rule: target-plan isolation

A provider document may contain several tiers side by side — for example IMG Global Prima Medical Insurance may contain Bronze, Bronze Plus, Silver, Gold and Platinum in one Table of Benefits. Proposal Studio does **not** flatten the table and let the LLM guess.

The pipeline is:

1. The client quotation/certificate identifies the selected plan (or the broker overrides it).
2. `core/brochure_tables.py` finds that exact plan header in the PDF table.
3. It crops the target column row-by-row and also detects small vector coverage checkmarks.
4. Only that plan-specific evidence is promoted above generic brochure text in the LLM prompt.
5. Optional benefits remain **optional/not confirmed selected** unless the client quotation confirms they were purchased.

## Architecture

```text
GitHub (private repo)
       |
       v
Railway service / Dockerfile
       |
       +-- Streamlit application
       +-- Claude API
       |
       +-- Railway persistent Volume mounted at /app/data
             |
             +-- proposal_studio.db
             +-- provider_documents/
                   provider/product/version/document-type/...
```

Provider documents and future client/case documents must **not** be committed to GitHub.

## Local development

```bash
cp .env.example .env
# add ANTHROPIC_API_KEY
pip install -r requirements.txt
streamlit run app.py
```

Local `DATA_DIR` defaults to `./data`.

## New GitHub repository

Recommended repository name:

`ashlar-proposal-studio`

Recommended visibility: **Private**.

Upload the contents of this project to the repository root. Do not upload `.env` or the contents of `data/`.

## Deploy to Railway

1. Create a new Railway project.
2. Choose **Deploy from GitHub repo** and select `ashlar-proposal-studio`.
3. Railway will use the included `Dockerfile` and `railway.json`.
4. Add service variables:

```text
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-haiku-4-5-20251001
DATA_DIR=/app/data
```

5. Add a **Railway Volume** to the service and mount it at:

```text
/app/data
```

This is essential. Without the Volume, the provider document library/SQLite database can disappear on redeploy.

6. Generate a Railway public domain or attach your own subdomain.

The health check is:

```text
/_stcore/health
```

## Current v0.2 workflow

### Provider Library

Store provider documents once with:

- Provider
- Product/product family
- Version/year
- Document type
- optional effective dates
- notes

Supported document types:

- Brochure / multi-plan Table of Benefits
- Table of Benefits
- Policy Wording / Member Guide
- Underwriting guide
- Supporting document

Exact duplicate documents are skipped by SHA-256.

### Case Workspace

For each provider in a case:

1. Select the matching provider/product/version from the Provider Library.
2. Upload the **client-specific quotation/certificate**.
3. Proposal Studio identifies the selected plan from the quote.
4. It searches the stored brochure/TOB for that plan's exact column.
5. It combines:
   - client-specific quote facts,
   - plan-specific table evidence,
   - generic policy wording/underwriting documents.
6. It produces a structured comparison and exposes the extracted source rows for broker audit.

## Next build milestones

1. Broker-review/confirmation screen with editable extracted fields.
2. Evidence object per material fact: source document + page + extraction confidence.
3. Case persistence and client/case history on the Railway Volume.
4. Import/refactor the existing Ashlar/CHI `python-pptx` engine.
5. Generate client-ready PPTX and PDF proposal packs.
6. Optional second-model verification for low-confidence or conflicting fields.
7. Authentication before production use.
