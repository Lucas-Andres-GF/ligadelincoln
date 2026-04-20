# Skill Registry — ligadelincoln

## Project Overview

Sitio web de la Liga de Lincoln (fútbol local amateur). Stack: Astro + React + TypeScript + Tailwind CSS (frontend), Python + BeautifulSoup + Supabase (backend).

## User Skills (from ~/.config/opencode/skills/)

### SDD Skills
| Skill | Purpose | Trigger |
|-------|---------|---------|
| sdd-init | Initialize SDD context | "sdd init", "iniciar sdd" |
| sdd-explore | Explore and investigate ideas | Explore topic investigation |
| sdd-propose | Create change proposal | Create/update proposal |
| sdd-spec | Write specifications | Write specs for change |
| sdd-design | Technical design document | Architecture decisions |
| sdd-tasks | Break down into tasks | Task checklist |
| sdd-apply | Implement tasks | Implement from specs |
| sdd-verify | Validate implementation | Verify against specs |
| sdd-archive | Archive completed change | Archive change |

### Utility Skills
| Skill | Purpose | Trigger |
|-------|---------|---------|
| go-testing | Go testing patterns | Go tests, Bubbletea TUI |
| issue-creation | Issue creation workflow | GitHub issue creation |
| branch-pr | PR creation workflow | Pull request creation |
| judgment-day | Adversarial review | "judgment day", "review adversarial" |
| skill-creator | Create new AI skills | Create new skill |
| skill-registry | Update skill registry | "update skills", "skill registry" |

## Project Conventions

### Architecture Patterns
- **Frontend**: Astro pages + React components (islands architecture)
- **Styling**: Tailwind CSS v4 with @tailwindcss/vite
- **Data**: Supabase (PostgreSQL) via @supabase/supabase-js
- **TypeScript**: Strict mode (extends astro/tsconfigs/strict)

### Testing Capabilities
- **Status**: No test runner installed
- **Recommendation**: Install vitest for frontend unit tests, pytest for backend

### Quality Tools
- TypeScript strict mode enabled
- No linter/formatter configured

### Git Conventions
- Conventional commits (no Co-Authored-By)
- Push after build verification

## Notes

- SDD initialized with **engram** mode (2026-04-19)
- No TDD enabled (no test runner)
- Project supports Astro + React stack for coding skills