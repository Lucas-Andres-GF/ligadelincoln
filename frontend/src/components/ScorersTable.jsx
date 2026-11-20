import { useEffect, useState } from 'react'
import { getEscudoPath, supabase } from '../utils/supabase'
import { sortOfficialScorers } from '../utils/scorers'
import { slugify } from '../utils/slugify'
import {
  getSelectedTorneoId,
  listenToTorneoChange,
  parseTorneoId,
  withTorneoParam,
} from '../utils/torneoSelection'

const dateFormatter = new Intl.DateTimeFormat('es-AR', {
  dateStyle: 'short', timeZone: 'America/Argentina/Buenos_Aires',
})

export default function ScorersTable({ categoriaId, torneoId = null }) {
  const [result, setResult] = useState(null)
  const [selectedTorneoId, setSelectedTorneoId] = useState(() => getSelectedTorneoId(torneoId))
  const scopedTorneoId = parseTorneoId(selectedTorneoId)

  useEffect(() => listenToTorneoChange(setSelectedTorneoId), [])

  useEffect(() => {
    if (scopedTorneoId === null) return
    let cancelled = false

    async function fetchScorers() {
      try {
        if (import.meta.env.DEV) {
          const preview = await fetch(`/api/goleadores-preview?torneo=${scopedTorneoId}&categoria=${categoriaId}`)
          if (preview.ok) {
            const report = await preview.json()
            if (!cancelled) setResult({ scopedTorneoId, categoriaId, report })
            return
          }
          if (preview.status !== 404) throw new Error('Error leyendo la vista local')
        }
        const { data, error } = await supabase.rpc('goleadores_actuales', {
          p_torneo_id: scopedTorneoId, p_categoria_id: categoriaId,
        })
        if (error) throw error
        if (!cancelled) setResult({ scopedTorneoId, categoriaId, report: data })
      } catch (error) {
        console.error('Error fetching official scorers:', error)
        if (!cancelled) setResult({ scopedTorneoId, categoriaId, error: true })
      }
    }

    fetchScorers()
    return () => {
      cancelled = true
    }
  }, [scopedTorneoId, categoriaId])

  if (scopedTorneoId === null) {
    return <div className='py-8 text-center text-xs uppercase tracking-widest text-yellow-200' role='status'>Seleccioná un torneo válido para ver los goleadores.</div>
  }

  if (result?.scopedTorneoId !== scopedTorneoId || result.categoriaId !== categoriaId) {
    return <div className='animate-pulse py-8 text-center text-xs uppercase tracking-widest text-green-700'>Cargando goleadores…</div>
  }

  if (result.error) {
    return <div className='py-8 text-center text-xs font-semibold text-red-300' role='alert'>No se pudo cargar la tabla de goleadores.</div>
  }

  const scorers = sortOfficialScorers(result.report?.filas ?? [])
  if (scorers.length === 0) {
    return <div className='py-8 text-center text-xs text-green-200/70'>Todavía no hay una tabla oficial disponible para este torneo y división.</div>
  }

  return <>
    <p className='mb-2 text-xs font-semibold text-green-200/75'>
      Actualización de la Liga · <time dateTime={result.report.emitido_en}>{dateFormatter.format(new Date(result.report.emitido_en))}</time>
    </p>
    <div role='region' aria-label='Listado de goleadores' tabIndex={0} className='h-[23rem] overflow-y-auto overscroll-y-contain rounded-xl border border-green-800/55 bg-green-950/20 [scrollbar-gutter:stable] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-yellow-300 sm:h-96'>
      <div className='sticky top-0 z-10 grid grid-cols-[minmax(0,1fr)_58px] border-b border-green-800/60 bg-[#092716] px-3 py-2.5 font-[var(--font-display)] text-[10px] font-bold uppercase tracking-[0.14em] text-green-600 sm:grid-cols-[minmax(0,1fr)_72px] sm:px-4'>
        <span>Jugador / club</span>
        <span className='text-center'>Goles</span>
      </div>
      <ol id='scorers-ranking' className='divide-y divide-green-800/45'>
        {scorers.map((scorer) => (
          <li
            key={`${scorer.club_id}-${scorer.nombre}`}
            className='grid grid-cols-[minmax(0,1fr)_58px] items-center px-3 py-2.5 transition-colors hover:bg-green-400/[0.055] sm:grid-cols-[minmax(0,1fr)_72px] sm:px-4'
          >
            <div className='flex min-w-0 items-center gap-3'>
              <a
                href={withTorneoParam(`/club/${slugify(scorer.club)}?categoria=${categoriaId}`, selectedTorneoId)}
                className='shrink-0 transition-transform hover:scale-105'
                aria-label={`Ver perfil de ${scorer.club}`}
              >
                <img src={getEscudoPath(scorer.club)} alt='' className='h-8 w-8 object-contain drop-shadow-[0_5px_8px_rgba(0,0,0,0.28)] sm:h-9 sm:w-9' />
              </a>
              <div className='min-w-0'>
                <div className='break-words font-[var(--font-display)] text-sm font-black uppercase tracking-wide text-green-50 sm:text-base'>{scorer.nombre}</div>
                <a href={withTorneoParam(`/club/${slugify(scorer.club)}?categoria=${categoriaId}`, selectedTorneoId)} className='block truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-green-600 transition hover:text-yellow-300'>{scorer.club}</a>
              </div>
            </div>
            <div className='text-center font-[var(--font-display)] text-2xl font-black tabular-nums text-yellow-100'>{scorer.goles}</div>
          </li>
        ))}
      </ol>
    </div>
  </>
}
