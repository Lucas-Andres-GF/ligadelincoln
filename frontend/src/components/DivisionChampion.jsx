import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { ACTIVE_TORNEO_ID } from '../config/torneo'
import { fetchDivisionChampions } from '../utils/divisionChampions'
import { getEscudoPath } from '../utils/supabase'
import { getSelectedTorneoId, listenToTorneoChange } from '../utils/torneoSelection'
import './DivisionChampion.css'

const confettiColors = ['#ffdf24', '#55dc82', '#fff3ac', '#e2ffe9']

function ChampionConfetti() {
  const [visible, setVisible] = useState(true)
  useEffect(() => {
    const timeout = window.setTimeout(() => setVisible(false), 4000)
    return () => window.clearTimeout(timeout)
  }, [])

  return visible && createPortal(
    <div aria-hidden='true' className='champion-confetti'>
      {Array.from({ length: 96 }, (_, index) => (
        <i key={index} style={{
          left: index % 2 ? '100%' : '0%',
          top: `${44 + (index * 11) % 32}%`,
          backgroundColor: confettiColors[index % confettiColors.length],
          '--drift': `${(index % 2 ? -1 : 1) * (15 + (index * 17) % 74)}vw`,
          '--rise': `-${29 + (index * 19) % 43}vh`,
          '--spin': `${(index % 2 ? -1 : 1) * (200 + (index * 31) % 360)}deg`,
          animationDelay: `${(index * 37) % 650}ms`,
        }} />
      ))}
    </div>,
    document.body,
  )
}

export default function DivisionChampion({ categoriaId }) {
  const [torneoId, setTorneoId] = useState(() => getSelectedTorneoId(ACTIVE_TORNEO_ID))
  const [result, setResult] = useState(null)

  useEffect(() => listenToTorneoChange(setTorneoId), [])
  useEffect(() => {
    if (!torneoId) return
    let cancelled = false

    async function loadChampion() {
      try {
        const rows = await fetchDivisionChampions({ torneoId, categoriaId })
        if (!cancelled) setResult({ torneoId, categoriaId, rows })
      } catch (error) {
        if (!cancelled) console.error('Error fetching division champion:', error)
      }
    }

    void loadChampion()
    return () => { cancelled = true }
  }, [torneoId, categoriaId])

  if (result?.torneoId !== torneoId || result?.categoriaId !== categoriaId) return null
  const champions = [...new Map(result.rows.map((row) => [row.club_id, row])).values()]
  if (champions.length === 0) return null

  const [first] = champions
  const calculated = first.tipo === 'matematico'
  const title = champions.length > 1 ? 'Campeones compartidos' : calculated ? 'Campeón matemático' : 'Campeón'

  return (
    <section id='campeon' aria-labelledby='campeon-title' className='relative isolate mb-5 flex flex-wrap items-center gap-x-6 gap-y-3 overflow-hidden rounded-2xl border border-yellow-300/30 bg-[linear-gradient(110deg,#24371a,#0b2e1a_66%)] px-4 py-4 shadow-lg sm:px-6'>
      {Number(torneoId) === Number(ACTIVE_TORNEO_ID) && <ChampionConfetti />}
      <div className='flex shrink-0 -space-x-1' aria-hidden='true'>
        {champions.map((club) => (
          <img key={club.club_id} src={getEscudoPath(club.club_nombre)} alt='' className='size-12 rounded-xl border border-yellow-300/25 bg-green-950/70 object-contain p-1.5 sm:size-14' />
        ))}
      </div>
      <div className='min-w-0 flex-1'>
        <p className='text-[10px] font-black uppercase tracking-[0.22em] text-yellow-300'>{title}</p>
        <h2 id='campeon-title' className='mt-0.5 font-[var(--font-display)] text-xl font-black uppercase leading-tight tracking-wide text-green-50 sm:text-2xl'>
          {champions.map((club) => club.club_nombre).join(' y ')}
        </h2>
        <p className='mt-1 text-xs text-green-100/75'>{first.torneo_nombre}</p>
      </div>
      {calculated && (
        <p className='w-full border-t border-yellow-300/15 pt-2 text-xs text-green-100/80 sm:w-auto sm:border-0 sm:pt-0'>
          <strong className='text-yellow-200'>{first.puntos} pts</strong> · Máximo de un rival: {first.maximo_rival} pts
        </p>
      )}
    </section>
  )
}
