import assert from 'node:assert/strict'
import test from 'node:test'

import { buildLineupScorerLabels } from './lineupScorers.js'

const match = {
  id: 101,
  local_id: 10,
  visitante_id: 20,
}

test('keeps normal goals on the scoring player team and abbreviates names', () => {
  const labels = buildLineupScorerLabels(
    [match],
    [{ partido_id: 101, equipo_id: 10, nombre: 'Juan Carlos Perez', goleo: 2 }],
  )

  assert.deepEqual(labels[101], {
    local: ['Juan C. P. ⚽', 'Juan C. P. ⚽'],
    visitor: [],
  })
})

test('credits a local player own goal to the visitor side', () => {
  const labels = buildLineupScorerLabels(
    [match],
    [{ partido_id: 101, equipo_id: 10, nombre: 'Local Defender', goles_en_contra: 1 }],
  )

  assert.deepEqual(labels[101], {
    local: [],
    visitor: ['Local D. (E/C) ⚽'],
  })
})

test('credits a visitor player own goal to the local side', () => {
  const labels = buildLineupScorerLabels(
    [match],
    [{ partido_id: 101, equipo_id: 20, nombre: 'Visitor Defender', goles_en_contra: 2 }],
  )

  assert.deepEqual(labels[101], {
    local: ['Visitor D. (E/C) ⚽', 'Visitor D. (E/C) ⚽'],
    visitor: [],
  })
})

test('splits mixed normal and own-goal counts between the correct sides', () => {
  const labels = buildLineupScorerLabels(
    [match],
    [{
      partido_id: 101,
      equipo_id: 10,
      nombre: 'Mixed Scorer',
      goleo: 2,
      goles_en_contra: 1,
    }],
  )

  assert.deepEqual(labels[101], {
    local: ['Mixed S. ⚽', 'Mixed S. ⚽'],
    visitor: ['Mixed S. (E/C) ⚽'],
  })
})

test('ignores null and zero counts', () => {
  const labels = buildLineupScorerLabels(
    [match],
    [
      { partido_id: 101, equipo_id: 10, nombre: 'No Goals', goleo: null, goles_en_contra: 0 },
      { partido_id: 101, equipo_id: 20, nombre: 'Also None', goleo: 0, goles_en_contra: null },
    ],
  )

  assert.deepEqual(labels[101], { local: [], visitor: [] })
})

test('fails closed for unrelated or malformed match and team identities', () => {
  const labels = buildLineupScorerLabels(
    [match],
    [
      { partido_id: 999, equipo_id: 10, nombre: 'Other Match', goleo: 1 },
      { partido_id: 101, equipo_id: 30, nombre: 'Other Team', goleo: 1 },
      { partido_id: null, equipo_id: 10, nombre: 'Missing Match', goles_en_contra: 1 },
      { partido_id: 101, equipo_id: null, nombre: 'Missing Team', goles_en_contra: 1 },
      { partido_id: 101, equipo_id: 10, nombre: '', goleo: 1 },
      { partido_id: 101, equipo_id: 10, nombre: 'Bad Count', goleo: -1, goles_en_contra: 'invalid' },
    ],
  )

  assert.deepEqual(labels, {
    101: { local: [], visitor: [] },
  })
})
