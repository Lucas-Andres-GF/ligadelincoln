-- One-time production ACL migration for the public-read/admin-write RLS model.
-- This migration changes privileges only. It does not alter policies, RLS state, or data.
-- Run from the Supabase SQL Editor as a role allowed to change postgres default
-- privileges. supabase_admin defaults are attempted only with role membership.

begin;

-- Preserve the configured administrator identity while pinning safe function attributes.
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

-- Reset direct ACLs before granting only the privileges required by the RLS model.
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

-- Generated IDs require nextval(), but authenticated clients do not need to read
-- or modify sequence state directly. Anonymous clients receive no sequence access.
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

commit;
