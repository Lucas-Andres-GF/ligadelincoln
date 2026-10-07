-- Cola segura para ejecutar scrapers desde el panel remoto.
-- El navegador solamente puede crear y leer sus trabajos como administrador.
-- El worker de Mint reclama y actualiza trabajos con la service-role key.

create table if not exists public.scraper_jobs (
    id bigint generated always as identity primary key,
    scraper text not null check (
        scraper in ('horarios', 'resultados', 'alineaciones', 'resultados_alineaciones')
    ),
    mode text not null default 'preview' check (mode in ('preview', 'execute')),
    torneo_id integer not null check (torneo_id > 0),
    categoria text check (
        categoria is null or categoria in ('primera', 'septima', 'octava', 'novena', 'decima')
    ),
    fecha integer check (fecha is null or fecha > 0),
    status text not null default 'queued' check (
        status in ('queued', 'running', 'succeeded', 'failed')
    ),
    requested_by uuid not null default auth.uid(),
    requested_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz,
    heartbeat_at timestamptz,
    worker_id text,
    exit_code integer,
    output text not null default '',
    error_message text,
    constraint scraper_jobs_parameters_check check (
        (scraper = 'horarios' and categoria is null and fecha is null)
        or (scraper = 'resultados' and fecha is null)
        or (scraper = 'alineaciones' and categoria is null and fecha is not null)
        or (scraper = 'resultados_alineaciones' and fecha is not null)
    )
);

create index if not exists scraper_jobs_queue_idx
    on public.scraper_jobs (status, requested_at, id);

create unique index if not exists scraper_jobs_single_active_idx
    on public.scraper_jobs ((true))
    where status in ('queued', 'running');

create table if not exists public.scraper_workers (
    worker_id text primary key,
    hostname text not null,
    last_seen_at timestamptz not null default now(),
    current_job_id bigint references public.scraper_jobs(id) on delete set null,
    version text not null default '1'
);

alter table public.scraper_jobs enable row level security;
alter table public.scraper_workers enable row level security;

revoke all privileges on table public.scraper_jobs from public, anon, authenticated;
revoke all privileges on table public.scraper_workers from public, anon, authenticated;

grant select on table public.scraper_jobs to authenticated;
grant insert (scraper, mode, torneo_id, categoria, fecha)
    on table public.scraper_jobs to authenticated;
grant select on table public.scraper_workers to authenticated;
grant usage, select on sequence public.scraper_jobs_id_seq to authenticated;

drop policy if exists scraper_jobs_admin_select on public.scraper_jobs;
create policy scraper_jobs_admin_select on public.scraper_jobs
    for select to authenticated
    using (public.is_liga_admin());

drop policy if exists scraper_jobs_admin_insert on public.scraper_jobs;
create policy scraper_jobs_admin_insert on public.scraper_jobs
    for insert to authenticated
    with check (
        public.is_liga_admin()
        and requested_by = (select auth.uid())
        and status = 'queued'
        and started_at is null
        and finished_at is null
        and worker_id is null
        and exit_code is null
        and output = ''
        and error_message is null
    );

drop policy if exists scraper_workers_admin_select on public.scraper_workers;
create policy scraper_workers_admin_select on public.scraper_workers
    for select to authenticated
    using (public.is_liga_admin());

create or replace function public.claim_scraper_job(p_worker_id text)
returns setof public.scraper_jobs
language plpgsql
security definer
set search_path = ''
as $$
declare
    claimed_id bigint;
begin
    if p_worker_id is null or length(btrim(p_worker_id)) < 3 then
        raise exception 'worker_id inválido';
    end if;

    select job.id
      into claimed_id
      from public.scraper_jobs as job
     where job.status = 'queued'
     order by job.requested_at, job.id
     for update skip locked
     limit 1;

    if claimed_id is null then
        return;
    end if;

    return query
    update public.scraper_jobs
       set status = 'running',
           worker_id = p_worker_id,
           started_at = now(),
           heartbeat_at = now(),
           finished_at = null,
           exit_code = null,
           output = '',
           error_message = null
     where id = claimed_id
     returning *;
end;
$$;

revoke all on function public.claim_scraper_job(text) from public, anon, authenticated;
grant execute on function public.claim_scraper_job(text) to service_role;
