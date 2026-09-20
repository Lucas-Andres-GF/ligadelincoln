const CANONICAL_TORNEO_ID = /^[1-9][0-9]*$/

export function parseTorneoId(value) {
  if (typeof value !== 'string' && typeof value !== 'number') return null

  const canonicalValue = String(value)
  if (!CANONICAL_TORNEO_ID.test(canonicalValue)) return null

  const torneoId = Number(canonicalValue)
  return Number.isSafeInteger(torneoId) ? torneoId : null
}

export function getSelectedTorneoId(fallback = null) {
  const fallbackId = parseTorneoId(fallback)
  if (typeof window === 'undefined') return fallbackId

  const params = new URLSearchParams(window.location.search)
  if (!params.has('torneo')) return fallbackId

  return parseTorneoId(params.get('torneo'))
}

export function listenToTorneoChange(callback) {
  if (typeof window === 'undefined') return () => {}

  function handleTorneoChange(event) {
    const hasEventValue = Object.prototype.hasOwnProperty.call(event.detail || {}, 'torneoId')
    const torneoId = hasEventValue
      ? parseTorneoId(event.detail.torneoId)
      : getSelectedTorneoId(null)
    callback(torneoId)
  }

  window.addEventListener('torneo:change', handleTorneoChange)
  return () => window.removeEventListener('torneo:change', handleTorneoChange)
}

const CATEGORY_PATHS = new Set([
  '/primera',
  '/septima',
  '/octava',
  '/novena',
  '/decima',
])

export function isCategoryPath(pathname) {
  if (!pathname) return false
  const normalized =
    pathname.length > 1 && pathname.endsWith('/')
      ? pathname.slice(0, -1)
      : pathname
  return CATEGORY_PATHS.has(normalized)
}

function isExcludedPath(pathname) {
  return (
    pathname === '/' ||
    pathname === '/admin' ||
    pathname.startsWith('/admin/') ||
    pathname === '/login' ||
    pathname.startsWith('/login/') ||
    isCategoryPath(pathname)
  )
}

export function canScopeTorneoHref(
  href,
  { baseHref, download = false, target = '' } = {},
) {
  if (!href || download || (target && target !== '_self')) return false

  const trimmedHref = href.trim()
  if (
    !trimmedHref ||
    trimmedHref.startsWith('#') ||
    /^(mailto:|tel:|javascript:|data:)/i.test(trimmedHref)
  ) {
    return false
  }

  const currentHref =
    baseHref || (typeof window !== 'undefined' ? window.location.href : null)
  if (!currentHref) return false

  try {
    const currentUrl = new URL(currentHref)
    const url = new URL(trimmedHref, currentUrl)
    return (
      url.origin === currentUrl.origin &&
      ['http:', 'https:'].includes(url.protocol) &&
      !isExcludedPath(url.pathname)
    )
  } catch {
    return false
  }
}

export function withTorneoParam(href, torneoId, baseHref) {
  if (!href) return href

  const trimmedHref = href.trim()
  if (
    !trimmedHref ||
    trimmedHref.startsWith('#') ||
    /^(mailto:|tel:|javascript:|data:)/i.test(trimmedHref)
  ) {
    return href
  }

  const selectedTorneoId = parseTorneoId(torneoId)
  if (selectedTorneoId === null) return href

  const currentHref =
    baseHref || (typeof window !== 'undefined' ? window.location.href : null)
  if (!currentHref) return href

  try {
    const currentUrl = new URL(currentHref)
    const url = new URL(trimmedHref, currentUrl)
    if (
      url.origin !== currentUrl.origin ||
      !['http:', 'https:'].includes(url.protocol) ||
      isExcludedPath(url.pathname)
    ) {
      return href
    }

    url.searchParams.set('torneo', String(selectedTorneoId))
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return href
  }
}
