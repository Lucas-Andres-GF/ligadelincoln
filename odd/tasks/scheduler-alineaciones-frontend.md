# Scheduler, Alineaciones and Frontend Reorg

## Goal
Reconfigure the results scheduler (15:00-22:00 ARG, every 5 min, Sat/Sun, systemd, manual weekday override), automate Primera alineaciones polling, then reorganize the frontend.

## Decisions
- Frequency: 5 minutes.
- Mechanism: systemd (keep existing `scraper-resultados.service/.timer`).
- Days: Sat/Sun automatic; weekday exceptions run manually.
- Alineaciones: poll the official page every 5 min for the current fecha; import if published, no-op otherwise.

## Tasks
- [x] SCH-001 Adjust results window to 15:00-22:00 (timer + runner hour guard) and add a manual weekday override.
- [x] SCH-002 Automate alineaciones: determine current fecha, graceful no-op when not published, 5-min systemd timer.
- [ ] SCH-003 Verify scheduler locally and document Mint install steps.
- [ ] FR-001 Reorganize the frontend UI (fix errors, improve button/link organization).

## Constraints
- `torneo_id=2` explicit; no silent fallback.
- Missing scores are never `0-0`.
- Alineaciones "not published" is a no-op, not an error.
- No deploy without explicit authorization.
