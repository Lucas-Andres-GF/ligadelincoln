import { useEffect, useState } from 'react'
import { getEscudoPath, supabase } from '../utils/supabase'
import { cachedQuery } from '../utils/supabaseCached'
import { ACTIVE_TORNEO_ID } from '../config/torneo'
import { getSelectedTorneoId, listenToTorneoChange, parseTorneoId } from '../utils/torneoSelection'
import { buildTournamentDeciderSeries } from '../utils/tournamentDecider'

const LEG_LABELS = {
  ida: 'IDA',
  vuelta: 'VUELTA',
  partido_unico: 'PARTIDO ÚNICO',
}

function formatDate(date) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date || '')
  return match ? `${match[3]}/${match[2]}/${match[1]}` : date
}

function Team({ club, align = 'left' }) {
  return (
    <div className={`flex min-w-0 items-center gap-2 ${align === 'right' ? 'justify-end text-right' : ''}`}>
      {align === 'right' && (
        <img src={getEscudoPath(club.name)} alt='' className='order-2 h-7 w-7 shrink-0 object-contain sm:h-9 sm:w-9' />
      )}
      <span className='min-w-0 text-[11px] font-extrabold leading-tight text-green-50 sm:text-sm'>{club.name}</span>
      {align === 'left' && (
        <img src={getEscudoPath(club.name)} alt='' className='h-7 w-7 shrink-0 object-contain sm:h-9 sm:w-9' />
      )}
    </div>
  )
}

