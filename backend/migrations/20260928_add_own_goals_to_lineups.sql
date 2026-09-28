-- Add own-goal tracking to lineup records without changing existing data or security.
BEGIN;

ALTER TABLE public.alineaciones
    ADD COLUMN IF NOT EXISTS goles_en_contra integer NOT NULL DEFAULT 0;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'alineaciones_goles_en_contra_non_negative'
          AND conrelid = 'public.alineaciones'::regclass
    ) THEN
        ALTER TABLE public.alineaciones
            ADD CONSTRAINT alineaciones_goles_en_contra_non_negative
            CHECK (goles_en_contra >= 0);
    END IF;
END;
$migration$;

COMMIT;
