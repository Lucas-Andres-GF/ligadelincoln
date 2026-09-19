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

export default function TournamentHeader({ divisionLabel = 'Primera División' }) {
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
          clearSelection('El torneo indicado en la URL no es válido. Elegí un torneo de la lista.')
        } else if (!available.some((torneo) => parseTorneoId(torneo.id) === urlTorneoId)) {
          clearSelection('El torneo indicado no está disponible. Elegí un torneo de la lista.')
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
              ? 'No hay un torneo activo configurado. Elegí un torneo para continuar.'
              : 'Hay más de un torneo activo. Elegí cuál querés consultar.',
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

  function selectTorneo(torneoId) {
    const nextTorneoId = parseTorneoId(torneoId)
    if (
      nextTorneoId === null ||
      !torneos.some((torneo) => parseTorneoId(torneo.id) === nextTorneoId)
    ) {
      setSelectedTorneoId(null)
      setError('Seleccioná un torneo válido de la lista.')
      return
    }

    publishSelection(nextTorneoId)
  }

  return (
    <section className='relative overflow-hidden rounded-2xl border border-green-400/25 bg-[#123912] shadow-2xl shadow-black/30'>
      <div className='absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(74,222,128,0.22),transparent_36%),linear-gradient(135deg,rgba(250,204,21,0.10),transparent_48%)]' />
      <div className='absolute -right-12 -top-16 h-36 w-36 rounded-full border border-green-300/20' />
      <div className='relative p-4 sm:p-5'>
        <div className='flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between'>
          <div>
            <p className='text-[10px] font-black uppercase tracking-[0.32em] text-green-300/70'>Torneo seleccionado</p>
            <h1 className='mt-1 text-2xl font-black uppercase tracking-tight text-green-50 sm:text-3xl'>
              {divisionLabel}
            </h1>
            <div className='mt-2 flex flex-wrap items-center gap-2'>
              <span className='rounded-full border border-green-300/30 bg-green-950/50 px-3 py-1 text-xs font-bold uppercase tracking-wider text-green-300'>
                {isLoading ? 'Cargando torneos…' : selectedTorneo?.nombre || 'Sin torneo seleccionado'}
              </span>
              {selectedTorneo?.activo === true && (
                <span className='rounded-full bg-yellow-300 px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.2em] text-green-950 shadow-lg shadow-yellow-300/20'>
                  Actual
                </span>
              )}
            </div>
            {error && (
              <p className='mt-3 max-w-xl text-sm font-semibold text-red-300' role='alert'>
                {error}
              </p>
            )}
          </div>

          <div className='min-w-0 lg:min-w-[320px]'>
            <label className='mb-2 block text-[10px] font-black uppercase tracking-[0.24em] text-green-200/70' htmlFor='torneo-selector'>
              Historial de torneos
            </label>
            <div className='flex flex-col gap-2 sm:flex-row'>
              <select
                id='torneo-selector'
                value={selectedTorneoId ?? ''}
                onChange={(event) => selectTorneo(event.target.value)}
                disabled={isLoading || torneos.length === 0}
                aria-describedby={error ? 'torneo-selection-error' : undefined}
                className='min-h-11 flex-1 rounded-xl border border-green-400/30 bg-green-950/80 px-3 py-2 text-sm font-bold uppercase tracking-wide text-green-50 outline-none ring-0 transition focus:border-yellow-300 focus:shadow-[0_0_0_3px_rgba(250,204,21,0.16)] disabled:cursor-wait disabled:opacity-60'
              >
                <option value='' disabled>
                  {isLoading ? 'Cargando…' : 'Seleccioná un torneo'}
                </option>
                {torneos.map((torneo) => (
                  <option key={torneo.id} value={torneo.id}>
                    {torneo.nombre}{torneo.activo ? ' · actual' : ''}
                  </option>
                ))}
              </select>
              <div className='flex gap-2 overflow-x-auto pb-1 sm:max-w-[220px]'>
                {torneos.map((torneo) => {
                  const isSelected = parseTorneoId(torneo.id) === selectedTorneoId
                  return (
                    <button
                      key={torneo.id}
                      type='button'
                      onClick={() => selectTorneo(torneo.id)}
                      aria-pressed={isSelected}
                      className={`shrink-0 rounded-xl border px-3 py-2 text-[10px] font-black uppercase tracking-widest transition ${
                        isSelected
                          ? 'border-yellow-300 bg-yellow-300 text-green-950 shadow-lg shadow-yellow-300/20'
                          : 'border-green-400/25 bg-green-950/50 text-green-300 hover:border-green-300 hover:bg-green-800/60'
                      }`}
                    >
                      {torneo.activo ? 'Actual' : torneo.temporada || 'Histórico'}
                    </button>
                  )
                })}
              </div>
            </div>
            {error && <span id='torneo-selection-error' className='sr-only'>{error}</span>}
          </div>
        </div>
      </div>
    </section>
  )
}
