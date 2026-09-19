# Tournament Script Modernization

## Objective

Modernize the backend tournament operations so future competitions can be imported, updated, audited, and corrected through a consistent, safe, tournament-scoped workflow.

## Problem

The newer audit/import scripts are dry-run-first and tournament-aware, while the recurring result, schedule, and lineup scrapers still mix parsing, database writes, process orchestration, and deployment. Some silently default to tournament ID 1, duplicate club/category maps, suppress errors, and expose incompatible command-line interfaces used by the control panel and shell runners.

## Why

Tournament IDs are immutable historical identities. Every database mutation must be explicitly scoped, previewable, observable, and safe to reuse for future tournaments without editing source code.

## Scope

- Shared runtime validation and database-write conventions for backend operational scripts.
- Recurring schedule, result, and lineup scrapers.
- Current fixture importer generalization where the official source permits it.
- Control panel and shell-runner compatibility.
- Focused automated tests around pure parsing/planning logic and CLI safety.
- Final operator documentation.

## Non-goals

- Frontend redesign.
- Database schema changes beyond already prepared RLS SQL.
- Automatic champion inference.
- Push, pull request creation, deployment, or production database execution.
- Rewriting the official website or depending on undocumented external APIs.

## Constraints

- Active competition: `torneo_id=2`, `Primavera/Verano 2026`.
- Never reuse tournament IDs.
- Champions remain explicit `palmares` records.
- Database-writing commands are dry-run-first and require `--execute`.
- Tournament selection must be explicit or resolved from validated environment configuration; never silently fall back to ID 1.
- No implicit deployment from data ingestion.
- Existing uncommitted multi-tournament changes must not be lost or mixed with unrelated frontend work.
- Technical artifacts are written in English; operator-facing commands may retain established repository language.

## Execution Configuration

- Workflow: Organic Driven Development (ODD).
- Branch: `refactor/tournament-operations`.
- TDD mode: off; source: existing project state has no configured test runner and no explicit TDD selection.
- Verification: ordinary focused checks using Python stdlib `unittest` where added, `py_compile`, CLI help/dry-run checks, and integration readbacks without production writes.
- Delivery strategy: `ask-on-risk`.
- Chain strategy: `feature-branch-chain`; keep cohesive work-unit commits on this feature branch and define future review slices from those boundaries.
- Estimated authored change: over 400 diff lines across the feature; slice by cohesive work units.
- Native RDD: disabled for the current clone; ordinary verification applies.

## Product Decisions

- Current fixture imports use versioned source profiles: shared engine, explicit URLs/season/format metadata, and no hidden tournament defaults.
- Fixture import never changes active tournament state. Activation is a separate explicit validated operation.
- Existing tournament fixtures abort by default. An explicit replacement operation may replace only fully validated tournament/category scope; append semantics are forbidden.
- Audit/comparison exit codes are `0` for no drift, `1` for verified differences, and `2` for operational or validation failure.

## Tasks

### OPS-001 — Establish shared operational contract and test seam

- [x] Centralize environment loading, positive tournament ID validation, common club/category identity, and lazy Supabase creation.
- [x] Define reusable CLI conventions and structured operation summaries without forcing production credentials for `--help` or unit tests.
- [x] Add focused stdlib tests for validation and configuration behavior.
- Route: delegated writer; trigger: multi-file write and preparation across shared config/tests.
- Allowed scope: `backend/scripts/config.py`, new narrow helper modules under `backend/scripts/`, focused tests under `backend/tests/`, `backend/requirements.txt` only if necessary.
- Checks: unit tests, `py_compile`, credential-free CLI/import smoke test.
- Evidence: 13 stdlib tests passed in writer verification, independent verification, and parent spot-check; `py_compile` passed; credential-free imports passed and resolved configured tournament ID 2 from `backend/.env` without creating a Supabase client.
- Review note: independent verification correctly reported remaining eager/default-ID behavior in schedule and lineup scripts; those are planned scope for OPS-002 and OPS-004, not an OPS-001 regression.
- Commit: `9654c96` (`refactor(backend): establish safe operation contract`).

### OPS-002 — Rebuild schedule ingestion safely

- [x] Separate fetch, parse, match planning, reporting, and execution.
- [x] Add `--torneo-id`, dry-run default, explicit `--execute`, and nonzero failure exits.
- [x] Reject ambiguous or missing fixture matches instead of updating the first row.
- [x] Add parser/planner tests with local fixtures.
- Route: delegated writer; trigger: multi-file implementation and tests.
- Allowed scope: `backend/scripts/scraper_horarios.py`, shared backend helper modules, `backend/tests/` fixtures/tests.
- Checks: focused unit tests, `py_compile`, `--help`; no DB writes.
- Evidence: 26 tests passed after writer verification, independent verification, three added safety-branch tests, and parent spot-check. `py_compile`, credential-free `--help`, and side-effect-free import passed. No network or DB write was used for verification.
- Review note: no deterministic functional defect found. Direct tests now cover inventory safety-bound rejection, duplicate target rejection, and update-error propagation to exit code 2. Control-panel/runner compatibility remains intentionally assigned to OPS-006.
- Commit: `8866a2a` (`refactor(backend): make schedule ingestion safe`).

