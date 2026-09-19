-- Emergency rollback only.
-- Use this only if the RLS hardening unexpectedly breaks the site/admin.
-- It disables RLS again on the public application tables.
-- WARNING: it does not restore prior grants or policies. Because authenticated
-- retains table DML grants from the hardening script, disabling RLS removes the
-- admin-email barrier until RLS is enabled again.

begin;

alter table public.alineaciones disable row level security;
alter table public.categorias disable row level security;
alter table public.clubes disable row level security;
alter table public.fechas disable row level security;
alter table public.goleadores disable row level security;
alter table public.goleadores_partido disable row level security;
alter table public.jugadores disable row level security;
alter table public.palmares disable row level security;
alter table public.participaciones disable row level security;
alter table public.partidos disable row level security;
alter table public.posiciones disable row level security;
alter table public.sanciones disable row level security;
alter table public.torneos disable row level security;

commit;
