# Ashlar Proposal Studio

Internal, evidence-first insurance comparison and client-proposal workspace for Ashlar Assurance.

This is a **standalone application** intended for its own private GitHub repository and Railway service.

## v0.4.1 — permanent Provider Library

The Provider Library is now designed to live **outside Railway** in **Supabase**:

- **Supabase Storage** — original brochures, Tables of Benefits, policy wordings, underwriting guides and endorsements.
- **Supabase Postgres** — provider/product/version metadata plus cached parsed text.
- **Railway** — application code and temporary case processing only.
- **GitHub** — application code only; no provider/client documents.

This means a normal Railway redeploy, code update, container replacement or new deployment does **not** delete the Provider Library.

If Supabase credentials are not configured, Proposal Studio automatically falls back to the original local SQLite/filesystem backend for development.

### One-click migration from the old Railway Volume

If v0.4 already has provider documents under `/app/data`, keep that volume mounted for the first v0.4.1 deployment. Once Supabase is configured, Admin → Provider Library will detect the old local library and offer:

**Migrate local Library to Supabase**

It copies the source documents and metadata to Supabase, skips exact duplicates by SHA-256 and leaves the old files untouched. After you confirm the cloud Library is complete, the old Railway volume is no longer required for provider knowledge.

### Persistent text indexing

When a source is added in Admin, Proposal Studio parses its PDF/TXT text immediately and stores that parsed text with the Library record. The same provider wording therefore does not need to be re-parsed after each deployment or for every new client case.

Multi-plan table isolation still reads the original PDF when necessary because table geometry/checkmarks are part of the evidence layer.

---

## Client Analysis Engine

After the broker has reviewed the extracted facts, Proposal Studio generates the client deliverable:

- client context / priorities
- presentation of each shortlisted insurance plan
- deterministic side-by-side comparison matrix
- practical **Key Differences That Matter**
- reasoned **Ashlar Assessment** based on the client priorities and supplied evidence
- alternative option and when it may be preferable
- important considerations and next steps
- branded **PPTX presentation**
- branded **PDF report**
- English or Greek output

The LLM does not rebuild the plan facts for this step. The comparison matrix is created deterministically from the already-extracted case data, while the model writes the client-facing synthesis and reasoned advisory view.

## Multi-plan brochure isolation

Proposal Studio locks the selected plan first, then isolates that plan's column before LLM analysis. This is designed for brochures such as IMG Global Prima Medical Insurance where Bronze, Bronze Plus, Silver, Gold and Platinum appear side by side.

The deterministic evidence layer records:

- source file
- page
- section
- benefit row
- target-plan value
- evidence type (text/checkmark)

The LLM receives target-plan evidence separately and is prohibited from borrowing a figure from a neighbouring tier.

## Admin Library

Store once and reuse across cases:

- Brochure / multi-plan Table of Benefits
- Table of Benefits
- Policy Wording / Member Guide
- Underwriting guide
- Supporting document / endorsement

Set `ADMIN_PASSWORD` in production to password-gate this page.

## Ask HAL — grounded case chat

After a case has been analyzed, **Ask HAL** lets the broker interrogate the case: compare benefits, explain trade-offs, surface limitations, identify clauses that require verification, and discuss underwriting uncertainty.

HAL receives the structured analyses plus deterministic target-plan evidence and is instructed not to invent missing policy facts.

---

## Repository layout

```text
ashlar-proposal-studio/
├── app.py
├── Dockerfile
├── railway.json
├── requirements.txt
├── .env.example
├── core/
│   ├── analyzer.py
│   ├── brochure_tables.py
│   ├── chat.py
│   ├── client_analysis.py
│   ├── presentation.py
│   ├── report_pdf.py
│   ├── extract.py
│   ├── plan_selector.py
│   └── storage.py
├── supabase/
│   ├── schema.sql
│   └── README.md
└── tests/
```

## Supabase setup — production

### 1. Create a Supabase project

Create the project in Supabase and keep the project URL and **service-role key** private.

### 2. Create the Library table

Open **Supabase → SQL Editor**, paste the contents of:

```text
supabase/schema.sql
```

and run it once.

The table is RLS-enabled and only the server-side `service_role` is granted access by the supplied schema.

### 3. Storage bucket

Proposal Studio will attempt to create a private bucket named `provider-library` automatically on first upload. You may also create it manually in Supabase Storage.

### 4. Railway variables

