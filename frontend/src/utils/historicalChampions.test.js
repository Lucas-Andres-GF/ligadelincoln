import assert from 'node:assert/strict'
import test from 'node:test'

import { groupHistoricalChampions } from './historicalChampions.js'

function champion(overrides = {}) {
  return {
    id: 10,
    torneo_id: 2,
    categoria_id: 5,
    club_id: 1,
    nombre: 'Campeón Clausura 2026',
    temporada: '2026',
    club: { nombre: 'Argentino' },
    ...overrides,
  }
}

function getGroup(rows, key = '2:5') {
  return groupHistoricalChampions(rows).get(key)
}

test('groups one official champion with its season and title metadata', () => {
  assert.deepEqual(getGroup([champion()]), {
    tournamentId: '2',
    categoryId: '5',
    season: '2026',
    title: 'Campeón Clausura 2026',
    metadataConflicts: { season: false, title: false },
    champions: [{ clubId: '1', clubName: 'Argentino' }],
  })
})

test('preserves every distinct official club in a shared championship', () => {
  const group = getGroup([
    champion({ id: 11, club_id: 2, club: [{ nombre: 'Atl. Pasteur' }] }),
    champion(),
  ])

  assert.deepEqual(group.champions, [
    { clubId: '1', clubName: 'Argentino' },
    { clubId: '2', clubName: 'Atl. Pasteur' },
  ])
})

test('deduplicates repeated rows for the same official club', () => {
  const group = getGroup([
    champion({ id: 11 }),
    champion({ id: 10 }),
    champion({ id: 12, club_id: '1', club: [{ nombre: 'Argentino' }] }),
    champion({ id: 13, club_id: '1', club: null }),
  ])

  assert.deepEqual(group.champions, [
    { clubId: '1', clubName: 'Argentino' },
  ])
})

test('ignores malformed rows instead of creating invalid groups or champions', () => {
  const groups = groupHistoricalChampions([
    null,
    champion({ torneo_id: null }),
    champion({ categoria_id: 'invalid' }),
    champion({ club_id: null }),
    champion({ club: null }),
    champion({ club: { nombre: '   ' } }),
    champion({ torneo_id: 3, categoria_id: 1, club_id: 8, club: { nombre: 'El Linqueño' } }),
  ])

  assert.deepEqual([...groups.keys()], ['3:1'])
  assert.deepEqual(groups.get('3:1').champions, [
    { clubId: '8', clubName: 'El Linqueño' },
  ])
  assert.deepEqual(groupHistoricalChampions(null), new Map())
})

test('returns stable group and champion ordering regardless of source row order', () => {
  const rows = [
    champion({ torneo_id: 10, categoria_id: 2, club_id: 12, club: { nombre: 'Club 12' } }),
    champion({ torneo_id: 2, categoria_id: 5, club_id: 2, club: { nombre: 'Atl. Pasteur' } }),
    champion(),
  ]

  assert.deepEqual(
    [...groupHistoricalChampions(rows)],
    [...groupHistoricalChampions([...rows].reverse())],
  )
  assert.deepEqual([...groupHistoricalChampions(rows).keys()], ['2:5', '10:2'])
})

test('flags conflicting season and title metadata without selecting or mixing values', () => {
  const group = getGroup([
    champion({ id: 10, temporada: '2025', nombre: 'Apertura' }),
    champion({ id: 11, club_id: 2, club: { nombre: 'Atl. Pasteur' }, temporada: '2026', nombre: 'Clausura' }),
  ])

  assert.equal(group.season, null)
  assert.equal(group.title, null)
  assert.deepEqual(group.metadataConflicts, { season: true, title: true })
  assert.equal(group.champions.length, 2)
})
