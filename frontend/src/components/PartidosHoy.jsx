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
                          className='flex items-center justify-center gap-2 py-1 px-2 rounded-lg bg-green-900/30 border border-green-800/50 text-xs'
                        >
                          <span className='text-green-100 font-medium text-xs'>{match.local?.nombre}</span>
                          <img src={getEscudoPath(match.local.nombre)} alt={match.local.nombre} className='w-5 h-5 object-contain shrink-0' />
                          <span className='text-green-700 font-semibold text-xs'>LIBRE</span>
                        </div>
                      )
                    }

                    return (
                      <div
                        key={i}
                        className='flex flex-col gap-0 py-1 px-2 rounded-lg bg-green-900/30 hover:bg-green-900/50 transition-colors text-xs border border-green-800/50'
                      >
                        <div className='text-[10px] text-green-600 font-medium mb-1'>
                          {seJugo ? 'JUGADO' : (match.hora ? match.hora.slice(0, 5) + 'hs' : '')}
                        </div>
                        <div className='flex items-center gap-1'>
                          <div className='flex-1 flex items-center gap-1 justify-end min-w-0'>
                            <span className='text-green-100 font-medium text-xs text-right'>{match.local?.nombre}</span>
                            {match.local?.nombre && <img src={getEscudoPath(match.local.nombre)} alt={match.local.nombre} className="w-5 h-5 object-contain shrink-0" />}
                          </div>
                          <div className='flex items-center shrink-0 min-w-[36px] justify-center'>
                            {seJugo ? (
                              <><span className='font-bold text-green-300 text-sm'>{match.goles_local}</span><span className='text-green-700 mx-0.5'>–</span><span className='font-bold text-green-300 text-sm'>{match.goles_visitante}</span></>
                            ) : (
                              <span className='text-green-700 font-semibold text-xs'>vs</span>
                            )}
                          </div>
                          <div className='flex-1 flex items-center gap-1 min-w-0'>
                            {match.visitante?.nombre && <img src={getEscudoPath(match.visitante.nombre)} alt={match.visitante.nombre} className="w-5 h-5 object-contain shrink-0" />}
                            <span className='text-green-100 font-medium text-xs'>{match.visitante?.nombre}</span>
                          </div>
                        </div>
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
