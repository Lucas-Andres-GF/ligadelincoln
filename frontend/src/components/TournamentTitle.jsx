import { useEffect, useMemo, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { ACTIVE_TORNEO_ID } from '../config/torneo'
import { getSelectedTorneoId, parseTorneoId } from '../utils/torneoSelection'

const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL
const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY
const supabase = createClient(supabaseUrl, supabaseKey)

function sortTorneos(torneos) {
  return [...torneos].sort((a, b) => {
    if (a.activo !== b.activo) return a.activo ? -1 : 1
    return parseTorneoId(b.id) - parseTorneoId(a.id)
  })
}

function hasTorneoParam() {
  return typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('torneo')
}

export default function TournamentTitle({ divisionLabel = 'Primera División', hidden = false }) {
  const [torneos, setTorneos] = useState([])
  const [selectedTorneoId, setSelectedTorneoId] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  function clearSelection(message) {
    setSelectedTorneoId(null)
    setError(message)
    window.dispatchEvent(
      new CustomEvent('torneo:change', { detail: { torneoId: null } }),
    )
  }

  function publishSelection(torneoId) {
    const canonicalId = parseTorneoId(torneoId)
    if (canonicalId === null) return

    setSelectedTorneoId(canonicalId)
    setError(null)

    const url = new URL(window.location.href)
    url.searchParams.set('torneo', String(canonicalId))
    window.history.replaceState({}, '', url)
    window.dispatchEvent(
      new CustomEvent('torneo:change', { detail: { torneoId: canonicalId } }),
    )
  }

  useEffect(() => {
    let cancelled = false

    async function fetchTorneos() {
      setIsLoading(true)
      setError(null)

      const { data, error: fetchError } = await supabase
        .from('torneos')
        .select('id,nombre,slug,temporada,activo')
        .order('temporada', { ascending: false })
        .order('id', { ascending: false })

      if (cancelled) return

      if (fetchError) {
        console.error('Error fetching torneos:', fetchError)
        setTorneos([])
        clearSelection('No se pudieron cargar los torneos. Intentá nuevamente más tarde.')
        setIsLoading(false)
        return
      }

      const available = sortTorneos(
        (data || []).filter((torneo) => parseTorneoId(torneo.id) !== null),
      )
      setTorneos(available)
      setSelectedTorneoId(null)

      if (hasTorneoParam()) {
        const urlTorneoId = getSelectedTorneoId(null)
        if (urlTorneoId === null) {
          clearSelection('El torneo indicado en la URL no es válido.')
        } else if (!available.some((torneo) => parseTorneoId(torneo.id) === urlTorneoId)) {
          clearSelection('El torneo indicado no está disponible.')
        } else {
          publishSelection(urlTorneoId)
        }
      } else {
        const activeTorneos = available.filter((torneo) => torneo.activo === true)
        const hintedActive =
          ACTIVE_TORNEO_ID === null
            ? null
            : activeTorneos.find(
                (torneo) => parseTorneoId(torneo.id) === ACTIVE_TORNEO_ID,
              )

        if (activeTorneos.length !== 1) {
          clearSelection(
            activeTorneos.length === 0
              ? 'No hay un torneo activo configurado.'
              : 'Hay más de un torneo activo.',
          )
        } else {
          publishSelection(hintedActive?.id ?? activeTorneos[0].id)
        }
      }

      setIsLoading(false)
    }

    fetchTorneos()
    return () => {
      cancelled = true
    }
  }, [])

  const selectedTorneo = useMemo(
    () =>
      torneos.find(
        (torneo) => parseTorneoId(torneo.id) === selectedTorneoId,
      ),
    [torneos, selectedTorneoId],
  )

  if (hidden) return null

  return (
    <header className='relative mb-5 overflow-hidden rounded-2xl border border-green-700/50 bg-[linear-gradient(110deg,#0d3b21_0%,#0a2b18_58%,#102a18_100%)] px-5 py-5 shadow-[0_24px_70px_rgba(0,0,0,0.28)] sm:px-7 sm:py-6'>
      <div className='pointer-events-none absolute -right-12 -top-24 h-64 w-64 rounded-full border-[34px] border-green-400/[0.035]' aria-hidden='true' />
      <div className='pointer-events-none absolute bottom-0 right-[18%] h-full w-px bg-green-300/[0.06]' aria-hidden='true' />
      <div className='relative flex flex-wrap items-end justify-between gap-4'>
        <div>
          <p className='mb-1 font-[var(--font-display)] text-[10px] font-bold uppercase tracking-[0.28em] text-green-500'>Liga de Lincoln · Competencia</p>
          <h1 className='font-[var(--font-display)] text-4xl font-black uppercase leading-none tracking-[0.01em] text-green-50 sm:text-5xl'>
            {divisionLabel}
          </h1>
        </div>
        <div className='min-w-[150px] rounded-xl border border-green-400/15 bg-black/10 px-3.5 py-2.5 text-left sm:text-right'>
          <span className='block text-[9px] font-extrabold uppercase tracking-[0.18em] text-green-600'>Torneo seleccionado</span>
          <strong className='mt-0.5 block font-[var(--font-display)] text-lg font-black uppercase tracking-wide text-yellow-200'>
            {isLoading ? 'Cargando…' : selectedTorneo?.nombre || 'Sin seleccionar'}
          </strong>
        </div>
      </div>
      {error && (
        <p className='relative mt-3 rounded-lg border border-red-300/20 bg-red-950/20 px-3 py-2 text-xs font-semibold text-red-200' role='alert'>
          {error}
        </p>
      )}
    </header>
  )
}
