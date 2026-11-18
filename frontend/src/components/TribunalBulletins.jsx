import { useEffect, useState } from 'react'
import { supabase } from '../utils/supabase'

const divisionByCategory = {
  1: 'PRIMERA',
  2: 'SEPTIMA',
  3: 'OCTAVA',
  4: 'NOVENA',
  5: 'DECIMA',
}
const selectClass = 'rounded-lg border border-green-700/70 bg-[#092716] px-3 py-2 text-sm text-green-50'
const dateFormat = new Intl.DateTimeFormat('es-AR', { dateStyle: 'long', timeZone: 'UTC' })

export default function TribunalBulletins({ categoriaId }) {
  const [bulletins, setBulletins] = useState(null)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(false)
  const division = divisionByCategory[categoriaId]

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        let data
        if (import.meta.env.DEV) {
          const response = await fetch('/api/boletines-preview', { signal: controller.signal })
          if (response.ok) {
            data = await response.json()
          } else if (response.status !== 404) {
            throw new Error('No se pudo leer la copia local.')
          }
        }
        if (!data) {
          const result = await supabase.rpc('boletines_tribunal', { p_division: division }).abortSignal(controller.signal)
          if (result.error) throw result.error
          data = result.data
        }
        if (controller.signal.aborted) return
        setBulletins(data)
        setSelected(data[0]?.numero ?? null)
      } catch {
        if (!controller.signal.aborted) setError(true)
      }
    }
    void load()
    return () => controller.abort()
  }, [division])

  const bulletin = bulletins?.find((item) => item.numero === selected)
  const rows = bulletin?.resoluciones.filter((row) => row.division === division) ?? []

  return (
    <section id='tribunal' aria-labelledby='tribunal-title' className='flex max-h-[var(--discipline-card-height)] min-w-0 scroll-mt-24 flex-col overflow-hidden rounded-2xl border border-green-800/60 bg-[#0b2e1a] @min-[720px]:h-[var(--discipline-card-height)]'>
      <header className='shrink-0 border-b border-green-800/60 bg-[#092716] px-4 py-4 sm:px-5'>
        <h2 id='tribunal-title' className='font-[var(--font-display)] text-xl font-black uppercase tracking-wide text-green-50'>Resoluciones del Tribunal</h2>
      </header>
      <div className='flex min-h-0 flex-1 flex-col gap-3 p-3 sm:p-4'>
        {bulletin ? (
          <>
            <label className='grid w-full shrink-0 gap-1 text-xs text-green-100 sm:max-w-xs'>
              Boletín
              <select className={selectClass} value={selected} onChange={(e) => setSelected(Number(e.target.value))}>
                {bulletins.map((item) => <option key={item.numero} value={item.numero}>{dateFormat.format(new Date(item.fecha))}</option>)}
              </select>
            </label>
            <div role='region' aria-label='Listado de resoluciones' tabIndex={0} className='min-h-0 overflow-y-auto overscroll-y-contain rounded-xl border border-green-800/60 text-green-50 [scrollbar-gutter:stable] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-yellow-300'>
              {rows.length ? (
                <ul className='divide-y divide-green-800/50'>
                  {rows.map((row, index) => (
                    <li key={index} className='flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 even:bg-green-950/30'>
                      <div>
                        <p className='text-sm font-bold'>{row.nombre}</p>
                        <p className='text-xs text-green-200/80'>{row.club} · {row.funcion}</p>
                      </div>
                      <span className='rounded-md bg-red-400/15 px-2 py-1 text-xs font-bold text-red-200'>{row.sancion}</span>
                    </li>
                  ))}
                </ul>
              ) : <p role='status' className='p-3 text-sm'>Este boletín no incluye resoluciones para esta división.</p>}
            </div>
          </>
        ) : (
          <p role='status' className='text-sm text-green-100'>
            {error ? 'No se pudieron cargar los boletines.' : bulletins ? 'Todavía no hay boletines publicados.' : 'Cargando boletines…'}
          </p>
        )}
      </div>
    </section>
  )
}
