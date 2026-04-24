-- Migration: Add goals count column to alineaciones
ALTER TABLE alineaciones ADD COLUMN IF NOT EXISTS goals INTEGER DEFAULT 0;
UPDATE alineaciones SET goals = 1 WHERE goleo = true;
ALTER TABLE alineaciones DROP COLUMN IF EXISTS goleo;
ALTER TABLE alineaciones RENAME COLUMN goals TO goleo;