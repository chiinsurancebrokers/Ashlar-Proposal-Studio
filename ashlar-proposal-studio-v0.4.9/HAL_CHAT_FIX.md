# v0.4.7 — HAL Chat Fix

- Removed the 510px decorative empty HAL panel that visually separated the real chat from the header.
- Added a real scrollable conversation area.
- `Key differences` and `Risk flags` now execute HAL immediately instead of only pre-filling the input.
- Added visible HAL ready/not-configured status.
- Prevented duplicate current-question injection into chat history.
- Added Anthropic authentication/model/rate-limit/connection error handling so chat errors are shown instead of silently appearing dead.
- Preserves/persists case chat in Saved Cases.
