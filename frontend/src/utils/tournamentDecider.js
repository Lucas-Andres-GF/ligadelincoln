const VALID_INSTANCES = new Set(['ida', 'vuelta', 'partido_unico'])

function isPositiveInteger(value) {
  return Number.isInteger(Number(value)) && Number(value) > 0
}

function isScore(value) {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
}

function relationName(value) {
  const relation = Array.isArray(value) ? value[0] : value
  return typeof relation?.nombre === 'string' ? relation.nombre.trim() : ''
}

function isValidSourceUrl(value) {
  if (typeof value !== 'string' || value.trim() !== value || !value) return false

  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

function isValidRow(row) {
  if (!row || typeof row !== 'object') return false

  const localId = Number(row.local_id)
  const visitorId = Number(row.visitante_id)
  const championId = Number(row.campeon_id)

  return Boolean(
    isPositiveInteger(row.id) &&
      isPositiveInteger(row.torneo_id) &&
      isPositiveInteger(row.categoria_id) &&
      isPositiveInteger(localId) &&
      isPositiveInteger(visitorId) &&
      isPositiveInteger(championId) &&
      localId !== visitorId &&
      (championId === localId || championId === visitorId) &&
      typeof row.serie === 'string' &&
      row.serie.trim() &&
      VALID_INSTANCES.has(row.instancia) &&
      isPositiveInteger(row.orden) &&
      isScore(row.goles_local) &&
      isScore(row.goles_visitante) &&
      typeof row.dia === 'string' &&
      row.dia.trim() &&
      typeof row.cancha === 'string' &&
      row.cancha.trim() &&
      isValidSourceUrl(row.fuente_url) &&
      relationName(row.local) &&
      relationName(row.visitante) &&
      relationName(row.campeon)
  )
}

function compareText(left, right) {
  const normalizedLeft = left.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  const normalizedRight = right.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

  if (normalizedLeft < normalizedRight) return -1
  if (normalizedLeft > normalizedRight) return 1
  if (left < right) return -1
  if (left > right) return 1
  return 0
}

function buildSeries(name, rows) {
  if (!rows.every(isValidRow)) return null

  const legs = [...rows].sort((left, right) => Number(left.orden) - Number(right.orden))
  const first = legs[0]
  const expectedOrders = legs.length === 1 ? [1] : [1, 2]
  const expectedInstances = legs.length === 1 ? ['partido_unico'] : ['ida', 'vuelta']

  if (
    ![1, 2].includes(legs.length) ||
    legs.some((leg, index) => Number(leg.orden) !== expectedOrders[index]) ||
    legs.some((leg, index) => leg.instancia !== expectedInstances[index])
  ) {
    return null
  }

  const tournamentId = Number(first.torneo_id)
  const categoryId = Number(first.categoria_id)
  const championId = Number(first.campeon_id)
  const sourceUrl = first.fuente_url
  const clubIds = new Set([Number(first.local_id), Number(first.visitante_id)])
  const namesByClub = new Map([
    [Number(first.local_id), relationName(first.local)],
    [Number(first.visitante_id), relationName(first.visitante)],
  ])

  for (const leg of legs) {
    const localId = Number(leg.local_id)
    const visitorId = Number(leg.visitante_id)
    const identitiesAreConsistent =
      Number(leg.torneo_id) === tournamentId &&
      Number(leg.categoria_id) === categoryId &&
      Number(leg.campeon_id) === championId &&
      leg.fuente_url === sourceUrl &&
      clubIds.has(localId) &&
      clubIds.has(visitorId) &&
      namesByClub.get(localId) === relationName(leg.local) &&
      namesByClub.get(visitorId) === relationName(leg.visitante) &&
      namesByClub.get(championId) === relationName(leg.campeon)

    if (!identitiesAreConsistent) return null
  }

  if (
    legs.length === 2 &&
    (
      Number(legs[1].local_id) !== Number(first.visitante_id) ||
      Number(legs[1].visitante_id) !== Number(first.local_id)
    )
  ) {
    return null
  }

  const goalsByClub = new Map([...clubIds].map((clubId) => [clubId, 0]))
  for (const leg of legs) {
    const localId = Number(leg.local_id)
    const visitorId = Number(leg.visitante_id)
    goalsByClub.set(localId, goalsByClub.get(localId) + Number(leg.goles_local))
    goalsByClub.set(visitorId, goalsByClub.get(visitorId) + Number(leg.goles_visitante))
  }

  const clubs = [...clubIds].map((id) => ({
    id,
    name: namesByClub.get(id),
    goals: goalsByClub.get(id),
  }))
  const aggregateWinner = [...clubs].sort((left, right) => right.goals - left.goals)
  if (aggregateWinner[0].goals === aggregateWinner[1].goals || aggregateWinner[0].id !== championId) {
    return null
  }

  return {
    id: `${tournamentId}:${categoryId}:${name}`,
    name,
    tournamentId,
    categoryId,
    legs,
    clubs,
    champion: {
      id: championId,
      name: namesByClub.get(championId),
    },
    sourceUrl,
  }
}

/**
 * Builds validated championship-decider series from database rows.
 * Malformed series are omitted so incomplete or contradictory data is never rendered.
 */
export function buildTournamentDeciderSeries(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return []

  const grouped = new Map()
  for (const row of rows) {
    const name = typeof row?.serie === 'string' ? row.serie.trim() : ''
    if (!grouped.has(name)) grouped.set(name, [])
    grouped.get(name).push(row)
  }

  return [...grouped.entries()]
    .sort(([left], [right]) => compareText(left, right))
    .map(([name, seriesRows]) => buildSeries(name, seriesRows))
    .filter(Boolean)
}
