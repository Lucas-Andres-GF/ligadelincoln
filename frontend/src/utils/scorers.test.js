import test from 'node:test'
import assert from 'node:assert/strict'
import { buildScorersTable } from './scorers.js'

test('aggregates one player goals across tournament matches', () => {
  const result = buildScorersTable([
    { equipo_id: 10, nombre: 'Juan Pérez', goleo: 2 },
    { equipo_id: 10, nombre: '  Juan   Perez ', goleo: 1 },
    { equipo_id: 20, nombre: 'Pedro Gómez', goleo: 2 },
  ], { 10: 'Argentino', 20: 'Lincoln' })

  assert.deepEqual(result, [
    { name: 'Juan Pérez', teamId: 10, clubName: 'Argentino', goals: 3 },
    { name: 'Pedro Gómez', teamId: 20, clubName: 'Lincoln', goals: 2 },
  ])
})

test('keeps identical names from different clubs separate', () => {
  const result = buildScorersTable([
    { equipo_id: 10, nombre: 'Juan Pérez', goleo: 1 },
    { equipo_id: 20, nombre: 'Juan Pérez', goleo: 3 },
  ], { 10: 'Argentino', 20: 'Lincoln' })

  assert.equal(result.length, 2)
  assert.equal(result[0].clubName, 'Lincoln')
  assert.equal(result[1].clubName, 'Argentino')
})

test('uses club and player name only as stable tie breakers', () => {
  const result = buildScorersTable([
    { equipo_id: 20, nombre: 'Bruno', goleo: 2 },
    { equipo_id: 10, nombre: 'Carlos', goleo: 2 },
    { equipo_id: 10, nombre: 'Agustín', goleo: 2 },
  ], { 10: 'Argentino', 20: 'Lincoln' })

  assert.deepEqual(result.map((row) => row.name), ['Agustín', 'Carlos', 'Bruno'])
})

test('ignores own goals, zero goals and malformed identities', () => {
  const result = buildScorersTable([
    { equipo_id: 10, nombre: 'Gol válido', goleo: 1, goles_en_contra: 2 },
    { equipo_id: 10, nombre: 'Sin goles', goleo: 0 },
    { equipo_id: null, nombre: 'Sin club', goleo: 4 },
    { equipo_id: 10, nombre: '', goleo: 4 },
  ], { 10: 'Argentino' })

  assert.deepEqual(result, [
    { name: 'Gol válido', teamId: 10, clubName: 'Argentino', goals: 1 },
  ])
})
