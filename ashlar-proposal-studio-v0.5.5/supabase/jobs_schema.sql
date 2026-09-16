-- Ashlar Proposal Studio v0.5 — persistent background job queue
-- Run once in Supabase Dashboard > SQL Editor.

create table if not exists public.analysis_jobs (
    id text primary key,
    case_id text not null references public.analysis_cases(id) on delete cascade,
    job_type text not null check (job_type in ('client_report', 'hal_chat')),
    status text not null default 'pending' check (status in ('pending', 'running', 'completed', 'failed')),
    progress_stage text,
    request_json jsonb not null default '{}'::jsonb,
    result_json jsonb,
    error_message text,
    attempts integer not null default 0,
    worker_id text,
    locked_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists analysis_jobs_status_created_idx
    on public.analysis_jobs (status, created_at);
create index if not exists analysis_jobs_case_idx
    on public.analysis_jobs (case_id, created_at desc);

alter table public.analysis_jobs enable row level security;
grant all on table public.analysis_jobs to service_role;
revoke all on table public.analysis_jobs from anon, authenticated;

create or replace function public.claim_analysis_job(p_worker_id text)
returns setof public.analysis_jobs
language plpgsql
security definer
set search_path = public
as $$
declare
    v_id text;
begin
    select id into v_id
    from public.analysis_jobs
    where status = 'pending'
    order by created_at asc
    for update skip locked
    limit 1;

    if v_id is null then
        return;
    end if;

    return query
    update public.analysis_jobs
       set status = 'running',
           worker_id = p_worker_id,
           locked_at = now(),
           attempts = attempts + 1,
           progress_stage = 'Worker started',
           updated_at = now()
     where id = v_id
     returning *;
end;
$$;

grant execute on function public.claim_analysis_job(text) to service_role;
revoke all on function public.claim_analysis_job(text) from anon, authenticated;
