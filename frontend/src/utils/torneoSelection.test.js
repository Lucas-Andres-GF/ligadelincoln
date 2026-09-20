import test from 'node:test'
import assert from 'node:assert/strict'
import {
  canScopeTorneoHref,
  getSelectedTorneoId,
  parseTorneoId,
  withTorneoParam,
} from './torneoSelection.js'

const originalWindow = globalThis.window

test.afterEach(() => {
  if (originalWindow === undefined) {
    delete globalThis.window
  } else {
    globalThis.window = originalWindow
  }
})

test('parseTorneoId accepts only canonical positive safe decimal IDs', () => {
  assert.equal(parseTorneoId('1'), 1)
  assert.equal(parseTorneoId('2048'), 2048)
  assert.equal(parseTorneoId(2), 2)

  for (const value of [
    '0',
    '02',
    '2abc',
    ' 2',
    '2 ',
    '+2',
    '-2',
    '2.0',
    '2.5',
    '',
    null,
    undefined,
    String(Number.MAX_SAFE_INTEGER + 1),
  ]) {
    assert.equal(parseTorneoId(value), null, `expected ${String(value)} to be rejected`)
  }
})

test('getSelectedTorneoId uses a strict fallback only when the URL parameter is missing', () => {
  globalThis.window = {
    location: {
      search: '?categoria=1',
      href: 'https://ligadelincoln.com/primera?categoria=1',
    },
  }

  assert.equal(getSelectedTorneoId('7'), 7)
  assert.equal(getSelectedTorneoId('7abc'), null)
})

test('getSelectedTorneoId never falls back when torneo is present but invalid', () => {
  globalThis.window = {
    location: {
      search: '?torneo=2abc',
      href: 'https://ligadelincoln.com/primera?torneo=2abc',
    },
  }

  assert.equal(getSelectedTorneoId('7'), null)
})

test('withTorneoParam adds or replaces one tournament query while preserving other query and hash state', () => {
  const base = 'https://ligadelincoln.com/primera?torneo=2'

  assert.equal(
    withTorneoParam('/club/argentino?categoria=1#fixture', 9, base),
    '/club/argentino?categoria=1&torneo=9#fixture',
  )
  assert.equal(
    withTorneoParam('/clubes?torneo=2&vista=tabla', '9', base),
    '/clubes?torneo=9&vista=tabla',
  )
})

test('withTorneoParam leaves external, hash-only, protocol, and excluded links untouched', () => {
  const base = 'https://ligadelincoln.com/primera'
  const excluded = [
    'https://example.com/fixture',
    '#tabla',
    'mailto:club@example.com',
    'tel:+541234',
    '/',
    '/admin',
    '/admin/partidos?categoria=1',
    '/login',
    '/primera',
    '/septima',
    '/octava',
    '/novena',
    '/decima',
  ]

  for (const href of excluded) {
    assert.equal(withTorneoParam(href, 3, base), href)
  }
  assert.equal(withTorneoParam('/club/argentino', ' 3', base), '/club/argentino')
})

test('canScopeTorneoHref excludes download and non-self target navigation', () => {
  const baseHref = 'https://ligadelincoln.com/primera'

  assert.equal(canScopeTorneoHref('/club/argentino', { baseHref }), true)
  assert.equal(canScopeTorneoHref('/club/argentino', { baseHref, download: true }), false)
  assert.equal(canScopeTorneoHref('/club/argentino', { baseHref, target: '_blank' }), false)
  assert.equal(canScopeTorneoHref('/club/argentino', { baseHref, target: '_self' }), true)
})

test('canScopeTorneoHref excludes category navigation paths so they always load active tournament', () => {
  const baseHref = 'https://ligadelincoln.com/septima?torneo=2'

  assert.equal(canScopeTorneoHref('/primera', { baseHref }), false)
  assert.equal(canScopeTorneoHref('/septima', { baseHref }), false)
  assert.equal(canScopeTorneoHref('/octava', { baseHref }), false)
  assert.equal(canScopeTorneoHref('/novena', { baseHref }), false)
  assert.equal(canScopeTorneoHref('/decima', { baseHref }), false)
})

test('canScopeTorneoHref excludes home/logo path so it returns to the active tournament', () => {
  const baseHref = 'https://ligadelincoln.com/octava?torneo=2#fixture'

  assert.equal(canScopeTorneoHref('/', { baseHref }), false)
  assert.equal(withTorneoParam('/', 2, baseHref), '/')
})
