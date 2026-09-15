# v0.4.4 — Cigna / deterministic fact-lock fix

This patch fixes two separate issues discovered with Cigna Global Health Options:

1. **Continuation tables without repeated plan headers** — e.g. the Dental Treatment table on page 16 continues the Silver/Gold/Platinum columns but does not repeat the plan names. The plan-table extractor now carries the verified column geometry into compatible continuation tables.
2. **LLM omission of material facts** — even when the quote and target-plan table contained the data, the UI could display `—` if the model returned null/missing fields. Material headline facts are now locked deterministically from the applicant quotation and target-plan table evidence.

For the test case `QQQ5349749-Ioannis_Konstantinidis.pdf` + `591050 CGHO Sales Brochure Broker EN 02_2026.pdf`, the patched engine deterministically resolves:

- Plan: Silver
- Premium: EUR 2,389.83 annual
- Deductible / cost share: €0 / 0%
- Area: Worldwide excluding USA (USA Cover not selected)
- Core annual maximum: €800,000
- Outpatient annual maximum: €12,000
- International Medical Evacuation: selected
- Health & Wellbeing: selected
- Vision & Dental: selected
- Dental annual maximum: €930

The Cigna Silver target-plan extraction increases from **71 to 76 rows**, adding the continuation Dental Treatment rows that were previously missed.
