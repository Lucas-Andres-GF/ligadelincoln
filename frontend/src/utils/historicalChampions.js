function normalizeIdentity(value) {
  if (Number.isSafeInteger(value) && value > 0) return String(value)
  if (typeof value !== 'string' || !/^[1-9]\d*$/.test(value)) return null

  const parsed = Number(value)
  return Number.isSafeInteger(parsed) ? String(parsed) : null
}

function normalizeText(value) {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized || null
}

function getClubName(relation) {
  const candidates = (Array.isArray(relation) ? relation : [relation])
    .map((club) => normalizeText(club?.nombre))
    .filter(Boolean)
    .sort(compareText)

  return candidates[0] || null
}

function compareText(left, right) {
  if (left < right) return -1
  if (left > right) return 1
  return 0
}

function compareIdentities(left, right) {
  return Number(left) - Number(right)
}

function resolveMetadata(values) {
  const sortedValues = [...values].sort(compareText)
  return {
    value: sortedValues.length === 1 ? sortedValues[0] : null,
    conflict: sortedValues.length > 1,
  }
}

/**
 * Groups valid palmares rows by tournament and category while preserving each
 * distinct official club. Returned groups and champions have stable ID order.
 */
export function groupHistoricalChampions(rows) {
  const pendingGroups = new Map()

  for (const row of Array.isArray(rows) ? rows : []) {
    const tournamentId = normalizeIdentity(row?.torneo_id)
    const categoryId = normalizeIdentity(row?.categoria_id)
    const clubId = normalizeIdentity(row?.club_id)
    const clubName = getClubName(row?.club)

    if (!tournamentId || !categoryId || !clubId || !clubName) continue

    const key = `${tournamentId}:${categoryId}`
    let group = pendingGroups.get(key)
    if (!group) {
      group = {
        tournamentId,
        categoryId,
        seasons: new Set(),
        titles: new Set(),
        clubs: new Map(),
      }
      pendingGroups.set(key, group)
    }

    const season = normalizeText(row.temporada)
    const title = normalizeText(row.nombre)
    if (season) group.seasons.add(season)
    if (title) group.titles.add(title)

    const names = group.clubs.get(clubId) || new Set()
    names.add(clubName)
    group.clubs.set(clubId, names)
  }

  const orderedGroups = [...pendingGroups.values()].sort((left, right) => (
    compareIdentities(left.tournamentId, right.tournamentId)
    || compareIdentities(left.categoryId, right.categoryId)
  ))

  const result = new Map()
  for (const group of orderedGroups) {
    const season = resolveMetadata(group.seasons)
    const title = resolveMetadata(group.titles)
    const champions = [...group.clubs.entries()]
      .sort(([leftId], [rightId]) => compareIdentities(leftId, rightId))
      .map(([clubId, names]) => ({
        clubId,
        clubName: [...names].sort(compareText)[0],
      }))

    result.set(`${group.tournamentId}:${group.categoryId}`, {
      tournamentId: group.tournamentId,
      categoryId: group.categoryId,
      season: season.value,
      title: title.value,
      metadataConflicts: {
        season: season.conflict,
        title: title.conflict,
      },
      champions,
    })
  }

  return result
}
