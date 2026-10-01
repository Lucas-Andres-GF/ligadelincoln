import { useEffect, useMemo, useRef, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { cachedQuery } from '../utils/supabaseCached'
import { slugify } from '../utils/slugify'
import { isMatchPlayed } from '../utils/matchState'
import { isMatchLive } from '../utils/matchTiming'
import { buildLineupScorerLabels } from '../utils/lineupScorers'
import { useMatchClock } from '../hooks/useMatchClock'
import LiveMatchBadge from './LiveMatchBadge'
import {
  getSelectedTorneoId,
  listenToTorneoChange,
  parseTorneoId,
  withTorneoParam,
} from '../utils/torneoSelection'

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY
const supabase = createClient(supabaseUrl, supabaseKey)

function getEscudoPath(nombre) {
  if (!nombre) return '/escudos/argentino.png'
  const mapa = {
    argentino: '/escudos/argentino.png',
    'atl. pasteur': '/escudos/atl.pasteur.png',
    'atl. roberts': '/escudos/atl.roberts.png',
    'ca. pintense': '/escudos/ca.pintense.png',
    'c a pintense': '/escudos/ca.pintense.png',
    'ca pintense': '/escudos/ca.pintense.png',
    pintense: '/escudos/ca.pintense.png',
    caset: '/escudos/caset.png',
    'dep. arenaza': '/escudos/dep.arenaza.png',
    'dep. gral pinto': '/escudos/dep.pinto.png',
    'dep gral pinto': '/escudos/dep.pinto.png',
    'el linqueño': '/escudos/el.linqueño.png',
    'juventad-unida': '/escudos/juventud.unida.png',
    juventadunida: '/escudos/juventud.unida.png',
    'juventud-unida': '/escudos/juventud.unida.png',
    juventudunida: '/escudos/juventud.unida.png',
    'san martin': '/escudos/san.martin.png',
    'villa francia': '/escudos/villa.francia.png',
    cael: '/escudos/el.linqueño.png',
  }
  const keyConEspacios = nombre.toLowerCase().trim()
  const keySinEspacios = nombre.toLowerCase().replace(' ', '').trim()
  return mapa[keyConEspacios] || mapa[keySinEspacios] || '/escudos/argentino.png'
}

function parseDate(dia) {
  if (!dia) return null
  const anio = new Date().getFullYear()
  if (dia.includes('/')) {
    const parts = dia.split('/')
    if (parts.length === 3) {
      const [dd, mm, aa] = parts
      return new Date(aa.length === 4 ? Number(aa) : Number(`20${aa}`), Number(mm) - 1, Number(dd))
    }
    const [dd, mm] = parts.map(Number)
    return dd > 12
      ? new Date(anio, mm - 1, dd)
      : new Date(anio, dd - 1, mm)
  }
  if (dia.includes('-')) {
    const [aa, mm, dd] = dia.split('-')
    return new Date(aa.length === 4 ? Number(aa) : Number(`20${aa}`), Number(mm) - 1, Number(dd))
  }
  return null
}

function detectarFechaActual(grouped, fechas) {
  if (fechas.length === 0) return null

  const hoy = new Date()
  hoy.setHours(0, 0, 0, 0)
  let proxima = null
  let diferenciaProxima = Infinity
  let ultima = null
  let diferenciaUltima = -Infinity

  for (const fechaId of fechas) {
    const fechaPartido = parseDate(grouped[fechaId]?.[0]?.dia)
    if (!fechaPartido) continue
    const diferencia = fechaPartido.getTime() - hoy.getTime()
    if (diferencia >= 0 && diferencia < diferenciaProxima) {
      diferenciaProxima = diferencia
      proxima = fechaId
    } else if (diferencia < 0 && diferencia > diferenciaUltima) {
      diferenciaUltima = diferencia
      ultima = fechaId
    }
  }

  return proxima ?? ultima ?? fechas[0]
}

function formatearFechaMostrar(dia) {
  if (!dia) return ''
  if (dia.includes('/')) {
    const parts = dia.split('/')
    if (parts.length === 3) {
      const [dd, mm] = parts
      return Number(dd) > 12 ? `${dd}/${mm}` : `${mm}/${dd}`
    }
    return dia
  }
  if (dia.includes('-')) {
    const [, mm, dd] = dia.split('-')
    return `${dd}/${mm}`
  }
  return dia
}

function normalizarCancha(nombre) {
  if (!nombre) return ''
  if (nombre.toLowerCase().trim() === 'cael') return 'ellinqueno'
  return nombre
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\b(cancha|estadio|club|ca|c\.a\.|atl|atletico|dep|deportivo)\b/g, '')
    .replace(/[^a-z0-9]/g, '')
}

