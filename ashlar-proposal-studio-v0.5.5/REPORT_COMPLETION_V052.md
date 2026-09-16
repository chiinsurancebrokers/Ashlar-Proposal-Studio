# v0.5.2 — Reliable long comparative reports

This patch fixes repeated `incomplete structure after automatic retry` failures on large multi-provider comparisons.

## Root cause

The v0.5 background report worker used a 4,500-token default output budget. A four-provider client report can exceed that budget. When Claude stopped at `max_tokens`, the outer JSON object was incomplete while some nested plan objects were still valid JSON. The tolerant parser could therefore select a nested object and surface a misleading schema error.

## Changes

- adaptive output budget: 5,200 / 6,500 / 7,800 / 9,200 tokens for 1 / 2 / 3 / 4+ plans;
- explicit detection of Anthropic `stop_reason=max_tokens`;
- automatic full-generation retry up to 12,000 tokens;
- only a complete report object containing all structural top-level keys can be accepted;
- repair prompt uses a compact grounded payload and at least 9,000 output tokens;
- tighter report-length instructions to keep the client document concise;
- default client-report model changed to `claude-sonnet-5` while HAL/general extraction can remain on Haiku.

No Supabase migration is required.
