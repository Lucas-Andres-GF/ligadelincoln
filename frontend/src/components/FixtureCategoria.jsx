import { useEffect, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { cachedQuery } from '../utils/supabaseCached'
import { slugify } from '../utils/slugify'

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY
const supabase = createClient(supabaseUrl, supabaseKey)

const TOTAL_FECHAS = 11

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

function detectarFechaActual(grouped) {
  const hoy = new Date()
  hoy.setHours(0, 0, 0, 0)
  const anio = hoy.getFullYear()
  
  let mejor = 1
  let menorDiff = Infinity
  let mejorPasado = 1
  let mayorDiffMenorCero = -Infinity
  
  const fechas = Object.keys(grouped)
    .map(Number)
    .sort((a, b) => a - b)

  for (const fechaNum of fechas) {
    const partido = grouped[fechaNum][0]
    if (!partido?.dia) continue
    
    const fechaPartido = parseDate(partido.dia)
    if (!fechaPartido) continue
    
    const diff = fechaPartido.getTime() - hoy.getTime()
    
    if (diff >= 0 && diff < menorDiff) {
      menorDiff = diff
      mejor = fechaNum
    }
    
    if (diff < 0 && diff > mayorDiffMenorCero) {
      mayorDiffMenorCero = diff
      mejorPasado = fechaNum
    }
  }
  
  return menorDiff !== Infinity ? mejor : mejorPasado
}

function formatearFechaMostrar(dia) {
  if (!dia) return ''
  if (dia.includes('/')) {
    const parts = dia.split('/')
    if (parts.length === 3) {
      const [dd, mm, aa] = parts
      if (parseInt(dd) > 12) {
        return `${dd}/${mm}`
      }
      return `${mm}/${dd}`
    }
    return dia
  }
  if (dia.includes('-')) {
    const [aa, mm, dd] = dia.split('-')
    return `${dd}/${mm}`
  }
  return dia
}

export default function FixtureCategoria({ categoria }) {
  const categoriaNombres = {
    1: 'PRIMERA',
    2: 'SEPTIMA',
    3: 'OCTAVA',
    4: 'NOVENA',
    5: 'DECIMA',
  }
  const nombreCategoria =
    categoriaNombres[categoria] || `CATEGORÍA ${categoria}`
  const [allMatches, setAllMatches] = useState({})
  const [fechaActual, setFechaActual] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [dropdownOpen, setDropdownOpen] = useState(false)

  useEffect(() => {
    async function fetchFixture() {
      const cacheKey = `fixture_categoria_${categoria}`
      
      const { data, error } = await cachedQuery(cacheKey, () =>
        supabase
          .from('partidos')
          .select(
            `
            id,
            fecha_id,
            dia,
            hora,
            goles_local,
            goles_visitante,
            estado,
            local_id,
            visitante_id,
            local:local_id ( nombre ),
            visitante:visitante_id ( nombre )
          `,
          )
          .order('fecha_id')
          .order('id')
          .eq('categoria_id', categoria)
      )

      // Fetch alineaciones with goleo for all matches
      let goleadoresMap = {}
      if (data && data.length > 0) {
        const partidoIds = data.map(p => p.id)
        const { data: aliData } = await supabase
          .from('alineaciones')
          .select('partido_id, equipo_id, nombre, goleo')
          .in('partido_id', partidoIds)
          .gt('goleo', 0)
        
        // Group by partido and equipo (each ⚽ as separate entry)
        for (const a of aliData || []) {
          if (!goleadoresMap[a.partido_id]) goleadoresMap[a.partido_id] = {}
          const key = String(a.equipo_id)
          if (!goleadoresMap[a.partido_id][key]) goleadoresMap[a.partido_id][key] = []
          // Truncate: "PEREYRA SEGUROLA JOAQUIN" -> "PEREYRA S.J"
          const truncated = a.nombre.split(' ').map((part, i) => 
            i === 0 ? part : part.charAt(0) + '.'
          ).join(' ')
          // Each goal = one line
          for (let i = 0; i < a.goleo; i++) {
            goleadoresMap[a.partido_id][key].push(truncated + ' ⚽')
          }
        }
      }

      if (error) {
        console.error('Error fetching partidos:', error)
      } else {
        // Attach goleadores to matches (normalize keys to string)
        for (const m of data) {
          m.goleadoresLocal = goleadoresMap[m.id]?.[String(m.local_id)] || []
          m.goleadoresVisita = goleadoresMap[m.id]?.[String(m.visitante_id)] || []
        }
        
        const grouped = {}
        for (const m of data) {
          if (!grouped[m.fecha_id]) grouped[m.fecha_id] = []
          grouped[m.fecha_id].push(m)
        }
        
        // Ordenar cada fecha por dia y hora
        for (const fecha of Object.keys(grouped)) {
          grouped[fecha].sort((a, b) => {
            // LIBRE siempre al final
            if (a.visitante_id === null && b.visitante_id !== null) return 1
            if (b.visitante_id === null && a.visitante_id !== null) return -1
            
            const fechaA = parseDate(a.dia)
            const fechaB = parseDate(b.dia)
            if (fechaA && fechaB) {
              if (fechaA.getTime() !== fechaB.getTime()) {
                return fechaA - fechaB
              }
            } else if (fechaA) return -1
            else if (fechaB) return 1
            
            // Si son el mismo día, ordenar por hora
            const horaA = a.hora || ''
            const horaB = b.hora || ''
            return horaA.localeCompare(horaB)
          })
        }
        
        setAllMatches(grouped)
        setFechaActual(detectarFechaActual(grouped))
      }
      setIsLoading(false)
    }
    fetchFixture()
  }, [categoria])

  const matches = allMatches[fechaActual] || []

  if (isLoading) {
    return (
      <div className='text-center py-8 text-green-700 animate-pulse text-xs uppercase tracking-widest'>
        Cargando...
      </div>
    )
  }

  return (
    <div className='p-2 md:p-4 pb-16'>
      <div className='flex items-center justify-between mb-2 md:mb-4'>
        <button
          onClick={() => setFechaActual((f) => Math.max(1, f - 1))}
          disabled={fechaActual === 1}
          className='w-7 h-7 md:w-8 md:h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30 text-sm md:text-base'
        >
          ‹
        </button>
        <div className='relative'>
          <div
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className='flex items-center gap-1 px-2 py-1 md:px-3 md:py-1.5 rounded-lg bg-green-900/40 text-green-400 hover:bg-green-900/60 transition-all font-bold text-xs md:text-sm uppercase tracking-wide cursor-pointer'
          >
            Fecha {fechaActual}
            <svg
              className={`w-3 h-3 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`}
              fill='none'
              viewBox='0 0 24 24'
              stroke='currentColor'
            >
              <path
                strokeLinecap='round'
                strokeLinejoin='round'
                strokeWidth={3}
                d='M19 9l-7 7-7-7'
              />
            </svg>
          </div>
          {dropdownOpen && (
            <>
              <div 
                className='fixed inset-0 z-[99]' 
                onClick={() => setDropdownOpen(false)}
              />
              <div className='absolute top-full left-1/2 -translate-x-1/2 mt-1 bg-[#143814] border border-green-900/60 rounded-lg shadow-2xl z-[100] overflow-y-auto max-h-60 min-w-[80px]'>
              {Array.from({ length: TOTAL_FECHAS }, (_, i) => i + 1).map(
                (f) => (
                  <button
                    key={f}
                    onClick={() => {
                      setFechaActual(f)
                      setDropdownOpen(false)
                    }}
                    className={`block w-full px-3 py-1 text-center text-xs font-semibold whitespace-nowrap transition-colors ${
                      f === fechaActual
                        ? 'bg-green-400 text-black'
                        : 'text-green-400 hover:bg-green-900/40'
                    }`}
                  >
                    Fecha {f}
                  </button>
                ),
              )}
            </div>
            </>
          )}
        </div>
        <button
          onClick={() => setFechaActual((f) => Math.min(TOTAL_FECHAS, f + 1))}
          disabled={fechaActual === TOTAL_FECHAS}
          className='w-7 h-7 md:w-8 md:h-8 flex items-center justify-center rounded-lg bg-green-900/40 text-green-400 hover:bg-green-400 hover:text-black transition-all cursor-pointer disabled:opacity-30 text-sm md:text-base'
        >
          ›
        </button>
      </div>
      <div className='space-y-2'>
        {matches.map((match, i) => {
const isLibre = match.visitante_id === null
            const seJugo = match.estado === 'jugado' || (match.goles_local !== null && match.goles_visitante !== null)
            
            // Solo Primera División + jugado => clickeable
            const esPrimera = categoria === 1
            const linkPartido = seJugo && esPrimera
            const matchUrl = linkPartido ? `/partido/${slugify(match.local?.nombre || '')}-vs-${slugify(match.visitante?.nombre || '')}` : null

if (isLibre) {
            return (
              <div
                key={i}
                className='flex items-center justify-center gap-2 py-1 px-2 rounded-lg bg-green-900/30 border border-green-800/50 text-xs'
              >
                <span className='text-green-100 font-medium text-xs sm:text-sm'>{match.local?.nombre}</span>
                <img src={getEscudoPath(match.local.nombre)} alt={match.local.nombre} className='w-4 h-4 sm:w-5 sm:h-5 object-contain shrink-0' />
                <span className='text-green-700 font-semibold text-xs sm:text-sm'>LIBRE</span>
              </div>
            )
          }

          // Clickable row for Primera + played matches
            const onRowClick = linkPartido ? () => { window.location.href = matchUrl } : null

            return (
            <div
              key={i}
              onClick={onRowClick}
              className={'flex flex-col gap-0 py-1 px-2 rounded-lg bg-green-900/30 hover:bg-green-900/50 transition-colors text-xs border border-green-800/50' + (linkPartido ? ' cursor-pointer' : '')}
            >
              {/* Row 1: Fecha / Estado */}
<div className='text-[10px] sm:text-xs text-green-600 font-medium mb-1'>
                {seJugo ? (
                  formatearFechaMostrar(match.dia)
                    ? <span>{formatearFechaMostrar(match.dia)} <span className='text-green-400 font-semibold'>JUGADO</span></span>
                    : <span className='text-green-400 font-semibold'>JUGADO</span>
                ) : match.hora ? (
                  <span>{formatearFechaMostrar(match.dia) || 'A DEFINIR'} - {match.hora.slice(0, 5)}hs</span>
                ) : (
                  formatearFechaMostrar(match.dia) || <span className='font-semibold'>A DEFINIR</span>
                )}
              </div>

              {/* Row 2: Club Local | Score | Club Visitante */}
              <div className='flex items-center gap-1'>
                <div className='flex-1 flex items-center gap-1 justify-end min-w-0'>
                  <span className='text-green-100 font-medium text-xs sm:text-sm text-right'>{match.local?.nombre}</span>
                  {match.local?.nombre && <img src={getEscudoPath(match.local.nombre)} alt={match.local.nombre} className='w-4 h-4 sm:w-5 sm:h-5 object-contain shrink-0' />}
                </div>

                <div className='flex items-center shrink-0 min-w-[36px] justify-center'>
                  {seJugo ? (
                    <><span className='font-bold text-green-300 text-sm sm:text-base tabular-nums'>{match.goles_local}</span><span className='text-green-700 mx-0.5'>–</span><span className='font-bold text-green-300 text-sm sm:text-base tabular-nums'>{match.goles_visitante}</span></>
                  ) : (
                    <span className='text-green-700 font-semibold text-xs sm:text-sm'>vs</span>
                  )}
                </div>

                <div className='flex-1 flex items-center gap-1 min-w-0'>
                  {match.visitante?.nombre && <img src={getEscudoPath(match.visitante.nombre)} alt={match.visitante.nombre} className='w-4 h-4 sm:w-5 sm:h-5 object-contain shrink-0' />}
                  <span className='text-green-100 font-medium text-xs sm:text-sm'>{match.visitante?.nombre}</span>
                </div>
              </div>

              {/* Row 3: Goleadores */}
              {seJugo && (match.goleadoresLocal?.length > 0 || match.goleadoresVisita?.length > 0) && (
                <div className='flex mt-1 gap-2'>
                  <div className='flex-1 text-right text-[9px] sm:text-[10px] text-green-500/80 space-y-0.5 pr-3'>
                    {match.goleadoresLocal?.map((g, i) => <div key={`l${i}`} className='truncate'>{g}</div>)}
                  </div>
                  <div className='flex-1 text-left text-[9px] sm:text-[10px] text-green-500/80 space-y-0.5 pl-3'>
                    {match.goleadoresVisita?.map((g, i) => <div key={`v${i}`} className='truncate'>{g}</div>)}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
