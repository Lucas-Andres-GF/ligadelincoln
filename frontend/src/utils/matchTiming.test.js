import test from 'node:test'
import assert from 'node:assert/strict'
import { getMatchKickoff, isMatchLive } from './matchTiming.js'

const kickoff = Date.parse('2026-09-30T20:30:00-03:00')
const scheduled = {
  dia: '2026-09-30',
  hora: '20:30:00',
  estado: 'programado',
  goles_local: null,
  goles_visitante: null,
}

test('parses match kickoff in the Liga de Lincoln timezone', () => {
  assert.equal(getMatchKickoff(scheduled, kickoff), kickoff)
})

test('a scheduled match becomes live exactly at kickoff', () => {
  assert.equal(isMatchLive(scheduled, kickoff - 1), false)
  assert.equal(isMatchLive(scheduled, kickoff), true)
  assert.equal(isMatchLive(scheduled, kickoff + 60 * 60 * 1000), true)
  assert.equal(isMatchLive(scheduled, kickoff + 4 * 60 * 60 * 1000 + 1), false)
})

test('a score, played state or observation always wins over live state', () => {
  assert.equal(isMatchLive({ ...scheduled, goles_local: 0, goles_visitante: 0 }, kickoff), false)
  assert.equal(isMatchLive({ ...scheduled, estado: 'jugado' }, kickoff), false)
  assert.equal(isMatchLive({ ...scheduled, estado: 'suspendido' }, kickoff), false)
  assert.equal(isMatchLive({ ...scheduled, estado: 'postergado' }, kickoff), false)
})

test('missing or invalid schedule data never becomes live', () => {
  assert.equal(isMatchLive({ ...scheduled, dia: null }, kickoff), false)
  assert.equal(isMatchLive({ ...scheduled, hora: '25:80' }, kickoff), false)
})
