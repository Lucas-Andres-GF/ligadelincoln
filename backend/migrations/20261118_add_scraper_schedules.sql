begin;

create table public.scraper_schedules (
    id bigint generated always as identity primary key,
    scraper text not null check (scraper in ('resultados', 'alineaciones', 'resultados_alineaciones')),
    torneo_id integer not null check (torneo_id > 0),
    categoria text check (categoria in ('primera', 'septima', 'octava', 'novena', 'decima')),
    fecha integer check (fecha > 0),
    run_date date,
    weekday smallint check (weekday between 1 and 7),
    start_time time not null,
    end_time time not null,
    interval_minutes smallint not null check (interval_minutes in (5, 10, 15, 20, 30, 60)),
    enabled boolean not null default true,
    requested_by uuid not null default auth.uid(),
    active_since timestamptz not null default now(),
    last_slot timestamptz,
    last_job_id bigint references public.scraper_jobs(id),
    check (num_nonnulls(run_date, weekday) = 1),
    check (start_time <= end_time and end_time < time '24:00'
           and extract(second from start_time) = 0 and extract(second from end_time) = 0),
    check (
        (scraper = 'resultados' and fecha is null)
        or (scraper = 'alineaciones' and fecha is not null and categoria is null)
        or (scraper = 'resultados_alineaciones' and fecha is not null)
    )
);

alter table public.scraper_schedules enable row level security;
revoke all on public.scraper_schedules from public, anon, authenticated;
grant insert (scraper, torneo_id, categoria, fecha, run_date, weekday, start_time, end_time, interval_minutes)
    on public.scraper_schedules to authenticated;
grant select on public.scraper_schedules to authenticated;
grant update (enabled) on public.scraper_schedules to authenticated;
grant usage, select on sequence public.scraper_schedules_id_seq to authenticated;

create policy schedules_admin_read on public.scraper_schedules
    for select to authenticated using (public.is_liga_admin());
create policy schedules_admin_insert on public.scraper_schedules
    for insert to authenticated with check (
        public.is_liga_admin() and requested_by = (select auth.uid())
        and (run_date is null or run_date + end_time >=
             date_trunc('minute', now() at time zone 'America/Argentina/Buenos_Aires'))
    );
create policy schedules_admin_pause on public.scraper_schedules
    for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());

create function public.scraper_schedule_rearmed()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if new.enabled and not old.enabled then
        new.active_since := now();
    end if;
    return new;
end;
$$;

create trigger scraper_schedule_rearmed before update of enabled on public.scraper_schedules
    for each row execute function public.scraper_schedule_rearmed();

-- Evaluate at most eight calendar days, regardless of the interval.
create function public.scraper_schedule_slot(
    schedule public.scraper_schedules, at_time timestamptz, due boolean
)
returns timestamptz
language sql
stable
set search_path = ''
as $$
    with clock as (
        select at_time at time zone 'America/Argentina/Buenos_Aires' as local_now
    ), windows as (
        select day + schedule.start_time as starts, day + schedule.end_time as ends, local_now,
               make_interval(mins => schedule.interval_minutes) as period
        from clock
        cross join lateral (
            select case when due then local_now::date
                        else coalesce(schedule.run_date, local_now::date + offset_days) end as day
            from generate_series(0, case when due or schedule.run_date is not null then 0 else 7 end) as offsets(offset_days)
        ) as days
        where (schedule.run_date = day or schedule.weekday = extract(isodow from day))
          and day >= local_now::date
          and (not due or (local_now >= day + schedule.start_time
                           and local_now < day + schedule.end_time + interval '1 minute'))
    ), slots as (
        select starts + period * greatest(0, case when due
            then floor(extract(epoch from least(local_now, ends) - starts) / extract(epoch from period))
            else ceil(extract(epoch from greatest(
                local_now,
                schedule.active_since at time zone 'America/Argentina/Buenos_Aires',
                coalesce((schedule.last_slot at time zone 'America/Argentina/Buenos_Aires') + period, starts)
            ) - starts) / extract(epoch from period))
        end)::integer as local_slot, ends
        from windows
    )
    select min(local_slot at time zone 'America/Argentina/Buenos_Aires')
    from slots
    where schedule.enabled and local_slot <= ends
      and (local_slot at time zone 'America/Argentina/Buenos_Aires') >= schedule.active_since
      and (schedule.last_slot is null
           or (local_slot at time zone 'America/Argentina/Buenos_Aires') > schedule.last_slot);
$$;

create function public.list_scraper_schedules()
returns table (
    id bigint, scraper text, torneo_id integer, categoria text, fecha integer,
    run_date date, weekday smallint, start_time time, end_time time, interval_minutes smallint,
    enabled boolean, next_run_at timestamptz, last_job_id bigint, last_status text, last_run_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
    select s.id, s.scraper, s.torneo_id, s.categoria, s.fecha, s.run_date, s.weekday,
           s.start_time, s.end_time, s.interval_minutes, s.enabled,
           coalesce(public.scraper_schedule_slot(s, now(), true), public.scraper_schedule_slot(s, now(), false)),
           s.last_job_id, j.status, j.requested_at
    from public.scraper_schedules s left join public.scraper_jobs j on j.id = s.last_job_id
    where public.is_liga_admin()
    order by s.id desc;
$$;

-- The existing worker calls this function. Manual jobs retain priority.
create or replace function public.claim_scraper_job(p_worker_id text)
returns setof public.scraper_jobs
language plpgsql
security definer
set search_path = ''
as $$
declare
    claimed_id bigint;
    selected_schedule public.scraper_schedules;
    selected_slot timestamptz;
begin
    if p_worker_id is null or length(btrim(p_worker_id)) < 3 then
        raise exception 'worker_id inválido';
    end if;

    select job.id into claimed_id
    from public.scraper_jobs job where job.status = 'queued'
    order by job.requested_at, job.id for update skip locked limit 1;

    if claimed_id is null and not exists (
        select 1 from public.scraper_jobs where status in ('queued', 'running')
    ) then
        select s.* into selected_schedule
        from public.scraper_schedules s
        where s.enabled and public.scraper_schedule_slot(s, now(), true) is not null
        order by s.last_slot nulls first, s.id for update of s skip locked limit 1;

        if found then
            selected_slot := public.scraper_schedule_slot(selected_schedule, now(), true);
            insert into public.scraper_jobs (scraper, mode, torneo_id, categoria, fecha, requested_by)
            values (selected_schedule.scraper, 'execute', selected_schedule.torneo_id,
                    selected_schedule.categoria, selected_schedule.fecha, selected_schedule.requested_by)
            on conflict do nothing returning id into claimed_id;
            if claimed_id is not null then
                update public.scraper_schedules set last_slot = selected_slot, last_job_id = claimed_id
                where id = selected_schedule.id;
            end if;
        end if;
    end if;

    if claimed_id is null then return; end if;
    return query update public.scraper_jobs
        set status = 'running', worker_id = p_worker_id, started_at = now(), heartbeat_at = now(),
            finished_at = null, exit_code = null, output = '', error_message = null
        where id = claimed_id returning *;
end;
$$;

revoke all on function public.scraper_schedule_slot(public.scraper_schedules, timestamptz, boolean)
    from public, anon, authenticated;
revoke all on function public.scraper_schedule_rearmed() from public, anon, authenticated;
revoke all on function public.list_scraper_schedules() from public, anon, authenticated;
grant execute on function public.list_scraper_schedules() to authenticated;
revoke all on function public.claim_scraper_job(text) from public, anon, authenticated;
grant execute on function public.claim_scraper_job(text) to service_role;

commit;
