function normalizeIdentity(value) {
  if (Number.isSafeInteger(value) && value > 0) return String(value)
  if (typeof value !== 'string' || !/^[1-9]\d*$/.test(value)) return null

  const parsed = Number(value)
  return Number.isSafeInteger(parsed) ? String(parsed) : null
}

function normalizeCount(value) {
  if (Number.isSafeInteger(value) && value > 0) return value
  if (typeof value !== 'string' || !/^[1-9]\d*$/.test(value)) return 0

  const parsed = Number(value)
  return Number.isSafeInteger(parsed) ? parsed : 0
}

function abbreviatePlayerName(name) {
  if (typeof name !== 'string') return null
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return null

  return parts
    .map((part, index) => (index === 0 ? part : `${part.charAt(0)}.`))
    .join(' ')
}

function appendLabels(target, label, count) {
  for (let goal = 0; goal < count; goal += 1) {
    target.push(label)
  }
}

/**
 * Builds scorer labels from lineup rows bounded by tournament-scoped matches.
 * Rows whose match or team identity does not belong to those matches are ignored.
 */
export function buildLineupScorerLabels(matches, lineupRows) {
  const labelsByMatch = {}
  const identitiesByMatch = new Map()

  for (const match of Array.isArray(matches) ? matches : []) {
    const matchId = normalizeIdentity(match?.id)
    const localId = normalizeIdentity(match?.local_id)
    const visitorId = normalizeIdentity(match?.visitante_id)

    if (!matchId || !localId || !visitorId || localId === visitorId) continue

    identitiesByMatch.set(matchId, { localId, visitorId })
    labelsByMatch[matchId] = { local: [], visitor: [] }
  }

  for (const row of Array.isArray(lineupRows) ? lineupRows : []) {
    const matchId = normalizeIdentity(row?.partido_id)
    const teamId = normalizeIdentity(row?.equipo_id)
    const identity = matchId ? identitiesByMatch.get(matchId) : null
    const abbreviatedName = abbreviatePlayerName(row?.nombre)

    if (!identity || !teamId || !abbreviatedName) continue
    if (teamId !== identity.localId && teamId !== identity.visitorId) continue

    const normalGoals = normalizeCount(row?.goleo)
    const ownGoals = normalizeCount(row?.goles_en_contra)
    const ownSide = teamId === identity.localId ? 'visitor' : 'local'
    const normalSide = teamId === identity.localId ? 'local' : 'visitor'

    appendLabels(labelsByMatch[matchId][normalSide], `${abbreviatedName} ⚽`, normalGoals)
    appendLabels(labelsByMatch[matchId][ownSide], `${abbreviatedName} (E/C) ⚽`, ownGoals)
  }

  return labelsByMatch
}
