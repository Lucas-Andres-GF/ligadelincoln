# Champions history

## Goal
Publish the approved Apertura and Clausura 2026 champions for every category, including shared lower-division titles, while preserving `palmares` as the sole champion authority.

## Approved dry-run candidates

### Apertura 2026 (`torneo_id=1`)
- Primera (`categoria_id=1`): Dep. Gral Pinto (`club_id=7`).
- Séptima (`categoria_id=2`): Argentino (`club_id=1`).
- Octava (`categoria_id=3`): El Linqueño (`club_id=8`).
- Novena (`categoria_id=4`): CA. Pintense (`club_id=4`).
- Décima (`categoria_id=5`): El Linqueño (`club_id=8`).

### Clausura 2026 (`torneo_id=2`)
- Primera (`categoria_id=1`): Dep. Arenaza (`club_id=6`), already present and confirmed by explicit palmarés after a points tie/final.
- Séptima (`categoria_id=2`): Atl. Pasteur (`club_id=2`).
- Octava (`categoria_id=3`): Argentino (`club_id=1`).
- Novena (`categoria_id=4`): San Martin (`club_id=10`).
- Décima (`categoria_id=5`): shared by Atl. Pasteur (`club_id=2`) and Argentino (`club_id=1`).

## Tasks
- [x] CHAMP-001 Extend the safe palmarés operation to support an explicit second co-champion without weakening single-champion conflict detection.
  - Evidence: 25 focused setup/palmarés tests pass; independent verifier GO.
  - Commit: `49f4a13` (`feat(palmares): support explicit cochampions`).
- [x] CHAMP-002 Render all official champions for each tournament/category and clearly identify shared titles.
  - Evidence: 29 frontend tests and Astro production build pass; independent verifier GO.
  - Commit: `ad1cac1` (`feat(frontend): display shared championships`).
- [x] CHAMP-003 Run focused/full tests and a zero-write dry-run for all 11 approved records.
  - Evidence: 234 backend tests, 29 frontend tests, Astro build, and `git diff --check` pass.
  - Production-state dry-run: 9 inserts, 1 exact no-op (Clausura Primera/Arenaza), and 1 expected staged block for the second Clausura Décima co-champion because the first candidate was intentionally not persisted. Zero mutations attempted.
  - Commit: recorded in the ODD evidence work unit.
- [ ] CHAMP-004 Apply only the confirmed palmarés changes after explicit production authorization, verify readback/public display, then prepare delivery.

## Constraints
- `palmares` remains the only champion authority; standings provide review evidence only.
- Active tournament `torneo_id=3` receives no champion.
- Primera ties require explicit final evidence; existing Dep. Arenaza palmarés is retained.
- Lower-division first-place ties produce co-champions.
- A second champion requires an explicit co-champion flag and at most two distinct clubs per tournament/category.
- Every operation remains dry-run-first; no production writes, push, or merge without explicit authorization.
