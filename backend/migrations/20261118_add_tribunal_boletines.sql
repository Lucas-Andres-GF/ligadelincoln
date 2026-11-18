begin;

create table public.tribunal_boletines (
    id bigint generated always as identity primary key,
    numero integer not null check (numero > 0),
    fecha date not null,
    fuente text not null,
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    html text not null check (octet_length(html) between 1 and 2000000),
    resoluciones jsonb not null check (jsonb_typeof(resoluciones) = 'array'),
    importado_en timestamptz not null default now()
);

create index tribunal_boletines_versiones on public.tribunal_boletines (numero, id desc);
alter table public.tribunal_boletines enable row level security;
revoke all on public.tribunal_boletines from public, anon, authenticated;

create function public.archivar_boletines_tribunal(p_boletines jsonb)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
    archived integer;
begin
    perform pg_catalog.pg_advisory_xact_lock(71675, 102);
    insert into public.tribunal_boletines (numero, fecha, fuente, sha256, html, resoluciones)
    select item.numero, item.fecha, item.fuente, item.sha256, item.html, item.resoluciones
    from pg_catalog.jsonb_to_recordset(p_boletines) as item(
        numero integer, fecha date, fuente text, sha256 text, html text, resoluciones jsonb
    )
    where item.sha256 is distinct from (
        select previous.sha256 from public.tribunal_boletines as previous
        where previous.numero = item.numero order by previous.id desc limit 1
    );
    get diagnostics archived = row_count;
    return archived;
end;
$$;

create function public.boletines_tribunal(p_division text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    with latest as (
        select distinct on (numero) numero, fecha, resoluciones
        from public.tribunal_boletines
        order by numero, id desc
    )
    select coalesce(jsonb_agg(jsonb_build_object(
        'numero', numero,
        'fecha', fecha,
        'resoluciones', (
            select coalesce(jsonb_agg(jsonb_build_object(
                'nombre', row_data -> 'nombre', 'club', row_data -> 'club',
                'funcion', row_data -> 'funcion', 'sancion', row_data -> 'sancion',
                'division', row_data -> 'division'
            ) order by position), '[]'::jsonb)
            from jsonb_array_elements(resoluciones) with ordinality as rows(row_data, position)
            where row_data ->> 'division' = p_division
        )
    ) order by fecha desc, numero desc), '[]'::jsonb)
    from latest
    where p_division in ('PRIMERA', 'SEPTIMA', 'OCTAVA', 'NOVENA', 'DECIMA');
$$;

revoke all on function public.archivar_boletines_tribunal(jsonb) from public, anon, authenticated;
grant execute on function public.archivar_boletines_tribunal(jsonb) to service_role;
revoke all on function public.boletines_tribunal(text) from public, anon, authenticated;
grant execute on function public.boletines_tribunal(text) to anon, authenticated;

commit;