### OPS-003 — Rebuild result ingestion and standings refresh

- [x] Separate parsing, result-change planning, standings calculation, and execution.
- [x] Add explicit tournament selection, dry-run default, `--execute`, visible failures, and transactional-style prevalidation.
- [x] Remove automatic lineup/deploy invocation.
- [x] Preserve tournament-scoped standings behavior and test calculations/edge cases.
- Route: delegated writer; trigger: multi-file implementation and tests.
- Allowed scope: `backend/scripts/scraper_resultados.py`, shared backend helper modules, `backend/tests/` fixtures/tests.
- Checks: focused unit tests, `py_compile`, dry-run/CLI smoke checks; no DB writes.
- Evidence: 55 tests passed after writer verification, independent review, two correction rounds, final independent PASS, and parent spot-check. `py_compile`, credential-free `--help`, and side-effect-free import passed. Production code contains no subprocess, lineup, pnpm, deploy, or positions-delete references.
- Review corrections: incomplete official result rows now fail closed; played fixtures with missing participants block projection; existing position rows require positive IDs; update actions always filter by position ID, tournament, category, and club. Sequential remote writes remain non-transactional, mitigated by complete prevalidation and narrow filters.
- Commit: `6800023` (`refactor(backend): make result ingestion safe`).

### OPS-004 — Rebuild lineup ingestion safely

- [x] Separate parsing and mutation planning from database execution.
- [x] Replace `--dry-run`/implicit-write asymmetry with dry-run default and explicit `--execute`.
- [x] Remove deploy behavior and duplicated identity maps.
- [x] Prevalidate a complete replacement before deleting existing lineups.
- [x] Add parser/planner tests for goals, cards, encoding, and missing matches.
- Route: delegated writer; trigger: multi-file implementation and tests.
- Allowed scope: `backend/scripts/scraper_alineaciones.py`, shared backend helper modules, `backend/tests/` fixtures/tests.
- Checks: focused unit tests, `py_compile`, CLI smoke checks; no DB writes or deploy.
- Evidence: 79 tests passed after writer verification, independent review, recovery from one failed correction worker, two targeted coverage repairs, final independent PASS, and parent spot-check. `py_compile`, credential-free `--help`, and side-effect-free import passed. Production contains no deploy, subprocess, result, state, or standings writes.
- Review corrections: header scores and attributed goal events must match exactly; malformed, missing, unknown, or ambiguous scorers fail closed; fixture inventory validates estado; omitted played fixtures block while pending/postponed/libre omissions are allowed. The sequential delete/insert/update replacement remains non-transactional and is reported explicitly.
- Commit: `5c0716c` (`refactor(backend): make lineup ingestion safe`).

### OPS-005 — Generalize and rationalize tournament import utilities

- [x] Extract one pure historical-source core shared by audit, comparison, correction, and historical import while keeping their command responsibilities separate.
- [x] Redesign the current fixture importer around explicit versioned source profiles and scoped replacement, without activation side effects.
- [x] Add a separate validated tournament activation operation and align position initialization/palmares with the shared contract.
- [x] Reuse shared identities/configuration and align safety/exit/reporting conventions.
- [x] Confirm initialization, historical import, correction, audit, comparison, and palmares utilities remain necessary and compatible; no retained utility is functionally redundant.
- [x] Remove or merge only genuinely redundant code with behavior preserved by tests; mapping found no additional utility eligible for removal.
- Route: delegated writer; trigger: broad multi-file utility integration.
- Allowed scope: tournament import/audit/correction scripts under `backend/scripts/`, shared helpers, focused `backend/tests/`.
- Checks: focused unit tests, `py_compile`, all CLI `--help` invocations, dry-run parsing against official sources when available.
- Evidence (historical-source work unit): 101 tests passed after writer verification, independent findings, targeted integrity correction, final independent PASS, and parent spot-check. Shared core validates LIBRE scores, fixture/standings participant asymmetry, aliases, duplicate/conflicting keys, and text/JSON drift exits. Imports/help are credential/network safe.
- Commit (historical-source work unit): `c664186` (`refactor(backend): centralize historical source parsing`).
- Evidence (current fixture profiles): 135 tests passed after writer verification, two independent findings/corrections (exact-count pagination and valid LIBRE inventory continuity), final independent PASS, and parent spot-check. Existing replacement scope is paginated with exact stable counts, strict identities/states, dependency blockers, no append, and no activation.
- Commit (current fixture profiles): `2b2b540` (`refactor(backend): add versioned fixture profiles`).
- Evidence (activation/setup utilities): 162 tests passed with `py_compile`, credential-free imports, and all setup `--help` paths. Final independent PASS followed corrections for explicit setup IDs, exact profile completeness, source-owned participation, and deterministic `id` ordering on every paginated inventory. Activation is target-first with narrow deactivation; initialization is fixture-derived and insert-only; palmares remains explicit and conflict-safe. No production write occurred.
- Commit (activation/setup utilities): `aa7e496` (`feat(ops): finalize tournament setup commands`).

### OPS-006 — Update operational integrations

