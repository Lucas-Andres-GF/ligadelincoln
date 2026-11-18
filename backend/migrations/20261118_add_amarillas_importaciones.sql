begin;

create table public.amarillas_importaciones (
    torneo_id bigint not null references public.torneos(id),
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    emitido_en timestamptz not null,
    importado_en timestamptz not null default now(),
    pdf_base64 text not null check (
        length(pdf_base64) between 8 and 6666668 and left(pdf_base64, 7) = 'JVBERi0'
    ),
    filas jsonb not null check (jsonb_typeof(filas) = 'array' and jsonb_array_length(filas) > 0),
    primary key (torneo_id, sha256)
);

create index amarillas_importaciones_recientes
    on public.amarillas_importaciones (torneo_id, emitido_en desc, importado_en desc);

alter table public.amarillas_importaciones enable row level security;
revoke all on public.amarillas_importaciones from public, anon, authenticated;
grant select, insert on public.amarillas_importaciones to service_role;

-- Expose only the current report and its public fields. COMET IDs remain private.
create function public.amarillas_actuales(p_torneo_id bigint)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'emitido_en', informe.emitido_en,
        'filas', (
            select jsonb_agg(jsonb_build_object(
                'nombre', fila -> 'nombre',
                'club', fila -> 'club',
                'club_id', fila -> 'club_id',
                'rol', fila -> 'rol',
                'amarillas', fila -> 'amarillas'
            ) order by posicion)
            from jsonb_array_elements(informe.filas) with ordinality as datos(fila, posicion)
        )
    )
    from public.amarillas_importaciones as informe
    where informe.torneo_id = p_torneo_id
    order by informe.emitido_en desc, informe.importado_en desc, informe.sha256 desc
    limit 1;
$$;

revoke all on function public.amarillas_actuales(bigint) from public, anon, authenticated;
grant execute on function public.amarillas_actuales(bigint) to anon, authenticated;

commit;
