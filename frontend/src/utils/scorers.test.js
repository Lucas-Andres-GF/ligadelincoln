import test from 'node:test'
import assert from 'node:assert/strict'
import { sortOfficialScorers } from './scorers.js'

test('sorts official totals by goals, club and player, without aggregating names', () => {
  const rows = [
    { club_id: 8, club: 'El Linqueño', nombre: 'Pérez Juan', goles: 2 },
    { club_id: 1, club: 'Argentino', nombre: 'Pérez Juan', goles: 2 },
    { club_id: 1, club: 'Argentino', nombre: 'Ávalos Santiago', goles: 2 },
    { club_id: 4, club: 'Pintense', nombre: 'Pérez Juan', goles: 7 },
  ]
  assert.deepEqual(sortOfficialScorers(rows), [rows[3], rows[2], rows[1], rows[0]])
})
