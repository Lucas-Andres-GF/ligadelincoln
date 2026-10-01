import { useEffect, useRef, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { slugify } from '../utils/slugify'
import { getSelectedTorneoId, listenToTorneoChange, parseTorneoId, withTorneoParam } from '../utils/torneoSelection'
import { isMatchPlayed } from '../utils/matchState'
import { isMatchLive } from '../utils/matchTiming'
import { buildLineupScorerLabels } from '../utils/lineupScorers'
import { useMatchClock } from '../hooks/useMatchClock'
import LiveMatchBadge from './LiveMatchBadge'

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY
const supabase = createClient(supabaseUrl, supabaseKey)

const CATEGORIAS = {
  1: 'PRIMERA',
  2: 'SÉPTIMA',
  3: 'OCTAVA',
  4: 'NOVENA',
  5: 'DÉCIMA',
}

const CATEGORIAS_ROUTES = {
  1: '/primera',
  2: '/septima',
  3: '/octava',
  4: '/novena',
  5: '/decima',
}

function getEscudoPath(nombre) {
  if (!nombre) return '/escudos/argentino.png'
  const mapa = {
    'argentino': '/escudos/argentino.png',
    'atl. pasteur': '/escudos/atl.pasteur.png',
    'atl. roberts': '/escudos/atl.roberts.png',
    'ca. pintense': '/escudos/ca.pintense.png',
    'c a pintense': '/escudos/ca.pintense.png',
    'ca pintense': '/escudos/ca.pintense.png',
    'pintense': '/escudos/ca.pintense.png',
    'caset': '/escudos/caset.png',
    'dep. arenaza': '/escudos/dep.arenaza.png',
    'dep. gral pinto': '/escudos/dep.pinto.png',
    'dep gral pinto': '/escudos/dep.pinto.png',
    'el linqueño': '/escudos/el.linqueño.png',
    'juventad-unida': '/escudos/juventud.unida.png',
    'juventadunida': '/escudos/juventud.unida.png',
    'juventud-unida': '/escudos/juventud.unida.png',
    'juventudunida': '/escudos/juventud.unida.png',
    'san martin': '/escudos/san.martin.png',
    'villa francia': '/escudos/villa.francia.png',
    'cael': '/escudos/el.linqueño.png',
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
      return new Date(aa.length === 4 ? Number(aa) : Number(`20${aa}`), parseInt(mm) - 1, parseInt(dd))
    }
    const [dd, mm] = parts.map(Number)
    if (dd > 12) {
      return new Date(anio, parseInt(mm) - 1, dd)
    }
    return new Date(anio, dd - 1, parseInt(mm))
  }
  if (dia.includes('-')) {
    const parts = dia.split('-')
    const anioFecha = parts[0].includes('20') ? parts[0] : `20${parts[0]}`
    return new Date(parseInt(anioFecha), parseInt(parts[1]) - 1, parseInt(parts[2]))
  }
  return null
}

function formatDateForDisplay(date) {
  const dd = String(date.getDate()).padStart(2, '0')
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  return `${dd}/${mm}`
}

const DIAS_SEMANA = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']

function getDayName(date) {
  return DIAS_SEMANA[date.getDay()]
}

function formatDateForQuery(date) {
  const anio = date.getFullYear()
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  return `${anio}-${mm}-${dd}`
}

function formatDateForQueryES(date) {
  const dd = String(date.getDate()).padStart(2, '0')
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  return `${dd}/${mm}`
}

function normalizarCancha(nombre) {
  if (!nombre) return ''
  const limpio = nombre.toLowerCase().trim()
  if (limpio === 'cael') return 'ellinqueno'

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
  if (!canchaNorm || !localNorm) return false
  return !canchaNorm.includes(localNorm) && !localNorm.includes(canchaNorm)
}

