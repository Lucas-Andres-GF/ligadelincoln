# Result Sync Repair

## Goal
Safely audit the published main branch, repair current official-result parsing, and synchronize only validated Primavera/Verano 2026 results.

## Tasks
- [x] AUD-001 Confirm local and GitHub `main` are identical and the worktree is clean.
  - Evidence: both point to `fc1c5b6`; remote-only commit count is zero.
- [x] RES-001 Support the official site's nested result tables without changing score or scope semantics.
- [x] RES-002 Run backend/frontend verification and a tournament-scoped dry-run for all categories.
- [x] RES-003 Apply only a valid nonempty result plan, then verify `partidos` and `posiciones` readback.
  - Applied Septima and Novena only: 5 results, 10 position rows, 0 issues. Readback confirmed; post-check dry-run is a no-op.

## Constraints
- Tournament scope is explicitly `torneo_id=2`.
- Official category pages are the only result source.
- Missing scores are not results and must never become `0-0`.
- Dry-run must complete with zero blocking issues before `--execute`.
- No commit, push, deploy, or unrelated production mutation without explicit authorization.

## Current findings
- `scraper_resultados.py` fails safely with `No result rows found for category primera`.
- The real category page wraps its result table in another table; `_TableParser` currently extracts only depth-1 rows.
- Primera Fecha 1 currently contains blank score cells.
