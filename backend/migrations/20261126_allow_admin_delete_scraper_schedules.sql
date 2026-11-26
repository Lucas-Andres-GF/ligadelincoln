begin;

grant delete on public.scraper_schedules to authenticated;

create policy schedules_admin_delete on public.scraper_schedules
    for delete to authenticated using (public.is_liga_admin());

commit;
