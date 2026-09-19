import { useEffect, useMemo, useState } from 'react'
import { supabase, getEscudoPath } from '../utils/supabase'

const CATEGORIES = [
  { id: 1, label: 'Primera', path: '/primera' },
  { id: 2, label: 'Séptima', path: '/septima' },
  { id: 3, label: 'Octava', path: '/octava' },
  { id: 4, label: 'Novena', path: '/novena' },
  { id: 5, label: 'Décima', path: '/decima' },
]

function relationValue(value) {
  return Array.isArray(value) ? value[0] : value
}

function torneoHref(path, torneoId) {
  return `${path}?torneo=${encodeURIComponent(torneoId)}#fixture`
}

export default function HistoricalChampions({ categoriaId }) {
  const normalizedCategoriaId = Number(categoriaId) || null
  const [torneos, setTorneos] = useState([])
  const [palmares, setPalmares] = useState([])
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    let cancelled = false

    async function fetchHistory() {
      setStatus('loading')

      let palmaresQuery = supabase
        .from('palmares')
        .select('id,nombre,temporada,club_id,torneo_id,categoria_id,club:club_id(nombre)')
        .order('torneo_id', { ascending: false })

      if (normalizedCategoriaId) {
        palmaresQuery = palmaresQuery.eq('categoria_id', normalizedCategoriaId)
      }

      const [torneosResult, palmaresResult] = await Promise.all([
        supabase
          .from('torneos')
          .select('id,nombre,temporada,activo')
          .order('temporada', { ascending: false })
          .order('id', { ascending: false }),
        palmaresQuery,
      ])

      if (cancelled) return

      if (torneosResult.error || palmaresResult.error) {
        console.error('Error fetching historical champions:', torneosResult.error || palmaresResult.error)
        setTorneos([])
        setPalmares([])
        setStatus('error')
        return
      }

      setTorneos(torneosResult.data || [])
      setPalmares(palmaresResult.data || [])
      setStatus('ready')
    }

    fetchHistory()
    return () => {
      cancelled = true
    }
  }, [normalizedCategoriaId])

  const categories = useMemo(() => {
    if (!normalizedCategoriaId) return CATEGORIES
    return CATEGORIES.filter((category) => category.id === normalizedCategoriaId)
  }, [normalizedCategoriaId])

  const championsByKey = useMemo(() => {
    const result = new Map()
    for (const row of palmares) {
      const key = `${row.torneo_id}:${row.categoria_id}`
      if (!result.has(key)) result.set(key, row)
    }
    return result
  }, [palmares])

  if (status === 'loading') {
    return (
      <div className='py-8 text-center text-[10px] font-bold uppercase tracking-[0.24em] text-green-600' aria-live='polite'>
        Cargando historial…
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className='rounded-lg border border-yellow-300/20 bg-yellow-300/5 px-4 py-5 text-center text-xs text-yellow-100' role='status'>
        No se pudo cargar el historial en este momento.
      </div>
    )
  }

  if (torneos.length === 0) {
    return (
      <div className='py-8 text-center text-xs text-green-600' role='status'>
        Todavía no hay torneos históricos cargados.
      </div>
    )
  }

  if (categories.length === 0) {
    return (
      <div className='py-8 text-center text-xs text-green-600' role='status'>
        La categoría solicitada no está disponible.
      </div>
    )
  }

  return (
    <div className='space-y-4'>
      {categories.map((category) => (
        <section key={category.id} aria-labelledby={`historial-categoria-${category.id}`} className='overflow-hidden rounded-xl border border-green-400/15 bg-green-950/20'>
          <div className='flex items-center justify-between border-b border-green-400/10 bg-green-950/30 px-3 py-2'>
            <h3 id={`historial-categoria-${category.id}`} className='text-[11px] font-black uppercase tracking-[0.2em] text-green-300'>
              {category.label}
            </h3>
            <span className='text-[9px] font-bold uppercase tracking-widest text-green-700'>Campeones oficiales</span>
          </div>

          <div className='divide-y divide-green-400/10'>
            {torneos.map((torneo) => {
              const champion = championsByKey.get(`${torneo.id}:${category.id}`)
              const club = relationValue(champion?.club)
              const clubName = club?.nombre

              return (
                <article key={`${torneo.id}:${category.id}`} className='grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-3 py-2.5 transition-colors hover:bg-green-400/[0.04] sm:grid-cols-[minmax(150px,0.75fr)_minmax(180px,1fr)_auto]'>
                  <div className='min-w-0'>
                    <p className='truncate text-xs font-black uppercase text-green-50'>{torneo.nombre}</p>
                    <p className='mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-green-600'>
                      {champion?.temporada || torneo.temporada || 'Temporada sin informar'}
                    </p>
                  </div>

                  <div className='col-span-2 flex min-w-0 items-center gap-2 sm:col-span-1 sm:row-auto'>
                    {clubName ? (
                      <>
                        <img
                          src={getEscudoPath(clubName)}
                          alt={`Escudo de ${clubName}`}
                          className='h-7 w-7 shrink-0 object-contain'
                          loading='lazy'
                        />
                        <div className='min-w-0'>
                          <p className='truncate text-xs font-bold text-green-100'>{clubName}</p>
                          {champion?.nombre && (
                            <p className='truncate text-[9px] font-bold uppercase tracking-wide text-yellow-300/80'>{champion.nombre}</p>
                          )}
                        </div>
                      </>
                    ) : (
                      <p className='text-[10px] font-semibold uppercase tracking-wide text-green-700'>Sin campeón cargado</p>
                    )}
                  </div>

                  <a
                    href={torneoHref(category.path, torneo.id)}
                    className='row-start-1 rounded-md border border-green-400/20 px-2 py-1 text-[9px] font-black uppercase tracking-wide text-green-300 transition hover:border-yellow-300/50 hover:text-yellow-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-yellow-300 sm:row-auto'
                    aria-label={`Ver ${torneo.nombre} de ${category.label}`}
                  >
                    Ver torneo
                  </a>
                </article>
              )
            })}
          </div>
        </section>
      ))}
    </div>
  )
}
