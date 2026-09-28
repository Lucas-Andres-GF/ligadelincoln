# Tournament decider matches

## Goal
Import official championship-decider matches without altering regular standings, and display the two-leg series in the selected historical tournament fixture.

## Confirmed source
- Official URL: `https://www.ligaamateurdedeportes.com.ar/torneos%20anteriores/z2026clausura1ra.html`.
- First leg: CA. Pintense 0–1 Dep. Arenaza, 2026-09-06, at CA. Pintense.
- Second leg: Dep. Arenaza 2–0 CA. Pintense, 2026-09-12, at Dep. Arenaza.
- Aggregate: Dep. Arenaza 3–0 CA. Pintense.
- Official champion: Dep. Arenaza.

## Tasks
- [x] DECIDER-001 Add a scoped `partidos_definicion` table with safe RLS/ACL, constraints, rollback, and contract tests.
  - Evidence: 8 focused migration contract tests pass; independent verifier GO.
  - Commit: `2f6bf32` (`feat(db): add tournament decider matches`).
- [x] DECIDER-002 Implement a dry-run-first official decider importer that validates the two-leg source and never modifies regular `partidos` or `posiciones`.
  - Evidence: 13 focused importer tests pass; independent live diagnostic parsed the exact official legs, 3–0 aggregate, and champion Arenaza.
  - Commit: `7dda129` (`feat(import): parse official decider series`).
- [x] DECIDER-003 Display selected tournament decider series after the regular fixture, including leg labels, aggregate score, source attribution, and champion.
  - Evidence: 30 frontend tests and Astro production build pass; independent verifier GO.
  - Commit: `c5046e7` (`feat(frontend): show championship deciders`).
- [x] DECIDER-004 Run focused/full tests and a live zero-write Clausura dry-run.
  - Evidence: 248 backend tests, 30 frontend tests, Astro production build, and `git diff --check` pass.
  - Live official-source diagnostic parsed both legs, Arenaza's 3–0 aggregate, and champion ID 6 without constructing a DB client or mutating data.
  - Isolation evidence: DECIDER-001 independent review confirmed migrations touch only `partidos_definicion`; importer tests reject any table other than `partidos_definicion`.
  - Commit: recorded in the ODD evidence work unit.
- [ ] DECIDER-005 Apply production DDL/data only after explicit authorization, verify public read/UI, then prepare delivery.
  - Production evidence: user applied the migration; readback confirmed schema, constraints, exact ACLs, RLS, and four policies. Authorized importer dry-run returned `insert` with zero issues and writes; atomic execution inserted two rows.
  - Data readback: Pintense 0–1 Arenaza (2026-09-06) and Arenaza 2–0 Pintense (2026-09-12), champion Arenaza; public REST returned both legs with HTTP 200.
  - Isolation readback: regular Clausura Primera remains 66 fixtures/55 played; Arenaza and Pintense remain tied on 23 points with 10 matches. Repeated importer dry-run returns exact no-op.
  - Delivery pending: push/merge frontend support and verify Vercel public rendering.
  - Review strategy: user explicitly accepted one cohesive PR with `size:exception` (approximately 2,128 changed lines); importer code/tests cannot be split below the normal 400-line budget without separating behavior from its verification.

## Constraints
- Tournament scope: Clausura `torneo_id=2`, Primera `categoria_id=1` for the initial import.
- Decider matches must not count toward regular standings.
- Existing `partidos` and `posiciones` data must remain unchanged.
- Writes require `--execute`; default is dry-run.
- Source structure or aggregate/champion mismatch fails closed.
- Production DDL/data and local work-unit commits were explicitly authorized; push and merge remain separate decisions.
