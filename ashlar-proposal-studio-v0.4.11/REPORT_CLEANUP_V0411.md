# v0.4.11 — Report cleanup

- PDF cover no longer repeats the Executive Summary; the full summary appears only on page 2.
- Full Medical Underwriting cases use one client-facing pre-existing-condition wording across compared IPMI plans.
- CPME, MHD and moratorium retain their own underwriting-specific wording.
- Age alone is never used as a proxy for health, pre-existing-condition likelihood or expected utilisation.
- Plan narrative matching is more tolerant of labels such as `CIGNA SILVER` vs `CIGNA`, preventing blank plan-review pages.
