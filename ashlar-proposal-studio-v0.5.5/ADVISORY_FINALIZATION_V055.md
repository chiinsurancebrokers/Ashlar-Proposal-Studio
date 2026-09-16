# v0.5.5 — Advisory Finalization

This release changes the client deliverable from a neutral comparison into a broker-advisory report.

## Client-facing decision structure

When the quality gate has passed and the quoted facts are sufficient, Ashlar must provide one clear **Recommended option**. The decision synthesis also identifies, where supported by the case:

- **Strong alternative** — the closest competing fit for the stated client priorities.
- **Broader extras option** — useful when add-on benefits such as dental/optical/wellness are a material priority.
- **Budget option** — the lower-cost route, with its material trade-offs stated plainly.

The model is no longer instructed to avoid choosing a winner merely because plans have trade-offs. It may leave the recommendation blank only when a material decision fact is genuinely missing; validation will reject a completed comparative report without a primary recommendation.

## Factual guardrails

- Premium order is derived deterministically and sent to the synthesis model.
- Annual-limit high/low facts are derived deterministically when values are comparable.
- A waiting-period claim must match both the duration and the benefit category found in verified case evidence.
- Incorrect premium superlatives are softened deterministically before the report is saved.

## Files changed

- `core/client_analysis.py`
- `core/report_schema.py`
- `core/presentation.py`
- `core/report_pdf.py`

No Supabase schema or Railway variable changes are required. Redeploy the **Worker** for decision-generation changes and the **Web** service for PDF/PPTX rendering changes.
