function normalizePlayerName(value) {
  return String(value || '')
    .trim()
    .replace(/\s+/g, ' ')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('es')
}

function parsePositiveGoals(value) {
  const goals = Number(value)
  return Number.isSafeInteger(goals) && goals > 0 ? goals : 0
}

export function buildScorersTable(lineups, clubsById = {}) {
  if (!Array.isArray(lineups)) return []

  const scorers = new Map()
  for (const row of lineups) {
    const teamId = Number(row?.equipo_id)
    const name = String(row?.nombre || '').trim().replace(/\s+/g, ' ')
    const normalizedName = normalizePlayerName(name)
    const goals = parsePositiveGoals(row?.goleo)
    if (!Number.isSafeInteger(teamId) || teamId <= 0 || !normalizedName || goals === 0) continue

    const key = `${teamId}:${normalizedName}`
    const current = scorers.get(key) || {
      name,
      teamId,
      clubName: clubsById[teamId] || 'Club sin identificar',
      goals: 0,
    }
    current.goals += goals
    scorers.set(key, current)
  }

  return [...scorers.values()].sort((a, b) => (
    b.goals - a.goals
    || a.clubName.localeCompare(b.clubName, 'es', { sensitivity: 'base' })
    || a.name.localeCompare(b.name, 'es', { sensitivity: 'base' })
  ))
}
