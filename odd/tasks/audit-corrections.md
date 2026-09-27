# Audit Corrections

## Goal
Repair the verified post-audit defects without weakening tournament scoping, dry-run safety, or independent category validation.

## Tasks
- [x] AUD-FIX-001 Isolate live result ingestion by category so one unavailable category cannot block valid categories.
  - Preserve fail-closed behavior for the unavailable category.
  - Add regression tests for mixed available/unavailable category sources.
  - Verify current live sources without `--execute`.
  - Evidence: runner now invokes all five categories independently, preserves the first failure status, and continues after failures; 4 runner tests, 8 CLI safety tests, Bash syntax, and scoped diff checks passed.
  - Commit: `6cddbe7` (`fix(ops): isolate result scraper categories`).
- [x] AUD-FIX-002 Normalize manual scored matches to `jugado` from non-terminal observation states.
  - Keep suspended matches scoreless.
  - Prevent fixture/result links that resolve to SSR 404.
  - Add focused frontend behavior coverage where practical.
  - Evidence: shared match-state utility is used by admin, fixture/home listings, and SSR; 17 frontend tests and production build passed under independent verification.
  - Commit: `8aa5386` (`fix(frontend): normalize played match state`).
- [x] AUD-FIX-003 Pin the frontend runtime to Node 22 for local/Vercel parity.
  - Evidence: `frontend/package.json` declares `engines.node=22.x`, `frontend/.nvmrc` selects 22, and the 17-test frontend suite passed.
  - Commit: `8aa5386` (`fix(frontend): normalize played match state`).
- [x] AUD-FIX-004 Remove the whitespace defect and run the full verification matrix.
  - Backend tests.
  - Frontend tests and production build.
  - Shell syntax checks.
  - `git diff --check`.
  - Live scraper dry-runs without database writes.
  - Evidence: 215 backend tests and 17 frontend tests passed; production build, Bash syntax, and diff checks passed. Live dry-runs succeeded for horarios, alineaciones, Primera, Octava, Novena, and Décima; Séptima failed closed as expected because its official page has no latest-results table.
  - Commit: `6cddbe7` (`fix(ops): isolate result scraper categories`).

## Constraints
- Active tournament remains `torneo_id=3`.
- Missing or malformed scores never become `0-0`.
- An unavailable category must never authorize writes for that category.
- Every production mutation remains dry-run-first and requires explicit `--execute`.
- No database writes, deploy, or merge are included.
- Commit and branch push were explicitly authorized after verification.

## Evidence
- Audit baseline: local `HEAD=bd5a574`, `origin/main=ac26456`, clean worktree before this task document.
- Live baseline: Primera plans 2 result updates; Octava 1; Novena 1; Décima 3; Séptima has no `ÚLTIMOS ENCUENTROS` table and aborts the combined run.
- Verification baseline: backend 213 tests passed; frontend 8 tests passed; Astro/Vercel build passed; Bash syntax passed; `git diff --check` failed only on `backend/tests/test_scraper_resultados.py:990`.
