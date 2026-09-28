# Own-goal lineup support

## Goal
Ingest official lineup pages containing `(E/C)` goal events without misattributing goals, while preserving the own-goal scorer and displaying the event on the scoring side.

## Tasks
- [x] OWN-GOAL-001 Define and version the `alineaciones.goles_en_contra` schema extension with safe defaults and ACL/RLS compatibility.
  - Evidence: 4 focused migration contract tests pass; independent verifier GO.
  - Commit: `1ce4789` (`feat(db): store lineup own goals`).
- [x] OWN-GOAL-002 Parse `(E/C)` events, validate the scorer against the conceding lineup, tolerate the observed `ERIK`/`ERIC` source variant without weakening unique matching, and persist own-goal counts separately from normal goals.
  - Evidence: 35 focused scraper tests pass; independent verifier GO.
  - Commit: `7a0f8b6` (`fix(scraper): support own-goal lineup events`).
- [x] OWN-GOAL-003 Display own-goal events as `(E/C)` on the beneficiary/scoring side in current fixture views.
  - Evidence: 23 frontend tests and Astro production build pass; independent verifier GO.
  - Commit: `e61de32` (`feat(frontend): display own-goal scorers`).
- [x] OWN-GOAL-004 Verify focused/backend/frontend suites and the live Fecha 2 dry-run; apply production DDL and scraper execution only after explicit authorization.
  - Evidence: 227 backend tests, 23 frontend tests, Astro build, and `git diff --check` pass. Live dry-run planned 3 fixture replacements and 108 lineup rows with zero blockers.
  - Production: user explicitly authorized and applied the migration; schema readback confirmed `integer NOT NULL DEFAULT 0` plus the non-negative constraint. Authorized execution replaced 3 fixtures/108 rows and updated 3 metadata records.
  - Readback: each fixture has 36 lineup rows; fixture 416 records `SMITH ERIC` with `goleo=0`, `goles_en_contra=1`, plus BRACCONI JULIAN with one normal goal.

## Constraints
- Tournament scope remains `torneo_id=3`; `alineaciones` is bounded through tournament-scoped fixtures.
- Missing or ambiguous players continue to fail closed.
- Own goals must not increase the player's normal `goleo` tally or goleadores table totals.
- Existing lineup rows default to zero own goals.
- All mutations remain dry-run-first and require explicit production authorization.
- Local work-unit commits, production migration, and Fecha 2 execution were explicitly authorized. Push and merge remain separate decisions.

## Evidence
- Official source row contains `ERIK SMITH (E/C)` for a Villa Francia score increase.
- The conceding Dep. Gral. Pinto lineup contains `SMITH ERIC`.
- Current parser matches scorers only against the scoring team and treats `(E/C)` as part of the name, causing a fail-closed parse error.
