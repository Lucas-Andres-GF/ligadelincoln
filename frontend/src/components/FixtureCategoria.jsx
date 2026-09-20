import { useEffect, useMemo, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { cachedQuery } from '../utils/supabaseCached'
import { slugify } from '../utils/slugify'
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

  useEffect(() => listenToTorneoChange(setSelectedTorneoId), [])

  useEffect(() => {
    let cancelled = false

    async function fetchFixture() {
      setAllMatches({})
      setAvailableFechas([])
      setFechaActual(null)
      setDropdownOpen(false)
      setError(null)

      const scopedTorneoId = parseTorneoId(selectedTorneoId)
      if (scopedTorneoId === null) {
        setIsLoading(false)
        return
      }

      setIsLoading(true)
      const cacheKey = `fixture_torneo_${scopedTorneoId}_categoria_${categoria}`
      const { data, error: partidosError } = await cachedQuery(cacheKey, () =>
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
          .order('id'),
      )

      if (cancelled) return
      if (partidosError) {
        console.error('Error fetching partidos:', partidosError)
        setError('No se pudo cargar el fixture de este torneo.')
        setIsLoading(false)
        return
      }

      let goleadoresMap = {}
      if (data?.length) {
        const partidoIds = data.map((partido) => partido.id)
        // alineaciones has no torneo_id. This bounded read is safe only because
        // every partido ID came from the tournament-scoped partidos query above.
        const { data: aliData, error: alineacionesError } = await supabase
          .from('alineaciones')
          .select('partido_id, equipo_id, nombre, goleo')
          .in('partido_id', partidoIds)
          .gt('goleo', 0)

        if (cancelled) return
        if (alineacionesError) {
          console.error('Error fetching alineaciones:', alineacionesError)
          setError('Se cargó el fixture, pero no se pudieron cargar los goleadores.')
        } else {
          for (const alineacion of aliData || []) {
            if (!goleadoresMap[alineacion.partido_id]) goleadoresMap[alineacion.partido_id] = {}
            const equipoId = String(alineacion.equipo_id)
            if (!goleadoresMap[alineacion.partido_id][equipoId]) {
              goleadoresMap[alineacion.partido_id][equipoId] = []
            }
            const abbreviated = alineacion.nombre
              .split(' ')
              .map((part, index) => (index === 0 ? part : `${part.charAt(0)}.`))
              .join(' ')
            for (let goal = 0; goal < alineacion.goleo; goal += 1) {
              goleadoresMap[alineacion.partido_id][equipoId].push(`${abbreviated} ⚽`)
            }
          }
        }
      }

      const grouped = {}
      for (const match of data || []) {
        const withScorers = {
          ...match,
          goleadoresLocal: goleadoresMap[match.id]?.[String(match.local_id)] || [],
          goleadoresVisita: goleadoresMap[match.id]?.[String(match.visitante_id)] || [],
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
      setFechaActual(detectarFechaActual(grouped, fechas))
      setIsLoading(false)
    }

    fetchFixture()
    return () => {
      cancelled = true
    }
  }, [categoria, selectedTorneoId])

  const currentIndex = availableFechas.indexOf(String(fechaActual))
  const matches = useMemo(
    () => (fechaActual === null ? [] : allMatches[fechaActual] || []),
    [allMatches, fechaActual],
  )

  if (parseTorneoId(selectedTorneoId) === null) {
    return (
      <div className='text-center py-8 text-yellow-200 text-xs uppercase tracking-widest' role='status'>
        Seleccioná un torneo válido para ver el fixture.
      </div>
    )
  }

  if (isLoading) {
    return <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>Cargando fixture…</div>
  }

  if (error && availableFechas.length === 0) {
    return <div className='text-center py-8 text-red-300 text-xs font-semibold' role='alert'>{error}</div>
  }

  if (availableFechas.length === 0) {
    return <div className='text-center py-8 text-green-700 text-xs uppercase tracking-widest'>No hay partidos cargados para este torneo.</div>
  }

  return (
    <div className='p-2 md:p-4 pb-16'>
      {error && <div className='mb-3 text-center text-red-300 text-xs font-semibold' role='alert'>{error}</div>}
      <div className='flex items-center justify-between mb-2 md:mb-4'>
        <button
          type='button'
          onClick={() => setFechaActual(availableFechas[currentIndex - 1])}
          disabled={currentIndex <= 0}
          aria-label='Ir a la fecha anterior'
          className='w-7 h-7 md:w-8 md:h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30 text-sm md:text-base'
        >‹</button>
        <div className='relative'>
          <button
            type='button'
            onClick={() => setDropdownOpen((open) => !open)}
            aria-expanded={dropdownOpen}
            aria-controls={`fixture-fechas-${categoria}`}
            aria-label={`Seleccionar fecha. Fecha actual ${fechaActual}`}
            className='flex items-center gap-1 px-2 py-1 md:px-3 md:py-1.5 rounded-lg bg-green-900/40 text-green-400 hover:bg-green-900/60 transition-all font-bold text-xs md:text-sm uppercase tracking-wide cursor-pointer'
          >
            Fecha {fechaActual}
            <svg className={`w-3 h-3 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} fill='none' viewBox='0 0 24 24' stroke='currentColor' aria-hidden='true'>
              <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={3} d='M19 9l-7 7-7-7' />
            </svg>
          </button>
          {dropdownOpen && (
            <>
              <button type='button' className='fixed inset-0 z-[99] cursor-default' onClick={() => setDropdownOpen(false)} aria-label='Cerrar selector de fecha' />
              <div id={`fixture-fechas-${categoria}`} className='absolute top-full left-1/2 -translate-x-1/2 mt-1 bg-[#143814] border border-green-900/60 rounded-lg shadow-2xl z-[100] overflow-y-auto max-h-60 min-w-[80px]'>
                {availableFechas.map((fechaId) => (
                  <button
                    type='button'
                    key={fechaId}
                    onClick={() => {
                      setFechaActual(fechaId)
                      setDropdownOpen(false)
                    }}
                    className={`block w-full px-3 py-1 text-center text-xs font-semibold whitespace-nowrap transition-colors ${String(fechaId) === String(fechaActual) ? 'bg-green-400 text-black' : 'text-green-400 hover:bg-green-900/40'}`}
                  >Fecha {fechaId}</button>
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
          className='w-7 h-7 md:w-8 md:h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30 text-sm md:text-base'
        >›</button>
      </div>

      {matches.length === 0 ? (
        <div className='text-center py-8 text-green-700 text-xs uppercase tracking-widest'>No hay partidos en esta fecha.</div>
      ) : (
        <div className='space-y-2'>
          {matches.map((match) => {
            const isLibre = match.visitante_id === null
            const seJugo = match.estado === 'jugado' || (match.goles_local !== null && match.goles_visitante !== null)
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
                <div key={match.id} className='flex items-center justify-center gap-2 py-1 px-2 rounded-lg bg-green-900/30 border border-green-800/50 text-xs'>
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
                className={`flex flex-col gap-0 py-1 px-2 rounded-lg bg-green-900/30 hover:bg-green-900/50 transition-colors text-xs border border-green-800/50 ${linkPartido ? 'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-yellow-300' : ''}`}
              >
                <div className='text-[10px] sm:text-xs text-green-600 font-medium mb-1'>
                  {seJugo ? (
                    formatearFechaMostrar(match.dia) ? <span>{formatearFechaMostrar(match.dia)} <span className='text-green-400 font-semibold'>JUGADO</span></span> : <span className='text-green-400 font-semibold'>JUGADO</span>
                  ) : esSuspendido ? (
                    <span className='text-red-400 font-bold uppercase tracking-wide'>SUSPENDIDO</span>
                  ) : tieneObservacion ? (
                    <span className='text-yellow-400 font-bold uppercase tracking-wide'>{match.estado}</span>
                  ) : match.hora ? (
                    <span>{formatearFechaMostrar(match.dia) || 'A DEFINIR'} - {match.hora.slice(0, 5)}hs</span>
                  ) : (
                    formatearFechaMostrar(match.dia) || <span className='font-semibold'>A DEFINIR</span>
                  )}
                </div>
                <div className='flex items-center gap-1'>
                  <div className='flex-1 flex items-center gap-1 justify-end min-w-0'>
                    <span className='text-green-100 font-medium text-xs sm:text-sm text-right'>{match.local?.nombre}</span>
                    {match.local?.nombre && <img src={getEscudoPath(match.local.nombre)} alt={match.local.nombre} className='w-4 h-4 sm:w-5 sm:h-5 object-contain shrink-0' />}
                  </div>
                  <div className='flex items-center shrink-0 min-w-[36px] justify-center'>
                    {seJugo ? <><span className='font-bold text-green-300 text-sm sm:text-base tabular-nums'>{match.goles_local}</span><span className='text-green-700 mx-0.5'>–</span><span className='font-bold text-green-300 text-sm sm:text-base tabular-nums'>{match.goles_visitante}</span></> : <span className='text-green-700 font-semibold text-xs sm:text-sm'>vs</span>}
                  </div>
                  <div className='flex-1 flex items-center gap-1 min-w-0'>
                    {match.visitante?.nombre && <img src={getEscudoPath(match.visitante.nombre)} alt={match.visitante.nombre} className='w-4 h-4 sm:w-5 sm:h-5 object-contain shrink-0' />}
                    <span className='text-green-100 font-medium text-xs sm:text-sm'>{match.visitante?.nombre}</span>
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