export default function PartidosHoy() {
  const [selectedDate, setSelectedDate] = useState(null)
  const [datesWithMatches, setDatesWithMatches] = useState([])
  const [matches, setMatches] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedTorneoId, setSelectedTorneoId] = useState(() =>
    getSelectedTorneoId(null),
  )
  const now = useMatchClock()
  const liveMatchesRef = useRef(false)
  liveMatchesRef.current = matches.some((match) => isMatchLive(match, now))

  useEffect(() => listenToTorneoChange(setSelectedTorneoId), [])

  useEffect(() => {
    let cancelled = false

    async function fetchDates() {
      setSelectedDate(null)
      setDatesWithMatches([])
      setMatches([])
      setError(null)
      const scopedTorneoId = parseTorneoId(selectedTorneoId)
      if (scopedTorneoId === null) {
        setIsLoading(false)
        return
      }

      setIsLoading(true)
      const { data: allPartidos, error: datesError } = await supabase
        .from('partidos')
        .select('dia')
        .eq('torneo_id', scopedTorneoId)
        .not('dia', 'is', null)

      if (cancelled) return
      if (datesError) {
        console.error('Error fetching match dates:', datesError)
        setError('No se pudieron cargar las fechas de este torneo.')
        setIsLoading(false)
        return
      }

      if (allPartidos && allPartidos.length > 0) {
        // Filter valid dates (not null, not "None" string)
        const validPartidos = allPartidos.filter(p => p.dia && p.dia !== 'None')
        const dates = [...new Set(validPartidos.map(p => p.dia))]
        setDatesWithMatches(dates)
        
        const hoy = new Date()
        hoy.setHours(0, 0, 0, 0)
        
        // PRIORIZAR: 1) próximo (futuro), 2) último (pasado), 3) hoy
        let nextDate = null
        let lastDate = null
        let minFutureDiff = Infinity
        let maxPastDiff = -Infinity
        
        for (const dia of dates) {
          const matchDate = parseDate(dia)
          if (matchDate) {
            const diff = matchDate.getTime() - hoy.getTime()
            if (diff >= 0 && diff < minFutureDiff) {
              minFutureDiff = diff
              nextDate = matchDate
            }
            if (diff < 0 && diff > maxPastDiff) {
              maxPastDiff = diff
              lastDate = matchDate
            }
          }
        }
        
        if (nextDate) {
          setSelectedDate(nextDate)
        } else if (lastDate) {
          setSelectedDate(lastDate)
        } else {
          setSelectedDate(hoy)
        }
      } else {
        setIsLoading(false)
      }
    }
    fetchDates()
    return () => {
      cancelled = true
    }
  }, [selectedTorneoId])

  useEffect(() => {
    const scopedTorneoId = parseTorneoId(selectedTorneoId)
    if (!selectedDate || scopedTorneoId === null) return

    let cancelled = false

    async function fetchMatches({ background = false } = {}) {
      if (!background) {
        setMatches([])
        setError(null)
        setIsLoading(true)
      }
      const queryDate = formatDateForQuery(selectedDate)
      
      const { data, error } = await supabase
        .from('partidos')
        .select(`
          id,
          fecha_id,
          dia,
          hora,
          cancha,
          goles_local,
          goles_visitante,
          estado,
          categoria_id,
          local_id,
          visitante_id,
          local:local_id ( nombre ),
          visitante:visitante_id ( nombre )
        `)
        .gte('dia', queryDate)
        .lte('dia', queryDate)
        .eq('torneo_id', scopedTorneoId)
        .not('visitante_id', 'is', null)
        .order('categoria_id', { ascending: false })

      if (cancelled) return

      if (error) {
        console.error('Error fetching matches:', error)
        if (!background) {
          setMatches([])
          setError('No se pudieron cargar los partidos de esta fecha.')
        }
      } else {
        let goleadoresMap = {}
        if (data?.length) {
          const partidoIds = data.map((partido) => partido.id)
          const { data: aliData, error: alineacionesError } = await supabase
            .from('alineaciones')
            .select('partido_id, equipo_id, nombre, goleo, goles_en_contra')
            .in('partido_id', partidoIds)
            .or('goleo.gt.0,goles_en_contra.gt.0')

          if (cancelled) return
          if (alineacionesError) {
            console.error('Error fetching alineaciones:', alineacionesError)
          } else {
            goleadoresMap = buildLineupScorerLabels(data, aliData)
          }
        }

        const matchesWithScorers = (data || []).map((match) => ({
          ...match,
          goleadoresLocal: goleadoresMap[match.id]?.local || [],
          goleadoresVisita: goleadoresMap[match.id]?.visitor || [],
        }))

        setMatches(matchesWithScorers)
      }
      if (!background) setIsLoading(false)
    }
    
    fetchMatches()
    const refreshInterval = window.setInterval(() => {
      if (document.visibilityState === 'visible' && liveMatchesRef.current) {
        fetchMatches({ background: true })
      }
    }, 60_000)
    return () => {
      cancelled = true
      window.clearInterval(refreshInterval)
    }
  }, [selectedDate, selectedTorneoId])

  const getPreviousMatchDate = () => {
    if (!selectedDate || datesWithMatches.length === 0) return null
    
    const sortedDates = datesWithMatches
      .map(d => parseDate(d))
      .filter(d => d !== null)
      .sort((a, b) => b.getTime() - a.getTime())
    
    for (const date of sortedDates) {
      if (date.getTime() < selectedDate.getTime()) {
        return date
      }
    }
    return null
  }

  const getNextMatchDate = () => {
    if (!selectedDate || datesWithMatches.length === 0) return null
    
    const sortedDates = datesWithMatches
      .map(d => parseDate(d))
      .filter(d => d !== null)
      .sort((a, b) => a.getTime() - b.getTime())
    
    for (const date of sortedDates) {
      if (date.getTime() > selectedDate.getTime()) {
        return date
      }
    }
    return null
  }

  const handlePrevDay = () => {
    const prevDate = getPreviousMatchDate()
    if (prevDate) setSelectedDate(prevDate)
  }

  const handleNextDay = () => {
    const nextDate = getNextMatchDate()
    if (nextDate) setSelectedDate(nextDate)
  }

  const handleGoToToday = () => {
    const hoy = new Date()
    const todayStr = formatDateForQuery(hoy)
    
    // Buscar si hay partidos hoy
    const hasToday = datesWithMatches.includes(todayStr)
    if (hasToday) {
      setSelectedDate(hoy)
    } else {
      // Buscar la fecha más cercana
      const sortedDates = datesWithMatches
        .map(d => parseDate(d))
        .filter(d => d !== null)
        .sort((a, b) => a.getTime() - b.getTime())
      
      for (const date of sortedDates) {
        if (date.getTime() > hoy.getTime()) {
          setSelectedDate(date)
          return
        }
      }
    }
  }

  const isToday = selectedDate && new Date().toDateString() === selectedDate.toDateString()

  if (parseTorneoId(selectedTorneoId) === null) {
    return (
      <div className='text-center py-8 text-yellow-200 text-xs uppercase tracking-widest' role='status'>
        Seleccioná un torneo válido para ver sus partidos.
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>
        Cargando partidos...
      </div>
    )
  }

  if (error) {
    return <div className='text-center py-8 text-red-300 text-xs font-semibold' role='alert'>{error}</div>
  }

  if (!selectedDate) {
    return (
      <div className='text-center py-8 text-green-700 text-xs uppercase tracking-widest'>
        No hay partidos disponibles para este torneo
      </div>
    )
  }

  const groupedByCategory = {}
  for (const match of matches) {
    if (!groupedByCategory[match.categoria_id]) {
      groupedByCategory[match.categoria_id] = []
    }
    groupedByCategory[match.categoria_id].push(match)
  }

  return (
    <div>
      <div className='mb-3 flex items-center justify-between rounded-xl border border-green-800/50 bg-green-950/25 p-1.5'>
        <button
          type='button'
          onClick={handlePrevDay}
          disabled={!getPreviousMatchDate()}
          aria-label='Ir al día anterior con partidos'
          className='grid h-8 w-8 place-items-center rounded-lg text-lg text-green-400 transition hover:bg-green-400 hover:text-[#082310] disabled:cursor-not-allowed disabled:opacity-25'
        >
          ‹
        </button>
        
        <div className='flex flex-col items-center gap-1 sm:flex-row sm:gap-3'>
          <span className='font-[var(--font-display)] text-sm font-black uppercase tracking-[0.12em] text-green-100'>
            {getDayName(selectedDate)} {formatDateForDisplay(selectedDate)}
          </span>
          {!isToday && (
            <button
              onClick={handleGoToToday}
              className='text-[8px] font-extrabold uppercase tracking-[0.12em] text-green-600 hover:text-green-400'
            >
              Ir a hoy
            </button>
          )}
        </div>
        
        <button
          type='button'
          onClick={handleNextDay}
          disabled={!getNextMatchDate()}
          aria-label='Ir al día siguiente con partidos'
          className='grid h-8 w-8 place-items-center rounded-lg text-lg text-green-400 transition hover:bg-green-400 hover:text-[#082310] disabled:cursor-not-allowed disabled:opacity-25'
        >
          ›
        </button>
      </div>

      {matches.length === 0 ? (
        <div className='text-center py-8 text-green-700 text-xs uppercase tracking-widest'>
          No hay partidos programados para esta fecha
        </div>
      ) : (
        <div className='space-y-3'>
          {Object.keys(groupedByCategory)
            .sort((a, b) => b - a)
            .map((categoriaId) => (
              <section key={categoriaId} className='overflow-hidden rounded-xl border border-green-800/60 bg-green-950/20'>
                <div className='flex items-center justify-between border-b border-green-800/50 bg-[#092716] px-3 py-2.5 text-[10px] font-bold uppercase tracking-wider text-green-600 sm:px-4'>
                  <span className='font-[var(--font-display)] text-sm font-black tracking-[0.08em] text-green-100'>{CATEGORIAS[categoriaId]}</span>
                  <a
                    href={withTorneoParam(CATEGORIAS_ROUTES[categoriaId], selectedTorneoId)}
                    className='rounded-full border border-green-400/15 px-2.5 py-1 text-[8px] font-extrabold tracking-[0.14em] text-green-500 transition hover:border-yellow-300/40 hover:text-yellow-300'
                  >
                    Ver más
                  </a>
                </div>
                <div className='divide-y divide-green-800/45'>
                  {groupedByCategory[categoriaId].map((match) => {
                    const isLibre = match.visitante_id === null
                    const seJugo = isMatchPlayed(match)
                    const enJuego = isMatchLive(match, now)
                    const estadoNormalizado = String(match.estado || '').trim().toLowerCase()
                    const esSuspendido = estadoNormalizado === 'suspendido'
                    const tieneObservacion = Boolean(match.estado && !['programado', 'jugado', 'libre'].includes(estadoNormalizado))
                    const mostrarCancha = debeMostrarCancha(match.cancha, match.local?.nombre)
                    const linkPartido = seJugo && Number(categoriaId) === 1 && !isLibre
                    const matchUrl = linkPartido
                      ? withTorneoParam(
                          `/partido/t${selectedTorneoId}-p${match.id}-${slugify(match.local?.nombre || '')}-vs-${slugify(match.visitante?.nombre || '')}`,
                          selectedTorneoId,
                        )
                      : null

                    if (isLibre) {
                      return (
                        <div
                          key={match.id}
                          className='flex items-center justify-center gap-2 bg-green-950/20 px-3 py-3 text-xs'
                        >
                          <span className='text-xs font-medium text-green-100 sm:text-sm'>{match.local?.nombre}</span>
                          <img src={getEscudoPath(match.local.nombre)} alt={match.local.nombre} className='h-4 w-4 shrink-0 object-contain sm:h-5 sm:w-5' />
                          <span className='text-xs font-semibold text-green-700 sm:text-sm'>LIBRE</span>
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
                            <span>{formatDateForDisplay(selectedDate)} <span className='font-semibold text-green-400'>JUGADO</span></span>
                          ) : esSuspendido ? (
                            <span className='text-red-400 font-bold uppercase tracking-wide'>SUSPENDIDO</span>
                          ) : tieneObservacion ? (
                            <span className='text-yellow-400 font-bold uppercase tracking-wide'>{match.estado}</span>
                          ) : enJuego ? (
                            <LiveMatchBadge />
                          ) : match.hora ? (
                            <span>{formatDateForDisplay(selectedDate)} - {match.hora.slice(0, 5)}hs</span>
                          ) : (
                            <span>{formatDateForDisplay(selectedDate)} - A DEFINIR</span>
                          )}
                        </div>
                        <div className='flex items-center gap-2'>
                          <div className='flex-1 flex items-center gap-1 justify-end min-w-0'>
                            <span className='text-right text-xs font-extrabold text-green-50 sm:text-sm'>{match.local?.nombre}</span>
                            {match.local?.nombre && <img src={getEscudoPath(match.local.nombre)} alt={match.local.nombre} className='h-6 w-6 shrink-0 object-contain' />}
                          </div>
                          <div className='flex min-w-[46px] shrink-0 items-center justify-center rounded-md bg-black/15 px-1.5 py-1'>
                            {seJugo ? (
                              <><span className='text-base font-black tabular-nums text-white sm:text-lg'>{match.goles_local}</span><span className='mx-1 text-green-700'>–</span><span className='text-base font-black tabular-nums text-white sm:text-lg'>{match.goles_visitante}</span></>
                            ) : (
                              <span className='font-[var(--font-display)] text-xs font-bold uppercase text-green-600'>vs</span>
                            )}
                          </div>
                          <div className='flex-1 flex items-center gap-1 min-w-0'>
                            {match.visitante?.nombre && <img src={getEscudoPath(match.visitante.nombre)} alt={match.visitante.nombre} className='h-6 w-6 shrink-0 object-contain' />}
                            <span className='text-xs font-extrabold text-green-50 sm:text-sm'>{match.visitante?.nombre}</span>
                          </div>
                        </div>
                        {mostrarCancha && (
                          <div className='mt-1 inline-flex w-fit max-w-full items-center gap-1 rounded-full border border-yellow-300/30 bg-yellow-300/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-yellow-200'>
                            <span className='text-yellow-400'>Cancha</span>
                            <span className='truncate'>{match.cancha}</span>
                          </div>
                        )}
                        {seJugo && ((match.goleadoresLocal?.length || 0) > 0 || (match.goleadoresVisita?.length || 0) > 0) && (
                          <div className='flex mt-1 gap-2'>
                            <div className='flex-1 text-right text-[9px] sm:text-[10px] text-green-500/80 space-y-0.5 pr-3'>
                              {match.goleadoresLocal.map((goleador, index) => (
                                <div key={`l${index}`} className='truncate'>{goleador}</div>
                              ))}
                            </div>
                            <div className='flex-1 text-left text-[9px] sm:text-[10px] text-green-500/80 space-y-0.5 pl-3'>
                              {match.goleadoresVisita.map((goleador, index) => (
                                <div key={`v${index}`} className='truncate'>{goleador}</div>
                              ))}
                            </div>
                          </div>
                        )}
                      </Row>
                    )
                  })}
                </div>
              </section>
            ))}
        </div>
      )}
    </div>
  )
}
