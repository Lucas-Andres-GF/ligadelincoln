# Supabase ACL Hardening

## Goal
Align production ACLs and future default privileges with the existing public-read/admin-write RLS model without breaking frontend reads, authenticated admin writes, or service-role automation.

## Tasks
- [x] SEC-ACL-001 Version an idempotent ACL hardening migration and update the canonical RLS script.
  - Anonymous: table `SELECT` only; no sequence or function execution privileges.
  - Authenticated: table `SELECT/INSERT/UPDATE/DELETE`; sequence `USAGE` only; execute only `is_liga_admin()`.
  - Service role and owners retain required access.
  - Remove broad default grants for future public tables, sequences, and functions for `postgres`; attempt `supabase_admin` defaults only under verified membership and surface residual drift otherwise.
  - Evidence: migration, canonical SQL, emergency rollback, runbook, and 6 static contract tests added; 221 backend tests pass.
  - Commit: `192269a` (`fix(db): harden Supabase ACL boundaries`).
- [x] SEC-ACL-002 Review the migration against current frontend/admin/backend access paths and add rollback guidance.
  - Evidence: independent verification confirmed exact current-object ACLs and compatibility, but issued NO-GO for claiming complete hardening because SQL Editor `postgres` is not a `supabase_admin` member; residual platform-owned default ACL drift remains unless separately authorized.
  - Commit: `192269a` (`fix(db): harden Supabase ACL boundaries`).
- [x] SEC-ACL-003 Apply the reviewed migration to production in one transaction.
  - Evidence: user executed `rls_acl_hardening_v2.sql` in Supabase SQL Editor successfully; no rows returned.
  - Commit: `192269a` (`fix(db): harden Supabase ACL boundaries`).
- [x] SEC-ACL-004 Verify effective ACLs, RLS policies, public reads, admin compatibility assumptions, service-role automation, and Supabase security advisors.
  - Readback: anon has table SELECT only and no sequence access; authenticated has table SELECT/INSERT/UPDATE/DELETE and sequence USAGE only; service_role grants remain; all 13 tables retain RLS and four policies; `is_liga_admin()` is invoker-safe with anon execute denied.
  - Smoke evidence: public REST reads returned HTTP 200 for `torneos`, `partidos`, `posiciones`, and `alineaciones`; Mint service-role Primera dry-run returned 5 matched fixtures, zero updates, and zero blockers.
  - Expected residual: `supabase_admin` default ACLs remain broad because SQL Editor `postgres` lacks role membership.
  - Advisor: Auth Leaked Password Protection remains disabled because the project is not on Supabase Pro; the user explicitly accepted this plan limitation and no Auth change was attempted.
  - Commit: `192269a` (`fix(db): harden Supabase ACL boundaries`).

## Constraints
- Project: `orrimhgwimzbgzicnlcc`.
- Existing RLS policies remain public-read/admin-write.
- Public frontend reads must continue to work.
- Authenticated admin inserts that rely on generated IDs require sequence `USAGE`.
- Service-role scrapers must remain unaffected.
- No data mutation is included; only privilege/default-privilege/function ACL DDL.
- Leaked Password Protection is a separate Auth dashboard/Management API setting and is not silently changed by SQL.
- Commit and branch push were explicitly authorized after verification; deploy/merge remain separate decisions.

## Baseline Evidence
- All 13 public application tables have RLS enabled and exactly four expected policies.
- `is_liga_admin()` is security-invoker with `search_path=''`.
- `anon` has unexpected table `MAINTAIN/REFERENCES/TRIGGER/TRUNCATE` on all 13 tables and sequence `UPDATE` on all 13 sequences.
- `authenticated` has unexpected table `MAINTAIN/REFERENCES/TRIGGER/TRUNCATE` and sequence `SELECT/UPDATE/USAGE` on all 13 sequences.
- Default ACLs for both `postgres` and `supabase_admin` recreate broad grants.
- Security advisor warning: Leaked Password Protection Disabled.
