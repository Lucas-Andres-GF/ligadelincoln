import { isMatchPlayed } from './matchState.js'

const ARGENTINA_OFFSET = '-03:00'
const LIVE_WINDOW_MS = 4 * 60 * 60 * 1000

function normalizeMatchDate(value, now) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()

  const isoMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed)
  if (isoMatch) return `${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`

  const localMatch = /^(\d{1,2})\/(\d{1,2})(?:\/(\d{2}|\d{4}))?$/.exec(trimmed)
  if (!localMatch) return null

  const day = Number(localMatch[1])
  const month = Number(localMatch[2])
  const fallbackYear = Number(
    new Intl.DateTimeFormat('en', {
      timeZone: 'America/Argentina/Buenos_Aires',
      year: 'numeric',
    }).format(new Date(now)),
  )
  const parsedYear = localMatch[3]
    ? Number(localMatch[3].length === 2 ? `20${localMatch[3]}` : localMatch[3])
    : fallbackYear

  if (month < 1 || month > 12 || day < 1 || day > 31) return null
  return `${parsedYear}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

export function getMatchKickoff(match, now = Date.now()) {
  const date = normalizeMatchDate(match?.dia, now)
  const timeMatch = /^(\d{2}):(\d{2})(?::\d{2})?$/.exec(String(match?.hora || '').trim())
  if (!date || !timeMatch) return null

  const hour = Number(timeMatch[1])
  const minute = Number(timeMatch[2])
  if (hour > 23 || minute > 59) return null

  const kickoff = Date.parse(`${date}T${timeMatch[1]}:${timeMatch[2]}:00${ARGENTINA_OFFSET}`)
  return Number.isFinite(kickoff) ? kickoff : null
}

export function isMatchLive(match, now = Date.now()) {
  if (!match || isMatchPlayed(match)) return false

  const state = String(match.estado || '').trim().toLowerCase()
  if (state && state !== 'programado') return false

  const kickoff = getMatchKickoff(match, now)
  return kickoff !== null && now >= kickoff && now <= kickoff + LIVE_WINDOW_MS
}
