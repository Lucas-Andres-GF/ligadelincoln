import { useEffect, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { slugify } from '../utils/slugify'

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
      return new Date(aa.includes('20') ? anio : `20${aa}`, parseInt(mm) - 1, parseInt(dd))
    }
    const [dd, mm] = parts.map(Number)
    if (dd > 12) {
      return new Date(anio, parseInt(mm) - 1, dd)
    }
    return new Date(anio, dd - 1, parseInt(mm))
  }
  if (dia.includes('-')) {
    const [aa, mm, dd] = dia.split('-')
    return new Date(aa.includes('20') ? anio : `20${aa}`, parseInt(mm) - 1, parseInt(dd))
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

export default function PartidosHoy() {
  const [selectedDate, setSelectedDate] = useState(null)
  const [datesWithMatches, setDatesWithMatches] = useState([])
  const [matches, setMatches] = useState([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    async function fetchDates() {
      const { data: allPartidos } = await supabase
        .from('partidos')
        .select('dia')
        .not('dia', 'is', null)
      
      if (allPartidos && allPartidos.length > 0) {
        const dates = [...new Set(allPartidos.map(p => p.dia))].filter(Boolean)
        setDatesWithMatches(dates)
        
        const hoy = new Date()
        hoy.setHours(0, 0, 0, 0)
        
        // Buscar la proxima fecha (futura)
        let nextDate = null
        let minFutureDiff = Infinity
        
        // Buscar la fecha mas cercana futura
        for (const dia of dates) {
          const matchDate = parseDate(dia)
          if (matchDate) {
            const diff = matchDate.getTime() - hoy.getTime()
            if (diff >= 0 && diff < minFutureDiff) {
              minFutureDiff = diff
              nextDate = matchDate
            }
          }
        }
        
        if (nextDate) {
          setSelectedDate(nextDate)
        } else {
          setSelectedDate(hoy)
        }
      }
    }
    fetchDates()
  }, [])

  useEffect(() => {
    if (!selectedDate) return
    
    async function fetchMatches() {
      setIsLoading(true)
      
      const startOfDay = formatDateForQuery(selectedDate)
      const endOfDay = formatDateForQuery(selectedDate)
      
      const { data, error } = await supabase
        .from('partidos')
        .select(`
          id,
          fecha_id,
          dia,
          hora,
          goles_local,
          goles_visitante,
          estado,
          categoria_id,
          local_id,
          visitante_id,
          local:local_id ( nombre ),
          visitante:visitante_id ( nombre )
        `)
        .gte('dia', startOfDay)
        .lte('dia', endOfDay)
        .not('visitante_id', 'is', null)
        .order('categoria_id', { ascending: false })

      if (!error && data) {
        setMatches(data)
      }
      setIsLoading(false)
    }
    
    fetchMatches()
  }, [selectedDate])

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

  if (isLoading) {
    return (
      <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>
        Cargando...
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
      <div className='flex items-center justify-between mb-4'>
        <button
          onClick={handlePrevDay}
          disabled={!getPreviousMatchDate()}
          className='p-2 rounded-lg bg-green-900/30 hover:bg-green-900/50 text-green-400 transition-colors disabled:opacity-30 disabled:cursor-not-allowed'
        >
          <svg className='w-5 h-5' fill='none' viewBox='0 0 24 24' stroke='currentColor'>
            <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={2} d='M15 19l-7-7 7-7' />
          </svg>
        </button>
        
        <div className='flex items-center gap-3'>
          <span className='text-green-400 font-bold text-sm uppercase tracking-wider'>
            {getDayName(selectedDate)} {formatDateForDisplay(selectedDate)}
          </span>
          {!isToday && (
            <button
              onClick={handleGoToToday}
              className='text-xs text-green-600 hover:text-green-400 underline'
            >
              Ir a hoy
            </button>
          )}
        </div>
        
        <button
          onClick={handleNextDay}
          disabled={!getNextMatchDate()}
          className='p-2 rounded-lg bg-green-900/30 hover:bg-green-900/50 text-green-400 transition-colors disabled:opacity-30 disabled:cursor-not-allowed'
        >
          <svg className='w-5 h-5' fill='none' viewBox='0 0 24 24' stroke='currentColor'>
            <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={2} d='M9 5l7 7-7 7' />
          </svg>
        </button>
      </div>

      {matches.length === 0 ? (
        <div className='text-center py-8 text-green-700 text-xs uppercase tracking-widest'>
          No hay partidos programados para esta fecha
        </div>
      ) : (
        <div className='space-y-4'>
          {Object.keys(groupedByCategory)
            .sort((a, b) => b - a)
            .map((categoriaId) => (
              <div key={categoriaId}>
                <div className='flex items-center justify-between text-[10px] font-bold text-green-600 uppercase tracking-wider mb-2'>
                  <span>{CATEGORIAS[categoriaId]}</span>
                  <a
                    href={CATEGORIAS_ROUTES[categoriaId]}
                    className='text-green-500 hover:text-green-400 text-[9px] underline'
                  >
                    Ver más
                  </a>
                </div>
                <div className='space-y-1'>
                  {groupedByCategory[categoriaId].map((match, i) => {
                    const isLibre = match.visitante_id === null
                    const seJugo = match.estado === 'jugado' || (match.goles_local !== null && match.goles_visitante !== null)

                    if (isLibre) {
                      return (
                        <div
                          key={i}
                          className='flex items-center gap-1 py-1 px-2 rounded-lg bg-green-950/20 border border-dashed border-green-900/30 text-xs'
                        >
                          <span className='text-[10px] text-green-500 font-bold w-12 shrink-0 text-left'></span>
                          <a
                            href={`/club/${slugify(match.local?.nombre || '')}?categoria=${match.categoria_id}`}
                            className='flex items-center gap-1 flex-1 justify-end min-w-0 hover:opacity-80'
                          >
                            {match.local?.nombre && (
                                <img
                                  src={getEscudoPath(match.local.nombre)}
                                  alt={match.local.nombre}
                                  className="w-8 h-8 object-contain"
                                />
                            )}
                            <span className='truncate text-green-100 font-semibold text-right text-[10px]'>
                              {match.local?.nombre}
                            </span>
                          </a>
                          <span className='text-green-700 font-bold text-[10px] '></span>
                          <span className='flex-1 text-left text-green-400 font-bold uppercase text-[10px]'>
                            LIBRE
                          </span>
                        </div>
                      )
                    }

                    return (
                      <div
                        key={i}
                        className='flex items-center gap-1 py-1 px-2 rounded-lg bg-green-950/30 hover:bg-green-400/5 transition-colors text-xs'
                      >
                        <span className='text-[10px] text-green-500 font-bold w-12 shrink-0 text-left'>
                          {seJugo ? 'JUGADO' : (match.hora ? match.hora.slice(0, 5) + 'hs' : '')}
                        </span>
                        <a
                          href={`/club/${slugify(match.local?.nombre || '')}?categoria=${match.categoria_id}`}
                          className='flex items-center gap-1 flex-1 justify-end min-w-0 hover:opacity-80'
                        >
                          <span className='truncate text-green-100 font-semibold text-right text-[10px]'>
                            {match.local?.nombre}
                          </span>
                          {match.local?.nombre && (
                                <img
                                  src={getEscudoPath(match.local.nombre)}
                                  alt={match.local.nombre}
                                  className="w-6 h-6 object-contain"
                                />
                            )}
                        </a>
                        <div className='flex items-center gap-1 shrink-0 px-1 min-w-[40px] justify-center'>
                          {seJugo ? (
                            <>
                              <span className='font-black text-green-400 text-xs w-3 text-center'>
                                {match.goles_local}
                              </span>
                              <span className='text-green-700'>–</span>
                              <span className='font-black text-green-400 text-xs w-3 text-center'>
                                {match.goles_visitante}
                              </span>
                            </>
                          ) : (
                            <span className='text-green-700 font-bold text-[10px]'>
                              vs
                            </span>
                          )}
                        </div>
                        <a
                          href={`/club/${slugify(match.visitante?.nombre || '')}?categoria=${match.categoria_id}`}
                          className='flex items-center gap-1 flex-1 min-w-0 hover:opacity-80'
                        >
                          {match.visitante?.nombre && (
                                <img
                                  src={getEscudoPath(match.visitante.nombre)}
                                  alt={match.visitante.nombre}
                                  className="w-6 h-6 object-contain"
                                />
                            )}
                          <span className='truncate text-green-100 font-semibold text-[10px]'>
                            {match.visitante?.nombre}
                          </span>
                        </a>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