```env
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-haiku-4-5-20251001
HAL_CHAT_MODEL=claude-haiku-4-5-20251001
CLIENT_ANALYSIS_MODEL=claude-haiku-4-5-20251001
ADMIN_PASSWORD=choose-a-strong-password

LIBRARY_BACKEND=supabase
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET=provider-library
SUPABASE_LIBRARY_TABLE=provider_documents

# Keep /app/data only while migrating an existing v0.4 Railway library.
DATA_DIR=/app/data
```

**Never put `SUPABASE_SERVICE_ROLE_KEY` into browser JavaScript or a public repository.** Proposal Studio uses it only on the Streamlit/Railway server.

### 5. Deploy

Redeploy Railway. Open **Admin Library**. The status card should show:

```text
Library backend: Supabase Cloud
Persistent cloud library active
```

If an old Railway library exists, use the migration button once.

---

## Local development

Without Supabase the app falls back to local storage:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

For a forced local library:

```env
LIBRARY_BACKEND=local
DATA_DIR=./data
```

## Data boundary

**Private GitHub repository:** code only.

**Supabase Provider Library:** reusable provider documents, versions and cached parsed text.

**Client quotations:** used within the active case and are not automatically promoted to the permanent provider library.

**Generated PDF/PPTX:** generated on demand; they are not automatically stored in the Provider Library.

## Evidence rules

1. Applicant-specific quote/certificate beats generic brochure examples for applicant-specific facts.
2. Target-plan table extraction beats ambiguous full-table LLM reading.
3. Policy wording governs exclusions, definitions and contractual conditions.
4. “Available” is not the same as “selected”. Optional benefits remain optional unless the client quote confirms selection.
5. If a plan cannot be locked confidently, the broker supplies the selected-plan override rather than allowing the system to guess.

## Tests

```bash
pytest -q
```

v0.4.1 currently includes local-storage, JSON parsing, client-output and persistence regression tests.


## v0.4.2 browser hotfix

- Pins Streamlit to `1.62.0` to avoid untested frontend changes from floating `>=` installs.
- Disables Enter-to-submit on the admin password form to reduce browser/autofill key-event issues.
- Uses an explicit session-state key for the admin password field and clears it after successful authentication.

The Chrome `Password field is not contained in a form` console message may still appear because Streamlit forms are not native HTML `<form>` elements. It is a browser warning, not an authentication or Supabase error.

## v0.4.5 — carrier adapters, extraction quality gate and Saved Cases

### Carrier-aware extraction

Proposal Studio now identifies the carrier before applying applicant-quote headline extraction. Dedicated adapters exist for:

- Cigna — validated against the 2026 CGHO Silver quotation/brochure test case.
- IMG — validated against the Global Prima multi-plan brochure test case.
- Bupa — carrier adapter framework enabled; final carrier-specific patterns should be validated against a real Bupa quotation and benefit schedule before being marked fully tested.
- Now Health — carrier adapter framework enabled; final carrier-specific patterns should be validated against a real Now Health quotation and benefit schedule before being marked fully tested.
- Generic fallback — conservative extraction for other insurers.

The adapter layer only locks applicant-specific headline facts that are explicitly stated. It does not replace the plan-table evidence engine.

### Extraction quality gate

Each analyzed option is assessed before client-report generation. Material checks include:

- selected plan lock
- premium
- annual limit
- deductible / excess
- area of cover
- presence of meaningful benefit extraction
- target-plan table evidence when a provider library source is used

Statuses are **Ready**, **Review**, or **Blocked**. A blocked option cannot generate a new client report until the material extraction issue is reviewed.

### Supabase Saved Cases

Analyzed cases can now be saved and reopened from a separate **Saved Cases** workspace. A case snapshot stores:

- case/client metadata
- structured plan analyses
- deterministic target-plan evidence
- HAL case chat
- generated client analysis

This allows the broker to reopen a case without re-running AI extraction. Provider documents remain in the Provider Library. Original applicant quote files are not archived in v0.4.5.

For an existing Supabase project run either the updated `supabase/schema.sql` or the smaller incremental file:

```text
supabase/cases_schema.sql
```

Then add to Railway if you want a non-default table name:

```env
SUPABASE_CASE_TABLE=analysis_cases
```

The default is already `analysis_cases`, so the variable is optional.

## v0.4.6 carrier validation

Bupa Global Select and Now Health SimpleCare are now validated against real quote/document samples. Saved HTML quote emails are supported. See `BUPA_NOW_VALIDATION.md`.
