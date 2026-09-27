import assert from 'node:assert/strict'
import test from 'node:test'

import { buildMatchStateUpdate, isMatchPlayed } from './matchState.js'

test('complete scores make an observation-state match played, including zero', () => {
  assert.equal(
    isMatchPlayed({ estado: 'Juegan 22-9-26', goles_local: 0, goles_visitante: 0 }),
    true,
  )
})

test('canonical played state is played even when scores are not available', () => {
  assert.equal(
    isMatchPlayed({ estado: 'jugado', goles_local: null, goles_visitante: null }),
    true,
  )
})

test('incomplete scores do not make a scheduled match played', () => {
  assert.equal(
    isMatchPlayed({ estado: 'programado', goles_local: 1, goles_visitante: null }),
    false,
  )
})

test('suspended state remains dominant over stale scores', () => {
  assert.equal(
    isMatchPlayed({ estado: 'suspendido', goles_local: 1, goles_visitante: 0 }),
    false,
  )
})

test('saving complete scores canonicalizes any non-suspended prior state', () => {
  assert.deepEqual(
    buildMatchStateUpdate({
      estado: 'Juegan 22-9-26',
      goles_local: '0',
      goles_visitante: '2',
      hora: '16:00',
    }),
    {
      estado: 'jugado',
      goles_local: 0,
      goles_visitante: 2,
      hora: '16:00',
    },
  )
})

test('saving a suspended match clears scores and kickoff time', () => {
  assert.deepEqual(
    buildMatchStateUpdate({
      estado: ' SUSPENDIDO ',
      goles_local: '3',
      goles_visitante: '1',
      hora: '18:30',
    }),
    {
      estado: 'suspendido',
      goles_local: null,
      goles_visitante: null,
      hora: null,
    },
  )
})

test('saving without scores preserves a non-suspended state without inventing goals', () => {
  assert.deepEqual(
    buildMatchStateUpdate({
      estado: 'Juegan 22-9-26',
      goles_local: '',
      goles_visitante: null,
      hora: '',
    }),
    {
      estado: 'Juegan 22-9-26',
      goles_local: null,
      goles_visitante: null,
      hora: null,
    },
  )
})

test('saving an incomplete score is rejected', () => {
  assert.throws(
    () => buildMatchStateUpdate({
      estado: 'programado',
      goles_local: 0,
      goles_visitante: '',
      hora: '15:00',
    }),
    /both scores/i,
  )
})

test('saving an invalid score is rejected', () => {
  assert.throws(
    () => buildMatchStateUpdate({
      estado: 'programado',
      goles_local: '-1',
      goles_visitante: '2',
      hora: '15:00',
    }),
    /valid non-negative integers/i,
  )
})