function debeMostrarCancha(cancha, localNombre) {
  const canchaNorm = normalizarCancha(cancha)
  const localNorm = normalizarCancha(localNombre)
  return Boolean(
    canchaNorm &&
      localNorm &&
      !canchaNorm.includes(localNorm) &&
      !localNorm.includes(canchaNorm),
  )
}

export default function FixtureCategoria({ categoria, torneoId = null }) {
  const [allMatches, setAllMatches] = useState({})
  const [availableFechas, setAvailableFechas] = useState([])
  const [fechaActual, setFechaActual] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [selectedTorneoId, setSelectedTorneoId] = useState(() =>
    getSelectedTorneoId(torneoId),
  )
  const now = useMatchClock()
  const liveMatchesRef = useRef(false)

  useEffect(() => listenToTorneoChange(setSelectedTorneoId), [])

  useEffect(() => {
    let cancelled = false

    async function fetchFixture({ background = false } = {}) {
      if (!background) {
        setAllMatches({})
        setAvailableFechas([])
        setFechaActual(null)
        setDropdownOpen(false)
        setError(null)
      }

      const scopedTorneoId = parseTorneoId(selectedTorneoId)
      if (scopedTorneoId === null) {
        setIsLoading(false)
        return
      }

      if (!background) setIsLoading(true)
      const cacheKey = `fixture_torneo_${scopedTorneoId}_categoria_${categoria}`
      const queryFixture = () =>
        supabase
          .from('partidos')
          .select(`
            id, fecha_id, dia, hora, cancha, goles_local, goles_visitante,
            estado, local_id, visitante_id,
            local:local_id ( nombre ), visitante:visitante_id ( nombre )
          `)
          .eq('categoria_id', categoria)
          .eq('torneo_id', scopedTorneoId)
          .order('fecha_id')
          .order('id')
      const { data, error: partidosError } = background
        ? await queryFixture()
        : await cachedQuery(cacheKey, queryFixture)

      if (cancelled) return
      if (partidosError) {
        console.error('Error fetching partidos:', partidosError)
        if (!background) {
          setError('No se pudo cargar el fixture de este torneo.')
          setIsLoading(false)
        }
        return
      }

      let goleadoresMap = {}
      if (data?.length) {
        const partidoIds = data.map((partido) => partido.id)
        // alineaciones has no torneo_id. This bounded read is safe only because
        // every partido ID came from the tournament-scoped partidos query above.
        const { data: aliData, error: alineacionesError } = await supabase
          .from('alineaciones')
          .select('partido_id, equipo_id, nombre, goleo, goles_en_contra')
          .in('partido_id', partidoIds)
          .or('goleo.gt.0,goles_en_contra.gt.0')

        if (cancelled) return
        if (alineacionesError) {
          console.error('Error fetching alineaciones:', alineacionesError)
          setError('Se cargó el fixture, pero no se pudieron cargar los goleadores.')
        } else {
          goleadoresMap = buildLineupScorerLabels(data, aliData)
        }
      }

      const grouped = {}
      for (const match of data || []) {
        const withScorers = {
          ...match,
          goleadoresLocal: goleadoresMap[match.id]?.local || [],
          goleadoresVisita: goleadoresMap[match.id]?.visitor || [],
        }
        if (!grouped[match.fecha_id]) grouped[match.fecha_id] = []
        grouped[match.fecha_id].push(withScorers)
      }

      for (const fechaId of Object.keys(grouped)) {
        grouped[fechaId].sort((a, b) => {
          if (a.visitante_id === null && b.visitante_id !== null) return 1
          if (b.visitante_id === null && a.visitante_id !== null) return -1
          const fechaA = parseDate(a.dia)
          const fechaB = parseDate(b.dia)
          if (fechaA && fechaB && fechaA.getTime() !== fechaB.getTime()) return fechaA - fechaB
          if (fechaA && !fechaB) return -1
          if (!fechaA && fechaB) return 1
          return (a.hora || '').localeCompare(b.hora || '')
        })
      }

      const fechas = Object.keys(grouped).sort((a, b) => Number(a) - Number(b))
      setAllMatches(grouped)
      setAvailableFechas(fechas)
      setFechaActual((current) => (
        current !== null && fechas.includes(String(current))
          ? current
          : detectarFechaActual(grouped, fechas)
      ))
      if (!background) setIsLoading(false)
    }

    fetchFixture()
    const refreshInterval = window.setInterval(() => {
      if (document.visibilityState === 'visible' && liveMatchesRef.current) {
        fetchFixture({ background: true })
      }
    }, 60_000)
    return () => {
      cancelled = true
      window.clearInterval(refreshInterval)
    }
  }, [categoria, selectedTorneoId])

  const currentIndex = availableFechas.indexOf(String(fechaActual))
  const matches = useMemo(
    () => (fechaActual === null ? [] : allMatches[fechaActual] || []),
    [allMatches, fechaActual],
  )
  liveMatchesRef.current = matches.some((match) => isMatchLive(match, now))

  if (parseTorneoId(selectedTorneoId) === null) {
    return (
      <div className='text-center py-8 text-yellow-200 text-xs uppercase tracking-widest' role='status'>
        Seleccioná un torneo válido para ver el fixture.
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className='p-4'>
        <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>Cargando fixture…</div>
      </div>
    )
  }

  if (error && availableFechas.length === 0) {
    return (
      <div className='p-4'>
        <div className='text-center py-8 text-red-300 text-xs font-semibold' role='alert'>{error}</div>
      </div>
    )
  }

  if (availableFechas.length === 0) {
    return (
      <div className='p-4'>
        <div className='text-center py-8 text-green-700 text-xs uppercase tracking-widest'>No hay partidos cargados para este torneo.</div>
      </div>
    )
  }

  return (
    <div className='p-3 sm:p-4'>
      {error && <div className='mb-3 text-center text-red-300 text-xs font-semibold' role='alert'>{error}</div>}
      <div className='mb-3 flex items-center justify-between rounded-xl border border-green-800/50 bg-green-950/25 p-1.5'>
        <button
          type='button'
          onClick={() => setFechaActual(availableFechas[currentIndex - 1])}
          disabled={currentIndex <= 0}
          aria-label='Ir a la fecha anterior'
          className='grid h-8 w-8 place-items-center rounded-lg text-lg text-green-400 transition hover:bg-green-400 hover:text-[#082310] disabled:cursor-not-allowed disabled:opacity-25'
        >‹</button>
        <div className='relative'>
          <button
            type='button'
            onClick={() => setDropdownOpen((open) => !open)}
            aria-expanded={dropdownOpen}
            aria-controls={`fixture-fechas-${categoria}`}
            aria-label={`Seleccionar fecha. Fecha actual ${fechaActual}`}
            className='flex cursor-pointer items-center gap-2 rounded-lg px-3 py-1.5 font-[var(--font-display)] text-sm font-black uppercase tracking-[0.12em] text-green-100 transition hover:bg-green-400/10'
          >
            <span className='text-green-600'>Jornada</span> {fechaActual}
            <svg className={`w-3 h-3 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} fill='none' viewBox='0 0 24 24' stroke='currentColor' aria-hidden='true'>
              <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={3} d='M19 9l-7 7-7-7' />
            </svg>
          </button>
          {dropdownOpen && (
            <>
              <button type='button' className='fixed inset-0 z-[99] cursor-default' onClick={() => setDropdownOpen(false)} aria-label='Cerrar selector de fecha' />
              <div id={`fixture-fechas-${categoria}`} className='absolute left-1/2 top-full z-[100] mt-2 max-h-60 min-w-[110px] -translate-x-1/2 overflow-y-auto rounded-xl border border-green-700/60 bg-[#092716] p-1 shadow-2xl'>
                {availableFechas.map((fechaId) => (
                  <button
                    type='button'
                    key={fechaId}
                    onClick={() => {
                      setFechaActual(fechaId)
                      setDropdownOpen(false)
                    }}
                    className={`block w-full rounded-lg px-3 py-1.5 text-center font-[var(--font-display)] text-xs font-bold uppercase tracking-wide whitespace-nowrap transition-colors ${String(fechaId) === String(fechaActual) ? 'bg-green-400 text-[#082310]' : 'text-green-300 hover:bg-green-900/50'}`}
                  >Jornada {fechaId}</button>
                ))}
              </div>
            </>
          )}
        </div>
        <button
          type='button'
          onClick={() => setFechaActual(availableFechas[currentIndex + 1])}
          disabled={currentIndex < 0 || currentIndex >= availableFechas.length - 1}
          aria-label='Ir a la fecha siguiente'
          className='grid h-8 w-8 place-items-center rounded-lg text-lg text-green-400 transition hover:bg-green-400 hover:text-[#082310] disabled:cursor-not-allowed disabled:opacity-25'
        >›</button>
      </div>

      {matches.length === 0 ? (
        <div className='text-center py-8 text-green-700 text-xs uppercase tracking-widest'>No hay partidos en esta fecha.</div>
      ) : (
        <div className='overflow-hidden rounded-xl border border-green-800/60 bg-green-950/20 divide-y divide-green-800/50'>
          {matches.map((match) => {
            const isLibre = match.visitante_id === null
            const seJugo = isMatchPlayed(match)
            const enJuego = isMatchLive(match, now)
            const estadoNormalizado = String(match.estado || '').trim().toLowerCase()
            const esSuspendido = estadoNormalizado === 'suspendido'
            const tieneObservacion = Boolean(match.estado && !['programado', 'jugado', 'libre'].includes(estadoNormalizado))
            const mostrarCancha = debeMostrarCancha(match.cancha, match.local?.nombre)
            const linkPartido = seJugo && Number(categoria) === 1 && !isLibre
            const matchUrl = linkPartido
              ? withTorneoParam(`/partido/t${selectedTorneoId}-p${match.id}-${slugify(match.local?.nombre || '')}-vs-${slugify(match.visitante?.nombre || '')}`, selectedTorneoId)
              : null

            if (isLibre) {
              return (
                <div key={match.id} className='flex items-center justify-center gap-2 bg-green-950/20 px-3 py-3 text-xs'>
                  <span className='text-green-100 font-medium text-xs sm:text-sm'>{match.local?.nombre}</span>
                  {match.local?.nombre && <img src={getEscudoPath(match.local.nombre)} alt={match.local.nombre} className='w-4 h-4 sm:w-5 sm:h-5 object-contain shrink-0' />}
                  <span className='text-green-700 font-semibold text-xs sm:text-sm'>LIBRE</span>
                </div>
              )
            }

            const Row = linkPartido ? 'a' : 'div'
            return (
              <Row
                key={match.id}
                {...(matchUrl ? { href: matchUrl, 'aria-label': `Ver detalle de ${match.local?.nombre} contra ${match.visitante?.nombre}` } : {})}
                className={`group flex flex-col gap-0 bg-transparent px-3 py-2.5 text-xs transition-colors hover:bg-green-400/[0.055] ${linkPartido ? 'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-yellow-300' : ''}`}
              >
                <div className='mb-1.5 font-[var(--font-display)] text-[10px] font-bold uppercase tracking-[0.1em] text-green-600 sm:text-xs'>
                  {seJugo ? (
                    formatearFechaMostrar(match.dia) ? <span>{formatearFechaMostrar(match.dia)} <span className='text-green-400 font-semibold'>JUGADO</span></span> : <span className='text-green-400 font-semibold'>JUGADO</span>
                  ) : esSuspendido ? (
                    <span className='text-red-400 font-bold uppercase tracking-wide'>SUSPENDIDO</span>
                  ) : tieneObservacion ? (
                    <span className='text-yellow-400 font-bold uppercase tracking-wide'>{match.estado}</span>
                  ) : enJuego ? (
                    <LiveMatchBadge />
                  ) : match.hora ? (
                    <span>{formatearFechaMostrar(match.dia) || 'A DEFINIR'} - {match.hora.slice(0, 5)}hs</span>
                  ) : (
                    formatearFechaMostrar(match.dia) || <span className='font-semibold'>A DEFINIR</span>
                  )}
                </div>
                <div className='flex items-center gap-2'>
                  <div className='flex-1 flex items-center gap-1 justify-end min-w-0'>
                    <span className='text-right text-xs font-extrabold text-green-50 sm:text-sm'>{match.local?.nombre}</span>
                    {match.local?.nombre && <img src={getEscudoPath(match.local.nombre)} alt={match.local.nombre} className='h-6 w-6 shrink-0 object-contain' />}
                  </div>
                  <div className='flex min-w-[46px] shrink-0 items-center justify-center rounded-md bg-black/15 px-1.5 py-1'>
                    {seJugo ? <><span className='text-base font-black tabular-nums text-white sm:text-lg'>{match.goles_local}</span><span className='mx-1 text-green-700'>–</span><span className='text-base font-black tabular-nums text-white sm:text-lg'>{match.goles_visitante}</span></> : <span className='font-[var(--font-display)] text-xs font-bold uppercase text-green-600'>vs</span>}
                  </div>
                  <div className='flex-1 flex items-center gap-1 min-w-0'>
                    {match.visitante?.nombre && <img src={getEscudoPath(match.visitante.nombre)} alt={match.visitante.nombre} className='h-6 w-6 shrink-0 object-contain' />}
                    <span className='text-xs font-extrabold text-green-50 sm:text-sm'>{match.visitante?.nombre}</span>
                  </div>
                </div>
                {mostrarCancha && <div className='mt-1 inline-flex w-fit max-w-full items-center gap-1 rounded-full border border-yellow-300/30 bg-yellow-300/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-yellow-200 sm:text-[10px]'><span className='text-yellow-400'>Cancha</span><span className='truncate'>{match.cancha}</span></div>}
                {seJugo && (match.goleadoresLocal.length > 0 || match.goleadoresVisita.length > 0) && (
                  <div className='flex mt-1 gap-2'>
                    <div className='flex-1 text-right text-[9px] sm:text-[10px] text-green-500/80 space-y-0.5 pr-3'>{match.goleadoresLocal.map((goleador, index) => <div key={`l${index}`} className='truncate'>{goleador}</div>)}</div>
                    <div className='flex-1 text-left text-[9px] sm:text-[10px] text-green-500/80 space-y-0.5 pl-3'>{match.goleadoresVisita.map((goleador, index) => <div key={`v${index}`} className='truncate'>{goleador}</div>)}</div>
                  </div>
                )}
              </Row>
            )
          })}
        </div>
      )}
    </div>
  )
}
