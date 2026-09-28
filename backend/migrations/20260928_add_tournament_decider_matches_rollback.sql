-- DANGER: This rollback permanently deletes every championship-decider match.
BEGIN;

DROP TABLE IF EXISTS public.partidos_definicion;

COMMIT;
