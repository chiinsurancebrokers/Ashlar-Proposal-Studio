-- Ashlar Proposal Studio — persistent Provider Library
-- Run once in Supabase Dashboard > SQL Editor.

create table if not exists public.provider_documents (
    id text primary key,
    provider text not null,
    product text not null,
    version text not null,
    doc_type text not null,
    original_filename text not null,
    stored_path text not null,
    sha256 text not null,
    effective_from text,
    effective_to text,
    notes text,
    uploaded_at timestamptz not null default now(),
    extracted_text text,
    extracted_at timestamptz,
    extraction_error text,
    constraint provider_documents_unique_source
        unique (provider, product, version, doc_type, sha256)
);

create index if not exists provider_documents_lookup_idx
    on public.provider_documents (provider, product, version);

alter table public.provider_documents enable row level security;

-- Proposal Studio uses the service-role key only on the Railway server.
-- No browser/anon access is granted to this table.
grant all on table public.provider_documents to service_role;
revoke all on table public.provider_documents from anon, authenticated;
