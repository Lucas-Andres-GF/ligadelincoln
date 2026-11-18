import { useEffect, useState } from 'react'
import { getEscudoPath, supabase } from '../utils/supabase'
import { getSelectedTorneoId, listenToTorneoChange } from '../utils/torneoSelection'
import RankingToggle from './RankingToggle'

const dateFormatter = new Intl.DateTimeFormat('es-AR', {
  dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Argentina/Buenos_Aires',
})
const normalize = (value) => value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
const controlClass = 'min-w-0 rounded-lg border border-green-700/70 bg-[#092716] px-3 py-2 text-sm text-green-50 focus-visible:outline-2 focus-visible:outline-yellow-300'

export default function YellowCards() {
  const [torneo, setTorneo] = useState(() => getSelectedTorneoId())
  const [result, setResult] = useState(null)
  const [role, setRole] = useState('jugador')
  const [club, setClub] = useState('')
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState(false)

  useEffect(() => listenToTorneoChange(setTorneo), [])
  useEffect(() => {
    if (!torneo) return
    let cancelled = false
    async function load() {
      try {
        if (import.meta.env.DEV) {
          const response = await fetch(`/api/amarillas-preview?torneo=${torneo}`)
          if (response.ok) {
            const report = await response.json()
            if (!cancelled) setResult({ torneo, report, preview: true })
            return
          }
          if (response.status !== 404) throw new Error('Error leyendo la vista local')
        }
        const { data, error } = await supabase.rpc('amarillas_actuales', { p_torneo_id: torneo })
        if (error) throw error
        if (!cancelled) setResult({ torneo, report: data })
      } catch {
        if (!cancelled) setResult({ torneo, error: true })
      }
    }
    void load()
    return () => { cancelled = true }
  }, [torneo])

  const current = result?.torneo === torneo ? result : null
  const report = current?.report
  const all = report?.filas ?? []
  const clubs = [...new Set(all.map((row) => row.club))].sort((a, b) => a.localeCompare(b, 'es'))
  const searching = Boolean(query.trim() || club)
  const matching = all.filter((row) => row.rol === role && (!club || row.club === club)
    && normalize(row.nombre).includes(normalize(query.trim())))
    .sort((a, b) => b.amarillas - a.amarillas || a.club.localeCompare(b.club, 'es')
      || a.nombre.localeCompare(b.nombre, 'es'))
  const highlighted = matching.filter((row) => row.amarillas >= 4)
  const canExpand = !searching && role === 'jugador' && highlighted.length > 0 && highlighted.length < matching.length
  const visible = canExpand && !expanded ? highlighted : matching
  const groups = new Map()
  for (const row of visible) {
    const key = `${row.amarillas}-${row.club_id}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(row)
  }
  const toggle = {
    expanded,
    controls: 'yellow-cards-ranking',
    onToggle: () => setExpanded((value) => !value),
    moreLabel: `Ver más (${matching.length})`,
  }

  return (
    <section id='amarillas' aria-labelledby='amarillas-title' className='mt-6 scroll-mt-24 overflow-hidden rounded-2xl border border-green-800/60 bg-[#0b2e1a]'>
      <header className='border-b border-green-800/60 bg-[#092716] px-4 py-4 sm:px-5'>
        <p className='text-[10px] font-bold uppercase tracking-[0.24em] text-yellow-300'>Disciplina</p>
        <h2 id='amarillas-title' className='font-[var(--font-display)] text-xl font-black uppercase tracking-wide text-green-50'>Amarillas acumuladas</h2>
        {report && <p className='mt-1 text-xs text-green-200/75'>{current.preview ? 'Vista local · ' : ''}Informe del <time dateTime={report.emitido_en}>{dateFormatter.format(new Date(report.emitido_en))}</time></p>}
      </header>
      {!report ? (
        <p role='status' className='p-4 text-sm text-green-100'>
          {!torneo || current ? (current?.error ? 'No se pudo cargar el informe.' : 'Todavía no hay un informe para este torneo.') : 'Cargando informe…'}
        </p>
      ) : (
        <div className='space-y-3 p-3 sm:p-4'>
          <div className='grid gap-2 sm:grid-cols-[1fr_auto_auto]'>
            <input aria-label='Buscar por nombre' placeholder='Buscar por nombre' value={query} onChange={(event) => setQuery(event.target.value)} className={controlClass} />
            <select aria-label='Filtrar por club' value={club} onChange={(event) => setClub(event.target.value)} className={controlClass}>
              <option value=''>Todos los clubes</option>
              {clubs.map((name) => <option key={name}>{name}</option>)}
            </select>
            <select aria-label='Tipo de participante' value={role} onChange={(event) => setRole(event.target.value)} className={controlClass}>
              <option value='jugador'>Jugadores</option>
              <option value='cuerpo_tecnico'>Cuerpo técnico</option>
            </select>
          </div>
          {role === 'jugador' && <p className='text-xs text-green-100/80'>Cinco amarillas alcanzan el umbral de una fecha de suspensión. Consultá al Tribunal para confirmar su vigencia.</p>}
          {visible.length ? (
            <div className='overflow-hidden rounded-xl border border-green-800/60'>
              {canExpand && <RankingToggle {...toggle} className='border-b border-green-700/70' />}
              <table id='yellow-cards-ranking' className='w-full text-left text-sm text-green-50'>
                <thead className='bg-[#092716] text-xs text-green-200'>
                  <tr><th scope='col' className='px-3 py-2'>Nombre y club</th><th scope='col' className='px-3 py-2 text-right'>Amarillas</th></tr>
                </thead>
                {[...groups].map(([key, rows]) => {
                  const { club: clubName, amarillas } = rows[0]
                  return (
                    <tbody key={key} className='divide-y divide-green-800/50 border-t border-green-700/60'>
                      <tr className='bg-[#092716]'>
                        <th scope='rowgroup' className='px-3 py-2'>
                          <span className='flex items-center gap-2 text-xs font-bold text-green-100'>
                            <img src={getEscudoPath(clubName)} alt='' width='22' height='22' className='h-[22px] w-[22px] shrink-0 object-contain' />
                            {clubName}
                          </span>
                        </th>
                        <td className='px-3 py-2 text-right'>
                          <span className={`inline-flex min-w-7 justify-center rounded px-1.5 py-0.5 font-black tabular-nums ${amarillas >= 5 ? 'bg-red-400/15 text-red-200' : amarillas === 4 ? 'bg-yellow-300/15 text-yellow-200' : 'bg-green-950 text-green-100'}`}>{amarillas}</span>
                          {role === 'jugador' && amarillas === 4 && <span className='mt-0.5 block whitespace-nowrap text-[10px] text-yellow-200'>Al límite</span>}
                        </td>
                      </tr>
                      {rows.map((row, index) => (
                        <tr key={`${row.nombre}-${index}`} className='even:bg-green-950/30'>
                          <td colSpan={2} className='py-2 pl-11 pr-3 font-semibold'>{row.nombre}</td>
                        </tr>
                      ))}
                    </tbody>
                  )
                })}
              </table>
              {canExpand && <RankingToggle {...toggle} className='border-t border-green-700/70' />}
            </div>
          ) : <p role='status' className='py-3 text-sm text-green-100'>Sin coincidencias para esos filtros.</p>}
        </div>
      )}
    </section>
  )
}
