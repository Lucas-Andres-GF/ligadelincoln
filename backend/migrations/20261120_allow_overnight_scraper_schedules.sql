begin;

alter table public.scraper_schedules
    drop constraint scraper_schedules_check1,
    add constraint scraper_schedules_whole_minute_times
        check (start_time < time '24:00' and end_time < time '24:00'
               and extract(second from start_time) = 0 and extract(second from end_time) = 0);

alter policy schedules_admin_insert on public.scraper_schedules with check (
    public.is_liga_admin() and requested_by = (select auth.uid())
    and (run_date is null
         or (run_date + case when end_time < start_time then 1 else 0 end) + end_time >=
             date_trunc('minute', now() at time zone 'America/Argentina/Buenos_Aires'))
);

-- A window can still be open after midnight on the day after its start.
create or replace function public.scraper_schedule_slot(
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
        select day + schedule.start_time as starts,
               (day + case when schedule.end_time < schedule.start_time then 1 else 0 end)
                   + schedule.end_time as ends,
               local_now, make_interval(mins => schedule.interval_minutes) as period
        from clock
        cross join lateral (
            select schedule.run_date as day where schedule.run_date is not null
            union all
            select local_now::date + offset_days
            from generate_series(-1, case when due then 0 else 7 end) as offsets(offset_days)
            where schedule.weekday = extract(isodow from local_now::date + offset_days)
        ) as days
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
        where local_now < ends + interval '1 minute'
          and (not due or local_now >= starts)
    )
    select min(local_slot at time zone 'America/Argentina/Buenos_Aires')
    from slots
    where schedule.enabled and local_slot <= ends
      and (local_slot at time zone 'America/Argentina/Buenos_Aires') >= schedule.active_since
      and (schedule.last_slot is null
           or (local_slot at time zone 'America/Argentina/Buenos_Aires') > schedule.last_slot);
$$;

commit;
