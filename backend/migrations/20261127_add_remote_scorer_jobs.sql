begin;

alter table public.scraper_jobs
    drop constraint scraper_jobs_scraper_check,
    drop constraint scraper_jobs_parameters_check,
    add constraint scraper_jobs_scraper_check check (
        scraper in ('horarios', 'resultados', 'alineaciones', 'resultados_alineaciones', 'amarillas', 'boletines', 'goleadores')
    ),
    add constraint scraper_jobs_parameters_check check (
        (scraper in ('horarios', 'amarillas', 'boletines', 'goleadores') and categoria is null and fecha is null)
        or (scraper = 'resultados' and fecha is null)
        or (scraper = 'alineaciones' and categoria is null and fecha is not null)
        or (scraper = 'resultados_alineaciones' and fecha is not null)
    );

commit;
