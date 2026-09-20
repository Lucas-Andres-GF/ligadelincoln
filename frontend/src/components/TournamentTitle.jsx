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
    <header className='mb-6'>
      <h1 className='text-3xl font-black uppercase tracking-tight text-green-50'>
        {divisionLabel}
      </h1>
      <p className='mt-1 text-sm font-bold uppercase tracking-wide text-green-400'>
        {isLoading ? 'Cargando torneo…' : selectedTorneo?.nombre || 'Sin torneo seleccionado'}
      </p>
      {error && (
        <p className='mt-2 text-xs font-semibold text-red-300' role='alert'>
          {error}
        </p>
      )}
    </header>
  )
}
