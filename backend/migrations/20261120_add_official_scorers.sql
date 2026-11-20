begin;

create table public.goleadores_importaciones (
    torneo_id bigint not null references public.torneos(id),
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    emitido_en timestamptz not null,
    importado_en timestamptz not null default now(),
    filas jsonb not null check (jsonb_typeof(filas) = 'array' and jsonb_array_length(filas) > 0),
    primary key (torneo_id, sha256)
);

create index goleadores_importaciones_recientes
    on public.goleadores_importaciones (torneo_id, emitido_en desc, importado_en desc, sha256 desc);

alter table public.goleadores_importaciones enable row level security;
revoke all on public.goleadores_importaciones from public, anon, authenticated;
grant select, insert on public.goleadores_importaciones to service_role;

create function public.goleadores_actuales(p_torneo_id bigint, p_categoria_id integer)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'emitido_en', informe.emitido_en,
        'filas', coalesce((
            select jsonb_agg(jsonb_build_object(
                'nombre', fila.nombre,
                'club_id', fila.club_id,
                'club', club.nombre,
                'goles', fila.goles
            ) order by fila.goles desc, club.nombre, fila.nombre)
            from jsonb_to_recordset(informe.filas) as fila(
                categoria_id integer, club_id integer, nombre text, goles integer
            )
            join public.clubes as club on club.id = fila.club_id
            where fila.categoria_id = p_categoria_id
        ), '[]'::jsonb)
    )
    from public.goleadores_importaciones as informe
    where informe.torneo_id = p_torneo_id and p_categoria_id between 1 and 5
    order by informe.emitido_en desc, informe.importado_en desc, informe.sha256 desc
    limit 1;
$$;

revoke all on function public.goleadores_actuales(bigint, integer) from public, anon, authenticated;
grant execute on function public.goleadores_actuales(bigint, integer) to anon, authenticated;

commit;
