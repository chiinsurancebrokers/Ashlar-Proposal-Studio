-- Ashlar Proposal Studio — persistent analyzed Case Archive
-- Run once in Supabase Dashboard > SQL Editor.

create table if not exists public.analysis_cases (
    id text primary key,
    case_reference text,
    client_name text,
    client_profile text,
    client_priorities text,
    report_language text not null default 'English',
    results_json jsonb not null default '[]'::jsonb,
    case_chat_json jsonb not null default '[]'::jsonb,
    client_analysis_json jsonb,
    provider_count integer not null default 0,
    plan_summary text,
    status text not null default 'analyzed',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists analysis_cases_updated_idx
    on public.analysis_cases (updated_at desc);
create index if not exists analysis_cases_client_idx
    on public.analysis_cases (client_name);

alter table public.analysis_cases enable row level security;

grant all on table public.analysis_cases to service_role;
revoke all on table public.analysis_cases from anon, authenticated;
