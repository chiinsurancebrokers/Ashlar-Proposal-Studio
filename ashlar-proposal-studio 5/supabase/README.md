# Supabase Provider Library setup

Ashlar Proposal Studio uses Supabase only for the **permanent provider knowledge base**. Client quote uploads remain case-specific.

## Setup

1. Create a Supabase project.
2. In **SQL Editor**, run `schema.sql` once.
3. In Railway, set:
   - `LIBRARY_BACKEND=supabase`
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_STORAGE_BUCKET=provider-library`
   - `SUPABASE_LIBRARY_TABLE=provider_documents`
4. Redeploy Proposal Studio.
5. Open **Admin Library** and upload a test provider source.

The app attempts to create the private Storage bucket automatically. If bucket creation is disabled for the supplied credentials/settings, create a **private** bucket named `provider-library` manually in Supabase Storage and retry.

## Migrating v0.4 Railway documents

Keep the old Railway volume mounted at `/app/data` and keep `DATA_DIR=/app/data` during the first v0.4.1 deployment. Admin Library will show a migration card if it detects the old SQLite library.

Run the migration, verify the Supabase catalog and downloads, then the old Railway provider-library volume can be removed if you do not use it for anything else.

## Security

`SUPABASE_SERVICE_ROLE_KEY` is a server secret. Store it only in Railway Variables / local `.env`. Do not commit it and do not expose it in client-side code.
