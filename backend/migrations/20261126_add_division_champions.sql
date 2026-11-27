begin;

-- Opt in only regular leagues and configure how each division handles a tie.
create table public.reglas_campeon_por_puntos (
    torneo_id bigint not null references public.torneos(id),
    categoria_id integer not null references public.categorias(id),
    equipos smallint not null check (equipos >= 2),
    vueltas smallint not null check (vueltas >= 1),
    puntos_victoria smallint not null check (puntos_victoria >= 1),
    comparte_empate boolean not null,
    primary key (torneo_id, categoria_id)
);

revoke all on public.reglas_campeon_por_puntos from public, anon, authenticated;
grant select on public.reglas_campeon_por_puntos to anon, authenticated;
alter table public.reglas_campeon_por_puntos enable row level security;
create policy reglas_campeon_publicas on public.reglas_campeon_por_puntos
    for select to anon, authenticated using (true);

insert into public.reglas_campeon_por_puntos
    (torneo_id, categoria_id, equipos, vueltas, puntos_victoria, comparte_empate)
select torneo.id, division.id, division.equipos, 1, 3, division.id <> 1
from public.torneos as torneo
cross join (values (1, 11), (2, 7), (3, 9), (4, 7), (5, 11)) as division(id, equipos)
where torneo.slug = 'primavera-verano-2026';

-- El Linqueño clinched Décima. Novena can still finish level on points.
insert into public.palmares (torneo_id, categoria_id, club_id, nombre, temporada)
select torneo.id, 5, 8, torneo.nombre, torneo.temporada::text
from public.torneos as torneo
where torneo.slug = 'primavera-verano-2026'
  and not exists (
      select 1 from public.palmares as previo
      where previo.torneo_id = torneo.id and previo.categoria_id = 5
  );

create function public.campeones_de_torneo(
    p_torneo_id bigint default null,
    p_categoria_id integer default null
)
returns table (
    torneo_id bigint, categoria_id integer, club_id bigint, club_nombre text,
    torneo_nombre text, nombre text, temporada text, tipo text,
    puntos bigint, maximo_rival bigint
)
language sql
stable
set search_path = ''
as $$
    with reglas as (
        select r.* from public.reglas_campeon_por_puntos as r
        where (p_torneo_id is null or r.torneo_id = p_torneo_id)
          and (p_categoria_id is null or r.categoria_id = p_categoria_id)
    ), partidos as (
        select p.torneo_id, p.categoria_id, p.local_id, p.visitante_id,
               p.goles_local, p.goles_visitante,
               coalesce(p.estado = 'jugado' and p.goles_local >= 0 and p.goles_visitante >= 0, false) as jugado
        from public.partidos as p
        join reglas as r using (torneo_id, categoria_id)
        where p.local_id is not null and p.visitante_id is not null
    ), cruces as (
        select p.torneo_id, p.categoria_id, count(*) as encuentros
        from partidos as p
        group by p.torneo_id, p.categoria_id,
                 least(p.local_id, p.visitante_id), greatest(p.local_id, p.visitante_id)
    ), por_equipo as (
        select p.torneo_id, p.categoria_id, lado.club_id,
               count(*) filter (where not p.jugado) as pendientes,
               count(*) filter (where p.jugado) as jugados,
               count(*) filter (where p.jugado and lado.goles > lado.recibidos) as ganados,
               count(*) filter (where p.jugado and lado.goles = lado.recibidos) as empatados,
               bool_and(p.local_id <> p.visitante_id) as cruces_validos
        from partidos as p
        cross join lateral (values
            (p.local_id, p.goles_local, p.goles_visitante),
            (p.visitante_id, p.goles_visitante, p.goles_local)
        ) as lado(club_id, goles, recibidos)
        group by p.torneo_id, p.categoria_id, lado.club_id
    ), posiciones as (
        select pos.torneo_id, pos.categoria_id, pos.club_id, pos.pts, pos.pj, pos.pg, pos.pe
        from public.posiciones as pos
        join reglas as r using (torneo_id, categoria_id)
    ), calculo as (
        select r.torneo_id, r.categoria_id, equipo.club_id, pos.pts::bigint as puntos,
               pos.pts + r.puntos_victoria * equipo.pendientes as techo,
               equipo.pendientes, r.comparte_empate
        from reglas as r
        join por_equipo as equipo using (torneo_id, categoria_id)
        left join posiciones as pos using (torneo_id, categoria_id, club_id)
    ), divisiones_validas as (
        select r.torneo_id, r.categoria_id
        from reglas as r
        where (
            select count(*) = r.equipos * (r.equipos - 1) / 2
                   and bool_and(c.encuentros = r.vueltas)
            from cruces as c
            where c.torneo_id = r.torneo_id and c.categoria_id = r.categoria_id
        ) and (
            select count(*) = r.equipos
              and count(distinct pos.club_id) = r.equipos
              and bool_and(coalesce(e.cruces_validos and pos.pts is not null
                  and pos.pj = e.jugados and pos.pg = e.ganados and pos.pe = e.empatados, false))
            from posiciones as pos
            left join por_equipo as e using (torneo_id, categoria_id, club_id)
            where pos.torneo_id = r.torneo_id and pos.categoria_id = r.categoria_id
        ) and (
            select count(*) = r.equipos from por_equipo as e
            where e.torneo_id = r.torneo_id and e.categoria_id = r.categoria_id
        )
    ), oficiales as (
        select p.torneo_id, p.categoria_id, p.club_id, p.nombre, p.temporada
        from public.palmares as p
        where (p_torneo_id is null or p.torneo_id = p_torneo_id)
          and (p_categoria_id is null or p.categoria_id = p_categoria_id)
    ), calculados as (
        select c.torneo_id, c.categoria_id, c.club_id, c.puntos, rival.techo,
               c.puntos = rival.techo as compartido
        from calculo as c
        join divisiones_validas using (torneo_id, categoria_id)
        cross join lateral (
            select max(otro.techo) as techo, bool_and(otro.pendientes = 0) as sin_pendientes
            from calculo as otro
            where otro.torneo_id = c.torneo_id and otro.categoria_id = c.categoria_id
              and otro.club_id <> c.club_id
        ) as rival
        where (c.puntos > rival.techo
               or (c.comparte_empate and c.pendientes = 0 and rival.sin_pendientes
                   and c.puntos = rival.techo))
          and not exists (
              select 1 from oficiales as o
              where o.torneo_id = c.torneo_id and o.categoria_id = c.categoria_id
          )
          and not exists (
              select 1 from public.partidos_definicion as d
              where d.torneo_id = c.torneo_id and d.categoria_id = c.categoria_id
          )
    )
    select o.torneo_id::bigint, o.categoria_id::integer, o.club_id::bigint, club.nombre::text,
           t.nombre::text, o.nombre::text, o.temporada::text, 'oficial'::text, null::bigint, null::bigint
    from oficiales as o
    join public.clubes as club on club.id = o.club_id
    join public.torneos as t on t.id = o.torneo_id
    union all
    select c.torneo_id, c.categoria_id, c.club_id::bigint, club.nombre::text,
           t.nombre::text,
           case when c.compartido then 'Campeonato compartido' else 'Campeón matemático' end,
           t.temporada::text, case when c.compartido then 'compartido' else 'matematico' end,
           c.puntos, c.techo
    from calculados as c
    join public.clubes as club on club.id = c.club_id
    join public.torneos as t on t.id = c.torneo_id;
$$;

revoke all on function public.campeones_de_torneo(bigint, integer) from public, anon, authenticated;
grant execute on function public.campeones_de_torneo(bigint, integer) to anon, authenticated;

commit;
