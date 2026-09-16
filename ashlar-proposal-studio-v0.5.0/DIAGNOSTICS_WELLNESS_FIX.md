# v0.4.10 — Diagnostics / wellness correction

- Cigna Silver Advanced Medical Imaging now matches only the exact `Advanced Medical Imaging` table row. It can no longer inherit `Private room` from the hospital-accommodation row that contains the phrase `excluding Advanced Medical Imaging`.
- Exact selected-plan diagnostic evidence overrides conflicting LLM prose.
- Now Health SimpleCare 250 now deterministically reports no separate wellness benefit when the quotation exclusions state that routine examinations and health screening are excluded except where specifically stated in the benefit schedule.
- Client-analysis prompt explicitly prohibits accommodation text inside diagnostics and prevents `Not covered` preventive evidence from being softened to `Not mentioned`.
