# v0.5.1 — Client Report Schema Reliability

Fixes a FastAPI/worker report-generation failure where Claude returned more than one JSON object or an incomplete/partial object and the parser selected the wrong object.

Changes:
- parse all JSON objects in the model response and select the one that best matches the ClientReport schema;
- automatically retry once with an explicit schema-repair prompt if Pydantic validation still fails;
- preserve the previous validated report on failure;
- replace raw Pydantic validation details with a concise client-safe retry message if the repair also fails.

No Supabase schema or Railway variable changes are required.
