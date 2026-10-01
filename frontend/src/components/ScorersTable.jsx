import { useEffect, useState } from 'react'
import { getEscudoPath, supabase } from '../utils/supabase'
import { cachedQuery } from '../utils/supabaseCached'
import { buildScorersTable } from '../utils/scorers'
import { slugify } from '../utils/slugify'
import {
  getSelectedTorneoId,
  listenToTorneoChange,
  parseTorneoId,
  withTorneoParam,
} from '../utils/torneoSelection'

function relationValue(value) {
  return Array.isArray(value) ? value[0] : value
}

function buildClubMap(matches) {
  const clubs = {}
  for (const match of matches || []) {
    const local = relationValue(match.local)
    const visitor = relationValue(match.visitante)
    if (local?.id && local?.nombre) clubs[Number(local.id)] = local.nombre
    if (visitor?.id && visitor?.nombre) clubs[Number(visitor.id)] = visitor.nombre
  }
  return clubs
}

export default function ScorersTable({ torneoId = null }) {
  const [scorers, setScorers] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [selectedTorneoId, setSelectedTorneoId] = useState(() => getSelectedTorneoId(torneoId))

  useEffect(() => listenToTorneoChange(setSelectedTorneoId), [])

  useEffect(() => {
    let cancelled = false

    async function fetchScorers() {
      setScorers([])
      setError(null)
      setIsExpanded(false)
      const scopedTorneoId = parseTorneoId(selectedTorneoId)
      if (scopedTorneoId === null) {
        setIsLoading(false)
        return
      }

      setIsLoading(true)
      const cacheKey = `scorers_torneo_${scopedTorneoId}_categoria_1`
      const { data: matches, error: matchesError } = await cachedQuery(cacheKey, () =>
        supabase
          .from('partidos')
          .select(`
            id,
            local:local_id ( id, nombre ),
            visitante:visitante_id ( id, nombre )
          `)
          .eq('torneo_id', scopedTorneoId)
          .eq('categoria_id', 1),
      )

      if (cancelled) return
      if (matchesError) {
        console.error('Error fetching scorer matches:', matchesError)
        setError('No se pudo cargar la tabla de goleadores.')
        setIsLoading(false)
        return
      }

      const matchIds = (matches || []).map((match) => match.id).filter(Boolean)
      if (matchIds.length === 0) {
        setIsLoading(false)
        return
      }

      const { data: lineups, error: lineupsError } = await supabase
        .from('alineaciones')
        .select('partido_id, equipo_id, nombre, goleo')
        .in('partido_id', matchIds)
        .gt('goleo', 0)

      if (cancelled) return
      if (lineupsError) {
        console.error('Error fetching scorers:', lineupsError)
        setError('No se pudo cargar la tabla de goleadores.')
      } else {
        setScorers(buildScorersTable(lineups, buildClubMap(matches)))
      }
      setIsLoading(false)
    }

    fetchScorers()
    return () => {
      cancelled = true
    }
  }, [selectedTorneoId])

  if (parseTorneoId(selectedTorneoId) === null) {
    return <div className='py-8 text-center text-xs uppercase tracking-widest text-yellow-200' role='status'>Seleccioná un torneo válido para ver los goleadores.</div>
  }

  if (isLoading) {
    return <div className='animate-pulse py-8 text-center text-xs uppercase tracking-widest text-green-700'>Cargando goleadores…</div>
  }

  if (error) {
    return <div className='py-8 text-center text-xs font-semibold text-red-300' role='alert'>{error}</div>
  }

  if (scorers.length === 0) {
    return <div className='py-8 text-center text-xs uppercase tracking-widest text-green-700'>Todavía no hay goles registrados.</div>
  }

  const visibleScorers = isExpanded ? scorers : scorers.slice(0, 5)
  const canExpand = scorers.length > 5

  return (
    <div className='overflow-hidden rounded-xl border border-green-800/55 bg-green-950/20'>
      <div className='grid grid-cols-[minmax(0,1fr)_58px] border-b border-green-800/60 bg-[#092716] px-3 py-2.5 font-[var(--font-display)] text-[10px] font-bold uppercase tracking-[0.14em] text-green-600 sm:grid-cols-[minmax(0,1fr)_72px] sm:px-4'>
        <span>Jugador / club</span>
        <span className='text-center'>Goles</span>
      </div>
      <ol id='scorers-ranking' className='divide-y divide-green-800/45'>
        {visibleScorers.map((scorer) => (
          <li
            key={`${scorer.teamId}-${scorer.name}`}
            className='grid grid-cols-[minmax(0,1fr)_58px] items-center px-3 py-2.5 transition-colors hover:bg-green-400/[0.055] sm:grid-cols-[minmax(0,1fr)_72px] sm:px-4'
          >
            <div className='flex min-w-0 items-center gap-3'>
              <a
                href={withTorneoParam(`/club/${slugify(scorer.clubName)}?categoria=1`, selectedTorneoId)}
                className='shrink-0 transition-transform hover:scale-105'
                aria-label={`Ver perfil de ${scorer.clubName}`}
              >
                <img src={getEscudoPath(scorer.clubName)} alt='' className='h-8 w-8 object-contain drop-shadow-[0_5px_8px_rgba(0,0,0,0.28)] sm:h-9 sm:w-9' />
              </a>
              <div className='min-w-0'>
                <div className='truncate font-[var(--font-display)] text-sm font-black uppercase tracking-wide text-green-50 sm:text-base'>{scorer.name}</div>
                <a href={withTorneoParam(`/club/${slugify(scorer.clubName)}?categoria=1`, selectedTorneoId)} className='block truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-green-600 transition hover:text-yellow-300'>{scorer.clubName}</a>
              </div>
            </div>
            <div className='text-center font-[var(--font-display)] text-2xl font-black tabular-nums text-yellow-100'>{scorer.goals}</div>
          </li>
        ))}
      </ol>
      {canExpand && (
        <button
          type='button'
          onClick={() => setIsExpanded((expanded) => !expanded)}
          aria-expanded={isExpanded}
          aria-controls='scorers-ranking'
          className='group flex w-full items-center justify-center gap-1.5 border-t border-green-700/70 bg-[#082a17] px-4 py-2.5 font-[var(--font-display)] text-[10px] font-black uppercase tracking-[0.16em] text-green-400 transition-colors hover:bg-green-400/10 hover:text-yellow-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-yellow-300'
        >
          {isExpanded ? 'Ver menos' : 'Ver más'}
          <svg
            viewBox='0 0 20 20'
            fill='none'
            stroke='currentColor'
            strokeWidth='2.5'
            className={`h-3 w-3 transition-transform duration-200 ${isExpanded ? 'rotate-180' : 'group-hover:translate-y-0.5'}`}
            aria-hidden='true'
          >
            <path d='m5 7.5 5 5 5-5' strokeLinecap='round' strokeLinejoin='round' />
          </svg>
        </button>
      )}
    </div>
  )
}
