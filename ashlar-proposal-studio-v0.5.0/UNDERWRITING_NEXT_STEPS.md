# v0.4.9 — Underwriting-aware Next Steps

The Client Analysis Engine now treats underwriting workflow as a deterministic broker rule rather than narrative AI output.

### Full Medical Underwriting

- Complete application + full medical history declaration.
- Submit for Full Medical Underwriting; additional medical information may be requested.
- Review final applicant-specific underwriting terms, exclusions/special conditions, final premium and effective date.
- Accept final terms and activate policy.

### Other supported methods

Dedicated workflows are also supplied for Moratorium, CPME and MHD.

This logic is applied after narrative generation, so even if the language model omits a step, the final PDF/PPTX receives the correct underwriting journey.
