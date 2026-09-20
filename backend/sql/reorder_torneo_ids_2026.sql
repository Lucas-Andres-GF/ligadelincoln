-- Reorder tournament IDs to chronological order.
-- Apertura = 1, Clausura = 2, Primavera/Verano = 3.
-- Swaps previous IDs 2 (Primavera/Verano) and 3 (Clausura) atomically.
BEGIN;

INSERT INTO torneos (id, nombre, slug, temporada, activo)
VALUES (900, '__temp__', '__temp__', 2026, false);

UPDATE partidos SET torneo_id = 900 WHERE torneo_id = 3;
UPDATE partidos SET torneo_id = 3 WHERE torneo_id = 2;
UPDATE partidos SET torneo_id = 2 WHERE torneo_id = 900;

UPDATE posiciones SET torneo_id = 900 WHERE torneo_id = 3;
UPDATE posiciones SET torneo_id = 3 WHERE torneo_id = 2;
UPDATE posiciones SET torneo_id = 2 WHERE torneo_id = 900;

UPDATE palmares SET torneo_id = 900 WHERE torneo_id = 3;
UPDATE palmares SET torneo_id = 2 WHERE torneo_id = 900;

UPDATE torneos SET nombre = 'Clausura 2026', slug = 'clausura-2026', activo = false WHERE id = 2;
UPDATE torneos SET nombre = 'Primavera/Verano 2026', slug = 'primavera-verano-2026', activo = true WHERE id = 3;

DELETE FROM torneos WHERE id = 900;

COMMIT;
