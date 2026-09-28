-- RLS hardening for Liga de Lincoln public data.
-- Execute this in the Supabase SQL Editor after reviewing.
-- Goal:
--   - Public visitors can read site data.
--   - Anonymous visitors cannot insert/update/delete.
--   - Only the configured authenticated admin can write.
--   - Service-role backend jobs continue to bypass RLS as usual.

begin;

-- Keep the admin decision in one place and restrict direct invocation.
create or replace function public.is_liga_admin()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce(auth.jwt() ->> 'email', '') = 'gallardolucas003@gmail.com';
$$;

revoke all privileges on function public.is_liga_admin()
from public, anon, authenticated;
grant execute on function public.is_liga_admin() to authenticated;

-- Make direct table privileges match the intended RLS access model. Resetting
-- all privileges also removes TRUNCATE, REFERENCES, TRIGGER, and MAINTAIN where
-- the PostgreSQL version supports them.
revoke all privileges on table
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
from public, anon, authenticated;

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

-- Sequences do not support RLS. Authenticated inserts need nextval() for
-- generated IDs, but no JWT role needs to inspect or mutate sequence state.
revoke all privileges on all sequences in schema public
from public, anon, authenticated;
grant usage on all sequences in schema public to authenticated;

-- Fail closed for objects created later by either Supabase application owner.
-- postgres defaults are always hardened in this transaction. supabase_admin
-- defaults are hardened only when the SQL Editor identity is a member of that
-- role; otherwise the warning requires residual-drift review after commit.
-- Future migrations must grant every intended table, sequence, and function ACL.
alter default privileges for role postgres in schema public
  revoke all privileges on tables from public, anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all privileges on sequences from public, anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all privileges on functions from public, anon, authenticated;

do $$
begin
  if pg_catalog.pg_has_role(current_user, 'supabase_admin', 'MEMBER') then
    execute 'ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public REVOKE ALL PRIVILEGES ON TABLES FROM public, anon, authenticated';
    execute 'ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public REVOKE ALL PRIVILEGES ON SEQUENCES FROM public, anon, authenticated';
    execute 'ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public REVOKE ALL PRIVILEGES ON FUNCTIONS FROM public, anon, authenticated';
    raise notice 'Applied supabase_admin default ACL hardening.';
  else
    raise warning 'Skipped supabase_admin default ACL hardening: current user % is not a member of supabase_admin; existing-object ACLs and postgres defaults will still commit.', current_user;
  end if;
end $$;

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