export default function TournamentDeciderSeries({ categoria, torneoId }) {
  const [series, setSeries] = useState([])
  const [error, setError] = useState(null)
  const [urlTorneoId, setUrlTorneoId] = useState(() =>
    getSelectedTorneoId(ACTIVE_TORNEO_ID),
  )
  const selectedTorneoId = parseTorneoId(torneoId) ?? urlTorneoId

  useEffect(() => listenToTorneoChange(setUrlTorneoId), [])

  useEffect(() => {
    let cancelled = false

    async function fetchSeries() {
      setSeries([])
      setError(null)

      const scopedTournamentId = parseTorneoId(selectedTorneoId)
      const scopedCategoryId = Number(categoria)
      if (scopedTournamentId === null || !Number.isInteger(scopedCategoryId) || scopedCategoryId <= 0) return

      try {
        const cacheKey = `tournament_deciders_torneo_${scopedTournamentId}_categoria_${scopedCategoryId}`
        const { data, error: queryError } = await cachedQuery(cacheKey, () =>
          supabase
            .from('partidos_definicion')
            .select(`
              id, torneo_id, categoria_id, local_id, visitante_id, campeon_id,
              serie, instancia, orden, goles_local, goles_visitante, dia, cancha, fuente_url,
              local:local_id ( id, nombre ),
              visitante:visitante_id ( id, nombre ),
              campeon:campeon_id ( id, nombre )
            `)
            .eq('torneo_id', scopedTournamentId)
            .eq('categoria_id', scopedCategoryId)
            .order('serie')
            .order('orden'),
        )

        if (cancelled) return
        if (queryError) {
          console.error('Error fetching tournament decider series:', queryError)
          setError('No se pudo cargar la definición del campeonato.')
          return
        }

        setSeries(buildTournamentDeciderSeries(data))
      } catch (queryError) {
        if (cancelled) return
        console.error('Error fetching tournament decider series:', queryError)
        setError('No se pudo cargar la definición del campeonato.')
      }
    }

    fetchSeries()
    return () => {
      cancelled = true
    }
  }, [categoria, selectedTorneoId])

  if (error) {
    return (
      <div className='mx-1 mt-5 rounded-md border border-red-300/20 bg-red-950/20 px-3 py-2 text-center text-[11px] font-semibold text-red-200' role='alert'>
        {error}
      </div>
    )
  }

  if (series.length === 0) return null

  const headingId = `tournament-decider-${selectedTorneoId}-${categoria}`

  return (
    <section aria-labelledby={headingId} className='mt-6 overflow-hidden rounded-xl border border-green-800/70 bg-[#0b2e1a] shadow-2xl'>
      <header className='flex items-center gap-3 border-b border-green-700/60 bg-[#0a2817] px-4 py-3 sm:px-5'>
        <span className='grid h-7 w-7 place-items-center rounded-full border border-yellow-300/35 bg-yellow-300/10 text-sm text-yellow-300' aria-hidden='true'>★</span>
        <div>
          <p className='text-[9px] font-black uppercase tracking-[0.24em] text-green-500'>Instancia decisiva</p>
          <h2 id={headingId} className='text-sm font-black uppercase tracking-wide text-green-50 sm:text-base'>Definición del campeonato</h2>
        </div>
      </header>

      <div className='divide-y divide-green-700/60'>
        {series.map((item) => {
          const firstClub = item.clubs[0]
          const secondClub = item.clubs[1]

          return (
            <article key={item.id}>
              <div className='flex items-center justify-between gap-3 border-b border-green-800/70 bg-green-950/20 px-4 py-2.5 sm:px-5'>
                <h3 className='text-[10px] font-black uppercase tracking-[0.18em] text-green-300'>{item.name}</h3>
                <div className='flex items-center gap-2 text-right'>
                  <span className='hidden text-[9px] font-bold uppercase tracking-[0.14em] text-yellow-300/70 sm:inline'>Campeón</span>
                  <img src={getEscudoPath(item.champion.name)} alt='' className='h-6 w-6 object-contain' />
                  <span className='text-[10px] font-black text-yellow-100 sm:text-xs'>{item.champion.name}</span>
                </div>
              </div>

              <div className='divide-y divide-green-800/55'>
                {item.legs.map((leg) => {
                  const local = { id: Number(leg.local_id), name: Array.isArray(leg.local) ? leg.local[0].nombre : leg.local.nombre }
                  const visitor = { id: Number(leg.visitante_id), name: Array.isArray(leg.visitante) ? leg.visitante[0].nombre : leg.visitante.nombre }

                  return (
                    <div key={leg.id} className='grid min-h-[72px] grid-cols-[58px_minmax(0,1fr)] items-stretch bg-[#0d351e] transition-colors hover:bg-[#103d23] sm:grid-cols-[96px_minmax(0,1fr)_150px]'>
                      <div className='flex flex-col items-center justify-center border-r border-green-700/60 px-2 text-center'>
                        <span className='text-[10px] font-black uppercase tracking-[0.12em] text-green-200'>{LEG_LABELS[leg.instancia]}</span>
                        <span className='mt-1 text-[9px] font-semibold tabular-nums text-green-500'>{formatDate(leg.dia)}</span>
                      </div>
                      <div className='grid grid-cols-[minmax(0,1fr)_54px_minmax(0,1fr)] items-center gap-2 px-3 py-3 sm:grid-cols-[minmax(0,1fr)_74px_minmax(0,1fr)] sm:px-6'>
                        <Team club={local} align='right' />
                        <div className='flex items-center justify-center gap-1.5 text-xl font-black tabular-nums text-white sm:text-2xl' aria-label={`${local.name} ${leg.goles_local}, ${visitor.name} ${leg.goles_visitante}`}>
                          <span>{leg.goles_local}</span>
                          <span className='text-green-600' aria-hidden='true'>–</span>
                          <span>{leg.goles_visitante}</span>
                        </div>
                        <Team club={visitor} />
                      </div>
                      <div className='col-span-2 flex items-center justify-center border-t border-green-800/50 bg-green-950/20 px-3 py-1.5 text-center sm:col-span-1 sm:border-l sm:border-t-0'>
                        <p className='text-[9px] font-semibold uppercase tracking-wide text-green-500'>
                          <span className='text-green-600'>Cancha · </span>{leg.cancha}
                        </p>
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className='flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-t border-yellow-300/20 bg-yellow-300/[0.07] px-4 py-2.5 text-center'>
                <span className='text-[9px] font-black uppercase tracking-[0.18em] text-yellow-300/65'>Resultado global</span>
                <div className='flex items-center gap-2 text-xs font-bold text-green-50 sm:text-sm'>
                  <span>{firstClub.name}</span>
                  <span className='text-base font-black tabular-nums text-yellow-100 sm:text-lg'>{firstClub.goals} – {secondClub.goals}</span>
                  <span>{secondClub.name}</span>
                </div>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
