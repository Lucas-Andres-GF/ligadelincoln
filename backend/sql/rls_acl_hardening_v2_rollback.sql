-- DANGER: EMERGENCY-ONLY ACL ROLLBACK.
-- This script WEAKENS the security boundary by restoring Supabase-style broad
-- privileges to anon/authenticated and broad future defaults. It should not
-- normally be used. Prefer fixing a missing explicit grant instead.
--
-- Exact limit: this changes only current ACLs for the 13 application tables,
-- all current public sequences, public.is_liga_admin(), future defaults for
-- postgres, and supabase_admin defaults when role membership permits. It does
-- not change RLS, policies, function code/attributes, data, ownership, or
-- service_role grants.
-- PostgreSQL PUBLIC receives function execution only, matching the standard
-- function default; it receives no table or sequence privilege.

begin;

-- Restore the broad current table and sequence privileges commonly provisioned
-- by Supabase. RLS still applies, but direct-privilege least privilege is lost.
grant all privileges on table
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

grant all privileges on all sequences in schema public to anon, authenticated;
grant execute on function public.is_liga_admin()
to public, anon, authenticated;

-- Restore broad defaults only for the owners hardened by the forward migration.
-- postgres defaults are always restored in this transaction. supabase_admin
-- defaults are restored only when the SQL Editor identity is a member of that
-- role; otherwise the warning requires residual-drift review after commit.
alter default privileges for role postgres in schema public
  grant all privileges on tables to anon, authenticated;
alter default privileges for role postgres in schema public
  grant all privileges on sequences to anon, authenticated;
alter default privileges for role postgres in schema public
  grant execute on functions to public, anon, authenticated;

do $$
begin
  if pg_catalog.pg_has_role(current_user, 'supabase_admin', 'MEMBER') then
    execute 'ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO anon, authenticated';
    execute 'ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO anon, authenticated';
    execute 'ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO public, anon, authenticated';
    raise notice 'Restored broad supabase_admin default ACLs.';
  else
    raise warning 'Skipped supabase_admin default ACL rollback: current user % is not a member of supabase_admin; current-object ACLs and postgres defaults will still commit.', current_user;
  end if;
end $$;

commit;
