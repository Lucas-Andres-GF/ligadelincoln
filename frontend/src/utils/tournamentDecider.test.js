import assert from 'node:assert/strict'
import test from 'node:test'

import { buildTournamentDeciderSeries } from './tournamentDecider.js'

const clubs = {
  pintense: { nombre: 'CA. Pintense' },
  arenaza: { nombre: 'Dep. Arenaza' },
}

function createLeg(overrides = {}) {
  return {
    id: 101,
    torneo_id: 2,
    categoria_id: 1,
    local_id: 10,
    visitante_id: 20,
    campeon_id: 20,
    serie: 'Final por desempate',
    instancia: 'ida',
    orden: 1,
    goles_local: 0,
    goles_visitante: 1,
    dia: '2026-09-06',
    cancha: 'CA. Pintense',
    fuente_url: 'https://liga.example/final-oficial.html',
    local: clubs.pintense,
    visitante: clubs.arenaza,
    campeon: clubs.arenaza,
    ...overrides,
  }
}

function createReturnLeg(overrides = {}) {
  return createLeg({
    id: 102,
    local_id: 20,
    visitante_id: 10,
    instancia: 'vuelta',
    orden: 2,
    goles_local: 2,
    goles_visitante: 0,
    dia: '2026-09-12',
    cancha: 'Dep. Arenaza',
    local: clubs.arenaza,
    visitante: clubs.pintense,
    ...overrides,
  })
}

test('builds a two-leg series and computes each club aggregate', () => {
  const [series] = buildTournamentDeciderSeries([
    createReturnLeg(),
    createLeg(),
  ])

  assert.deepEqual(series.legs.map((leg) => leg.id), [101, 102])
  assert.deepEqual(
    series.clubs.map(({ id, goals }) => ({ id, goals })),
    [
      { id: 10, goals: 0 },
      { id: 20, goals: 3 },
    ],
  )
  assert.deepEqual(series.champion, { id: 20, name: 'Dep. Arenaza' })
})

test('credits aggregate goals by club when home and away teams reverse', () => {
  const [series] = buildTournamentDeciderSeries([
    createLeg({ goles_local: 2, goles_visitante: 1 }),
    createReturnLeg({ goles_local: 3, goles_visitante: 0 }),
  ])

  assert.equal(series.clubs.find((club) => club.id === 10).goals, 2)
  assert.equal(series.clubs.find((club) => club.id === 20).goals, 4)
})

test('sorts series and legs deterministically regardless of input order', () => {
  const rows = [
    createReturnLeg({ id: 202, serie: 'Serie B' }),
    createLeg({ id: 201, serie: 'Serie B' }),
    createReturnLeg({ id: 302, serie: 'Serie A' }),
    createLeg({ id: 301, serie: 'Serie A' }),
  ]

  const series = buildTournamentDeciderSeries(rows)

  assert.deepEqual(series.map((item) => item.name), ['Serie A', 'Serie B'])
  assert.deepEqual(series.map((item) => item.legs.map((leg) => leg.orden)), [[1, 2], [1, 2]])
})

test('omits malformed and internally inconsistent series', () => {
  const rows = [
    createLeg({ serie: 'Válida' }),
    createReturnLeg({ serie: 'Válida' }),
    createLeg({ serie: 'Marcador inválido', goles_local: -1 }),
    createReturnLeg({ serie: 'Marcador inválido' }),
    createLeg({ serie: 'Marcador ausente', goles_local: null }),
    createReturnLeg({ serie: 'Marcador ausente' }),
    createLeg({ serie: 'Fuente inconsistente' }),
    createReturnLeg({ serie: 'Fuente inconsistente', fuente_url: 'https://otra.example/final.html' }),
    createLeg({ serie: 'Campeón inconsistente' }),
    createReturnLeg({ serie: 'Campeón inconsistente', campeon_id: 10, campeon: clubs.pintense }),
    createLeg({ serie: 'Clubes no distintos', visitante_id: 10, visitante: clubs.pintense }),
    createReturnLeg({ serie: 'Clubes no distintos' }),
  ]

  assert.deepEqual(buildTournamentDeciderSeries(rows).map((series) => series.name), ['Válida'])
})

test('rejects two-leg series without ordered ida/vuelta home reversal', () => {
  const invalidReturn = createReturnLeg({
    local_id: 10,
    visitante_id: 20,
    local: clubs.pintense,
    visitante: clubs.arenaza,
  })

  assert.deepEqual(buildTournamentDeciderSeries([createLeg(), invalidReturn]), [])
})

test('returns no series for empty or non-array input', () => {
  assert.deepEqual(buildTournamentDeciderSeries([]), [])
  assert.deepEqual(buildTournamentDeciderSeries(null), [])
})

test('omits a series when the declared champion does not win the aggregate', () => {
  const rows = [
    createLeg({ campeon_id: 10, campeon: clubs.pintense }),
    createReturnLeg({ campeon_id: 10, campeon: clubs.pintense }),
  ]

  assert.deepEqual(buildTournamentDeciderSeries(rows), [])
})
