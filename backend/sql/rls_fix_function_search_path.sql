-- Fix Supabase advisor warning: function_search_path_mutable.
-- This keeps the same admin check but pins search_path for safer execution.

begin;

create or replace function public.is_liga_admin()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce(auth.jwt() ->> 'email', '') = 'gallardolucas003@gmail.com';
$$;

commit;
