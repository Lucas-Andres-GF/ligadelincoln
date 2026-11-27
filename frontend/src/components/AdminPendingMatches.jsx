import { useEffect, useState } from 'react'
import { ACTIVE_TORNEO_ID } from '../config/torneo'

const divisions = { 1: 'Primera', 2: 'Séptima', 3: 'Octava', 4: 'Novena', 5: 'Décima' }

export default function AdminPendingMatches({ supabase, lastExecution }) {
  const [matches, setMatches] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      const { data, error } = await supabase.from('partidos')
        .select('id,fecha_id,categoria_id,estado,local:local_id(nombre),visitante:visitante_id(nombre)')
        .eq('torneo_id', ACTIVE_TORNEO_ID).in('estado', ['A reprogramar', 'suspendido'])
        .not('local_id', 'is', null).not('visitante_id', 'is', null)
        .order('categoria_id').order('fecha_id').order('id')
      if (cancelled) return
      setError(error?.message || '')
      if (!error) setMatches(data)
    }
    if (ACTIVE_TORNEO_ID) void load()
    return () => { cancelled = true }
  }, [supabase, lastExecution])

  return (
    <section className='border-y border-green-400/15 p-4 sm:p-6' aria-label='Partidos pendientes'>
      <h3 className='font-[var(--font-display)] text-xl font-black uppercase text-white'>
        Partidos pendientes {matches && !error && <span className='text-green-300'>({matches.length})</span>}
      </h3>
      {error ? <p role='alert'>{error}</p> : matches?.length ? (
        <ul className='mt-3 divide-y divide-green-400/15'>
          {matches.map((match) => (
            <li key={match.id} className='grid gap-1 py-2 text-sm sm:grid-cols-[10rem_1fr_8rem]'>
              <span className='text-green-200'>{divisions[match.categoria_id]} · Fecha {match.fecha_id}</span>
              <strong className='text-white'>{match.local?.nombre} vs. {match.visitante?.nombre}</strong>
              <span className='text-green-100/75'>{match.estado}</span>
            </li>
          ))}
        </ul>
      ) : <p className='mt-2 text-sm text-green-100/75'>{!ACTIVE_TORNEO_ID ? 'Falta configurar el torneo activo.' : matches ? 'No hay partidos suspendidos ni a reprogramar.' : 'Cargando partidos…'}</p>}
    </section>
  )
}