- [ ] Update the control panel to pass tournament IDs and use preview/execute actions explicitly.
- [ ] Update shell runners to use the project environment/venv without installing dependencies on every run.
- [ ] Remove implicit deploy assumptions and preserve clear confirmations.
- [ ] Keep automation backwards-safe or document deliberate command changes.
- Route: delegated writer; trigger: multi-file integration update.
- Allowed scope: `scripts/control-panel/`, `scripts/run_scraper_horarios.sh`, `scripts/run_scraper_resultados.sh`, related narrow runner files.
- Checks: Python compile/tests for control panel, shell syntax checks where available, command-construction tests/readback.
- Commit: pending.

### OPS-007 — Verify and document the final operator workflow

- [ ] Run the complete backend test suite, compile all retained scripts, and exercise every `--help`/dry-run path without writes.
- [ ] Confirm no retained command silently targets tournament ID 1 or triggers deployment.
- [ ] Write `backend/README_OPERACIONES.md` with safe workflows, risk levels, recovery, and exact command order.
- [ ] Reconcile or replace stale command documentation in `COMANDOS.md`.
- Route: delegated verification plus bounded documentation writer; trigger: command-running verification and multi-file docs.
- Allowed scope: `backend/README_OPERACIONES.md`, `COMANDOS.md`, test/read-only verification over operational files.
- Checks: complete documented command matrix and clean verification report.
- Commit: pending.

## Acceptance Criteria

1. Every retained DB-writing Python entry point is dry-run-first and requires `--execute` to mutate data.
2. Every mutation is scoped to a validated positive tournament ID; no silent fallback to tournament ID 1 remains.
3. Parsing/planning logic can be imported and tested without Supabase credentials or network access.
4. Data ingestion never triggers deployment implicitly.
5. Schedule/result/lineup operations fail visibly with useful exit codes and do not partially mutate after failed prevalidation.
6. Club and category identities have one authoritative definition or an explicitly justified boundary.
7. Control panel and shell runners use the new contract correctly.
8. Future-tournament setup and recurring operations are documented and verified without writing to production during tests.
9. Each completed task has observed checks and a local Conventional Commit recorded below.

## Progress and Evidence

- 2026-09-15: User authorized full modernization, a feature branch, and local work-unit commits. No push or deploy authorized.
- 2026-09-15: Created branch `refactor/tournament-operations` from the existing dirty `main` working tree.
- 2026-09-15: User selected `feature-branch-chain` for future review slicing; no push or PR creation is authorized.
- Exploration found that control-panel actions and shell runners depend on the legacy implicit-write CLIs.
- OPS-001 completed in commit `9654c96`: shared validation, lazy Supabase compatibility, dry-run-first CLI helpers, and 13 tests.
- OPS-002 completed in commit `8866a2a`: side-effect-free schedule parsing/planning, dry-run-first execution, deterministic tournament fixture matching, blocking safety validation, and 13 schedule-focused tests (26 total).
- OPS-003 completed in commit `6800023`: safe result planning, fixture-derived projected standings, non-destructive scoped position synchronization, no deploy coupling, fail-closed source/inventory integrity, and 29 result-focused tests (55 total).
- OPS-004 completed in commit `5c0716c`: Primera-only lineup replacement with side-effect-free parsing, strict score/event integrity, estado-aware complete coverage, tournament/round scoping, no result/deploy ownership, and 24 lineup-focused tests (79 total).
- OPS-005 mapping found no fully redundant utility. Historical source parsing is duplicated between audit and comparison, while correction/import already reuse comparison. The current fixture importer remains explicitly 2026-specific.
- OPS-005 product decisions: versioned source profiles; activation as a separate operation; abort-by-default with explicit scoped replacement and no append; audit/comparison codes 0=no drift, 1=drift, 2=error.
- OPS-005 historical-source work unit completed in commit `c664186`: one shared parser/catalog/integrity core, distinct audit/comparison/correction/import commands, drift-aware exits, and 22 historical-focused tests (101 total).
- OPS-005 current-fixture work unit completed in commit `2b2b540`: versioned source profiles without DB identity, explicit profile/scope, exact-count paginated dependency inspection, fail-closed scoped replacement, inactive-only creation, active-state preservation, and 34 fixture-focused tests (135 total).
- OPS-005 activation/setup work unit completed in commit `aa7e496`: explicit setup IDs, immutable 307-row profile completeness, stable exact pagination, fixture-derived participant membership, validated target-first activation, safe position initialization, and explicit palmares mutation. Writer and independent verification passed 162 tests; production schema assumptions were confirmed read-only through Supabase MCP.
- Mapping incident: a fallback read-only mapper initialized `.codegraph/`. User authorized deletion; exact CodeGraph server/watchdog processes were stopped, the 4.5 MB generated index was removed, and `.codegraph/` was ignored in commit `bb8a259`.
- Delegated exploration was attempted twice but the configured explorer failed before returning a report; parent continued read-only mapping as the documented fallback.

## Next Step

Implement OPS-006 by updating the control panel and shell runners to the explicit tournament, preview/execute, project-venv contract without production writes or implicit deployment.
