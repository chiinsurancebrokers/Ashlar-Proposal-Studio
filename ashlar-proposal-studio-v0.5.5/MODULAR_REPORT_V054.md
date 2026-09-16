# v0.5.4 — Modular Report Generator

The client-report pipeline no longer asks one LLM call to recreate the entire report.

## Deterministic sections
- report title
- plan pages from verified quote / benefit facts
- side-by-side matrix
- underwriting workflow and next steps
- disclaimer

## LLM synthesis only
- executive summary
- client-needs summary
- up to 4 key differences
- Ashlar Assessment
- up to 5 important considerations

The decision payload is deliberately compact and excludes the full extraction audit and comparison matrix. Model output is capped at 4,800 tokens even when a legacy larger CLIENT_ANALYSIS_MAX_TOKENS value exists. One concise retry is allowed.

This architecture prevents the 10k–12k-token truncation seen in four-provider comparisons and makes section failures cheaper to retry.
