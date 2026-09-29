import { useEffect, useState } from 'react'
import { getEscudoPath, supabase } from '../utils/supabase'
import { cachedQuery } from '../utils/supabaseCached'
import { parseTorneoId } from '../utils/torneoSelection'
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
    <div className={`flex min-w-0 flex-1 items-center gap-2 ${align === 'right' ? 'justify-end text-right' : ''}`}>
      {align === 'left' && (
        <img src={getEscudoPath(club.name)} alt='' className='h-7 w-7 shrink-0 object-contain sm:h-8 sm:w-8' />
      )}
      <span className='min-w-0 text-xs font-bold leading-tight text-green-50 sm:text-sm'>{club.name}</span>
      {align === 'right' && (
        <img src={getEscudoPath(club.name)} alt='' className='h-7 w-7 shrink-0 object-contain sm:h-8 sm:w-8' />
      )}
    </div>
  )
}

export default function TournamentDeciderSeries({ categoria, torneoId }) {
  const [series, setSeries] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function fetchSeries() {
      setSeries([])
      setError(null)

      const scopedTournamentId = parseTorneoId(torneoId)
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
  }, [categoria, torneoId])

  if (error) {
    return (
      <div className='mx-1 mt-5 rounded-md border border-red-300/20 bg-red-950/20 px-3 py-2 text-center text-[11px] font-semibold text-red-200' role='alert'>
        {error}
      </div>
    )
  }

  if (series.length === 0) return null

  const headingId = `tournament-decider-${torneoId}-${categoria}`

  return (
    <section aria-labelledby={headingId} className='relative mx-1 mt-8 overflow-hidden rounded-xl border border-yellow-300/30 bg-[#09290f] shadow-[0_18px_45px_rgba(0,0,0,0.28)]'>
      <div className='absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-yellow-300 to-transparent' aria-hidden='true' />
      <header className='border-b border-yellow-300/15 bg-[linear-gradient(115deg,rgba(250,204,21,0.12),transparent_58%)] px-4 py-4 sm:px-5'>
        <p className='mb-1 text-[9px] font-black uppercase tracking-[0.3em] text-yellow-300/70'>Serie decisiva</p>
        <h2 id={headingId} className='font-serif text-lg font-black tracking-tight text-yellow-100 sm:text-xl'>
          Definición del campeonato
        </h2>
      </header>

      <div className='divide-y divide-yellow-300/15'>
        {series.map((item) => {
          const firstClub = item.clubs[0]
          const secondClub = item.clubs[1]

          return (
            <article key={item.id} className='px-3 py-5 sm:px-5'>
              <div className='mb-4 flex items-center gap-3'>
                <span className='h-px flex-1 bg-yellow-300/20' aria-hidden='true' />
                <h3 className='text-center text-[10px] font-black uppercase tracking-[0.22em] text-yellow-200'>{item.name}</h3>
                <span className='h-px flex-1 bg-yellow-300/20' aria-hidden='true' />
              </div>

              <div className='space-y-2'>
                {item.legs.map((leg) => {
                  const local = { id: Number(leg.local_id), name: Array.isArray(leg.local) ? leg.local[0].nombre : leg.local.nombre }
                  const visitor = { id: Number(leg.visitante_id), name: Array.isArray(leg.visitante) ? leg.visitante[0].nombre : leg.visitante.nombre }

                  return (
                    <div key={leg.id} className='rounded-lg border border-green-700/40 bg-green-950/45 px-3 py-3'>
                      <div className='mb-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[9px] font-bold uppercase tracking-[0.14em]'>
                        <span className='rounded-sm bg-yellow-300 px-1.5 py-0.5 text-[#0a2b10]'>{LEG_LABELS[leg.instancia]}</span>
                        <span className='text-green-400'>{formatDate(leg.dia)}</span>
                      </div>
                      <div className='flex items-center gap-2'>
                        <Team club={local} align='right' />
                        <div className='flex min-w-[66px] items-center justify-center gap-2 font-serif text-xl font-black tabular-nums text-yellow-100' aria-label={`${local.name} ${leg.goles_local}, ${visitor.name} ${leg.goles_visitante}`}>
                          <span>{leg.goles_local}</span>
                          <span className='text-yellow-300/35' aria-hidden='true'>—</span>
                          <span>{leg.goles_visitante}</span>
                        </div>
                        <Team club={visitor} />
                      </div>
                      <p className='mt-2 text-center text-[9px] font-semibold uppercase tracking-wide text-green-500'>
                        <span className='text-green-600'>Cancha · </span>{leg.cancha}
                      </p>
                    </div>
                  )
                })}
              </div>

              <div className='mt-4 grid gap-3 rounded-lg border border-yellow-300/25 bg-yellow-300/[0.06] p-3 sm:grid-cols-[1fr_auto] sm:items-center'>
                <div>
                  <p className='mb-1 text-[9px] font-black uppercase tracking-[0.2em] text-yellow-300/65'>Resultado global</p>
                  <div className='flex items-center gap-2 text-sm font-bold text-green-50'>
                    <span>{firstClub.name}</span>
                    <span className='font-serif text-xl font-black tabular-nums text-yellow-100'>{firstClub.goals} — {secondClub.goals}</span>
                    <span>{secondClub.name}</span>
                  </div>
                </div>
                <div className='flex items-center gap-2 border-t border-yellow-300/15 pt-3 sm:border-l sm:border-t-0 sm:pl-4 sm:pt-0'>
                  <img src={getEscudoPath(item.champion.name)} alt='' className='h-9 w-9 shrink-0 object-contain' />
                  <div>
                    <p className='text-[9px] font-black uppercase tracking-[0.18em] text-yellow-300/65'>Campeón</p>
                    <p className='text-sm font-black text-yellow-100'>{item.champion.name}</p>
                  </div>
                </div>
              </div>

            </article>
          )
        })}
      </div>
    </section>
  )
}
