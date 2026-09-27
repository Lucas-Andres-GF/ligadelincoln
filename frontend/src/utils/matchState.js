function normalizeState(state) {
  return String(state || '').trim().toLowerCase()
}

function parseScore(value) {
  if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) {
    return { kind: 'missing', value: null }
  }

  const score = Number(value)
  if (!Number.isSafeInteger(score) || score < 0) {
    return { kind: 'invalid', value: null }
  }

  return { kind: 'valid', value: score }
}

export function hasCompleteScore(match) {
  return parseScore(match?.goles_local).kind === 'valid'
    && parseScore(match?.goles_visitante).kind === 'valid'
}

export function isMatchPlayed(match) {
  const state = normalizeState(match?.estado)
  if (state === 'suspendido') return false
  return state === 'jugado' || hasCompleteScore(match)
}

export function buildMatchStateUpdate(match) {
  const state = normalizeState(match?.estado)
  if (state === 'suspendido') {
    return {
      estado: 'suspendido',
      goles_local: null,
      goles_visitante: null,
      hora: null,
    }
  }

  const localScore = parseScore(match?.goles_local)
  const visitorScore = parseScore(match?.goles_visitante)
  if (localScore.kind === 'invalid' || visitorScore.kind === 'invalid') {
    throw new TypeError('Scores must be valid non-negative integers.')
  }

  const hasLocalScore = localScore.kind === 'valid'
  const hasVisitorScore = visitorScore.kind === 'valid'
  if (hasLocalScore !== hasVisitorScore) {
    throw new TypeError('Both scores are required to save a result.')
  }

  return {
    estado: hasLocalScore ? 'jugado' : match?.estado,
    goles_local: localScore.value,
    goles_visitante: visitorScore.value,
    hora: match?.hora === '' || match?.hora === null || match?.hora === undefined
      ? null
      : match.hora,
  }
}
