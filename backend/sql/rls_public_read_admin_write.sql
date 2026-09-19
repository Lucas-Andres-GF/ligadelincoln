-- RLS hardening for Liga de Lincoln public data.
-- Execute this in the Supabase SQL Editor after reviewing.
-- Goal:
--   - Public visitors can read site data.
--   - Anonymous visitors cannot insert/update/delete.
--   - Only the configured authenticated admin can write.
--   - Service-role backend jobs continue to bypass RLS as usual.

begin;

-- Keep the admin decision in one place.
create or replace function public.is_liga_admin()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce(auth.jwt() ->> 'email', '') = 'gallardolucas003@gmail.com';
$$;

-- Make table privileges match the intended access model.
-- Revoke inherited PUBLIC access first so role-specific grants cannot be bypassed.
revoke insert, update, delete on table
  public.alineaciones,
  public.categorias,
  public.clubes,
  public.fechas,
  public.goleadores,
  public.goleadores_partido,
  public.jugadores,
  public.palmares,
  public.participaciones,
  public.partidos,
  public.posiciones,
  public.sanciones,
  public.torneos
from public;

grant select on table
  public.alineaciones,
  public.categorias,
  public.clubes,
  public.fechas,
  public.goleadores,
  public.goleadores_partido,
  public.jugadores,
  public.palmares,
  public.participaciones,
  public.partidos,
  public.posiciones,
  public.sanciones,
  public.torneos
to anon, authenticated;

revoke insert, update, delete on table
  public.alineaciones,
  public.categorias,
  public.clubes,
  public.fechas,
  public.goleadores,
  public.goleadores_partido,
  public.jugadores,
  public.palmares,
  public.participaciones,
  public.partidos,
  public.posiciones,
  public.sanciones,
  public.torneos
from anon;

grant insert, update, delete on table
  public.alineaciones,
  public.categorias,
  public.clubes,
  public.fechas,
  public.goleadores,
  public.goleadores_partido,
  public.jugadores,
  public.palmares,
  public.participaciones,
  public.partidos,
  public.posiciones,
  public.sanciones,
  public.torneos
to authenticated;

-- Sequences do not support RLS. Keep them unavailable to public JWT roles so a
-- non-admin authenticated user cannot call nextval() or inspect sequence state.
-- Inserts that need generated IDs must use the trusted service-role backend.
-- An authenticated admin may still insert a row when supplying an explicit ID.
revoke all privileges on all sequences in schema public from public, anon, authenticated;

-- Remove every existing policy on the application tables before recreating the
-- complete intended set. This prevents an unknown permissive policy surviving a rerun.
do $$
declare
  table_name text;
  policy_name text;
begin
  foreach table_name in array array[
    'alineaciones',
    'categorias',
    'clubes',
    'fechas',
    'goleadores',
    'goleadores_partido',
    'jugadores',
    'palmares',
    'participaciones',
    'partidos',
    'posiciones',
    'sanciones',
    'torneos'
  ] loop
    for policy_name in
      select policy.polname
      from pg_catalog.pg_policy as policy
      where policy.polrelid = format('public.%I', table_name)::regclass
    loop
      execute format('drop policy %I on public.%I', policy_name, table_name);
    end loop;
  end loop;
end $$;

-- Enable RLS everywhere after privileges/policies are prepared in this transaction.
alter table public.alineaciones enable row level security;
alter table public.categorias enable row level security;
alter table public.clubes enable row level security;
alter table public.fechas enable row level security;
alter table public.goleadores enable row level security;
alter table public.goleadores_partido enable row level security;
alter table public.jugadores enable row level security;
alter table public.palmares enable row level security;
alter table public.participaciones enable row level security;
alter table public.partidos enable row level security;
alter table public.posiciones enable row level security;
alter table public.sanciones enable row level security;
alter table public.torneos enable row level security;

-- Public read policies.
create policy public_read on public.alineaciones for select to anon, authenticated using (true);
create policy public_read on public.categorias for select to anon, authenticated using (true);
create policy public_read on public.clubes for select to anon, authenticated using (true);
create policy public_read on public.fechas for select to anon, authenticated using (true);
create policy public_read on public.goleadores for select to anon, authenticated using (true);
create policy public_read on public.goleadores_partido for select to anon, authenticated using (true);
create policy public_read on public.jugadores for select to anon, authenticated using (true);
create policy public_read on public.palmares for select to anon, authenticated using (true);
create policy public_read on public.participaciones for select to anon, authenticated using (true);
create policy public_read on public.partidos for select to anon, authenticated using (true);
create policy public_read on public.posiciones for select to anon, authenticated using (true);
create policy public_read on public.sanciones for select to anon, authenticated using (true);
create policy public_read on public.torneos for select to anon, authenticated using (true);

-- Admin write policies. `using` controls existing rows; `with check` controls new row values.
create policy admin_insert on public.alineaciones for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.alineaciones for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.alineaciones for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.categorias for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.categorias for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.categorias for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.clubes for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.clubes for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.clubes for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.fechas for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.fechas for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.fechas for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.goleadores for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.goleadores for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.goleadores for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.goleadores_partido for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.goleadores_partido for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.goleadores_partido for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.jugadores for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.jugadores for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.jugadores for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.palmares for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.palmares for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.palmares for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.participaciones for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.participaciones for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.participaciones for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.partidos for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.partidos for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.partidos for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.posiciones for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.posiciones for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.posiciones for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.sanciones for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.sanciones for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.sanciones for delete to authenticated using (public.is_liga_admin());

create policy admin_insert on public.torneos for insert to authenticated with check (public.is_liga_admin());
create policy admin_update on public.torneos for update to authenticated using (public.is_liga_admin()) with check (public.is_liga_admin());
create policy admin_delete on public.torneos for delete to authenticated using (public.is_liga_admin());

commit;
