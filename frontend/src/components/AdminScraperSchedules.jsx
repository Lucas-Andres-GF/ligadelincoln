import { useCallback, useEffect, useState } from 'react'
import { ACTIVE_TORNEO_ID } from '../config/torneo'

const week = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
const frequencies = [5, 10, 15, 20, 30, 60]
const inputClass = 'w-full min-w-0 rounded-lg border border-green-400/25 bg-[#0a2816] px-3 py-2 text-sm text-white focus-visible:outline-2 focus-visible:outline-green-300'

function isScheduleCurrent(item, now) {
  if (!item.run_date) return true
  const start = item.start_time.slice(0, 5)
  const end = item.end_time.slice(0, 5)
  const endOnStartDate = Date.parse(`${item.run_date}T${end}:00-03:00`)
  const overnight = end < start ? 24 * 60 * 60_000 : 0
  // Mint can pick up the final run throughout its scheduled minute.
  return now < endOnStartDate + overnight + 60_000
}

function formatScheduleWindow(item) {
  const start = item.start_time.slice(0, 5)
  const end = item.end_time.slice(0, 5)
  const day = item.run_date ? item.run_date.split('-').reverse().join('/') : week[item.weekday - 1]
  if (end >= start) return `${day} · ${start}–${end}`

  let nextDay = week[item.weekday % 7]
  if (item.run_date) {
    const date = new Date(`${item.run_date}T00:00:00Z`)
    date.setUTCDate(date.getUTCDate() + 1)
    nextDay = date.toISOString().slice(0, 10).split('-').reverse().join('/')
  }
  return `${day} ${start} → ${nextDay} ${end}`
}

function Field({ label, children }) {
  return (
    <label className='grid min-w-0 gap-1 text-xs font-semibold text-green-100'>
      {label}
      {children}
    </label>
  )
}

export default function AdminScraperSchedules({ supabase, operations, categories, formatDateTime, statuses }) {
  const [items, setItems] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [busy, setBusy] = useState(false)
  const [scraper, setScraper] = useState('resultados')
  const [kind, setKind] = useState('date')
  const [start, setStart] = useState('19:00')
  const [end, setEnd] = useState('23:00')
  const endsNextDay = Boolean(start && end && end < start)

  const refresh = useCallback(async () => {
    const { data, error } = await supabase.rpc('list_scraper_schedules')
    setLoadError(error?.code === 'PGRST202'
      ? 'Falta instalar el programador en Supabase.'
      : error?.message || '')
    if (!error) {
      const now = Date.now()
      setItems((data ?? []).filter((item) => isScheduleCurrent(item, now)))
    }
  }, [supabase])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(refresh, 8000)
    return () => window.clearInterval(timer)
  }, [refresh])

  async function save(event) {
    event.preventDefault()
    const form = event.currentTarget
    const fields = new FormData(form)
    setActionError('')
    if (fields.get('confirm') !== 'ESCRIBIR') {
      setActionError('Para guardar una programación, escribí ESCRIBIR.')
      return
    }
    const payload = {
      scraper,
      torneo_id: Number(fields.get('torneo_id')),
      fecha: fields.has('fecha') ? Number(fields.get('fecha')) : null,
      categoria: fields.get('categoria') || null,
      weekday: kind === 'weekly' ? Number(fields.get('weekday')) : null,
      run_date: kind === 'date' ? fields.get('run_date') : null,
      start_time: fields.get('start_time'),
      end_time: fields.get('end_time'),
      interval_minutes: Number(fields.get('interval_minutes')),
    }
    setBusy(true)
    const { error } = await supabase.from('scraper_schedules').insert(payload)
    if (error) {
      setActionError(error.code === '42501' ? 'Verificá que tengas permisos y que la fecha y hora de fin sigan vigentes.' : error.message)
    } else {
      form.elements.namedItem('confirm').value = ''
      await refresh()
    }
    setBusy(false)
  }

  async function toggle(item) {
    setBusy(true)
    setActionError('')
    const { error } = await supabase.from('scraper_schedules')
      .update({ enabled: !item.enabled }).eq('id', item.id).select('id').single()
    if (error) setActionError(error.message)
    else await refresh()
    setBusy(false)
  }

  return (
    <section aria-labelledby='admin-schedules-title' className='border-t border-green-400/15 p-4 sm:p-6'>
      <h3 id='admin-schedules-title' className='font-[var(--font-display)] text-xl font-black uppercase text-white'>Programaciones</h3>
      <p className='mb-4 mt-1 text-sm text-green-100/75'>Mint ejecuta y guarda los registros en «Últimas ejecuciones». Todos los horarios son de Argentina.</p>
      {loadError && <p role='alert' className='mb-3 text-sm text-red-200'>{loadError}</p>}
      <form onSubmit={save} className='rounded-xl border border-green-400/20 bg-black/15 p-3 sm:p-4'>
        <fieldset disabled={busy || items === null || Boolean(loadError)} className='grid gap-3 sm:grid-cols-2 lg:grid-cols-4'>
          <Field label='Proceso'>
            <select className={inputClass} value={scraper} onChange={(e) => setScraper(e.target.value)}>
              {operations.filter((op) => !op.manualOnly).map((op) => <option key={op.id} value={op.id}>{op.title}</option>)}
            </select>
          </Field>
          <Field label='ID de torneo'>
            <input className={inputClass} type='number' name='torneo_id' min='1' required defaultValue={ACTIVE_TORNEO_ID ?? ''} />
          </Field>
          {scraper !== 'alineaciones' && (
            <Field label='Categoría para resultados'>
              <select className={inputClass} name='categoria'>{categories.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
            </Field>
          )}
          {scraper !== 'resultados' && (
            <Field label='Número de jornada para alineaciones'>
              <input className={inputClass} type='number' name='fecha' min='1' required />
            </Field>
          )}
          <Field label='Repetición'>
            <select className={inputClass} value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value='date'>Una fecha puntual</option>
              <option value='weekly'>Todas las semanas</option>
            </select>
          </Field>
          {kind === 'date' ? (
            <Field label='Fecha de inicio'><input className={inputClass} type='date' name='run_date' required /></Field>
          ) : (
            <Field label='Día de inicio'>
              <select className={inputClass} name='weekday'>{week.map((day, i) => <option key={day} value={i + 1}>{day}</option>)}</select>
            </Field>
          )}
          <Field label='Desde'><input className={inputClass} type='time' name='start_time' value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
          <Field label={endsNextDay ? 'Hasta (del día siguiente)' : 'Hasta'}><input className={inputClass} type='time' name='end_time' value={end} onChange={(e) => setEnd(e.target.value)} required /></Field>
          <Field label='Frecuencia'>
            <select className={inputClass} name='interval_minutes'>{frequencies.map((value) => <option key={value} value={value}>Cada {value} min</option>)}</select>
          </Field>
          <Field label='Confirmación'>
            <input className={inputClass} name='confirm' autoComplete='off' placeholder='Escribí ESCRIBIR' required />
          </Field>
          <button type='submit' className='self-end rounded-lg bg-green-300 px-4 py-2 text-sm font-bold text-green-950 enabled:hover:bg-green-200 disabled:opacity-50'>Guardar programación</button>
        </fieldset>
      </form>
      {actionError && <p role='alert' className='mt-3 text-sm text-red-200'>{actionError}</p>}
      <ul className='mt-4 space-y-2' aria-label='Programaciones guardadas'>
        {items?.map((item) => (
          <li key={item.id} className='flex flex-wrap items-start justify-between gap-3 rounded-xl border border-green-400/20 bg-[#082411] p-3'>
            <div className='min-w-0 space-y-1 text-sm text-green-100'>
              <strong className='text-white'>{operations.find((op) => op.id === item.scraper)?.title}</strong>
              <p>{formatScheduleWindow(item)} · cada {item.interval_minutes} min</p>
              <p className='text-xs'>Torneo {item.torneo_id}{item.fecha && ` · Jornada ${item.fecha}`}{item.categoria && ` · ${categories.find(([id]) => id === item.categoria)?.[1]}`}</p>
              <p className='text-xs'>{!item.enabled ? 'Pausada' : item.next_run_at ? `Próxima corrida ${formatDateTime(item.next_run_at)}` : 'Sin corridas pendientes'}</p>
              {item.last_job_id && <p className='text-xs'>Última orden #{item.last_job_id} · {statuses[item.last_status]?.label || item.last_status} · {formatDateTime(item.last_run_at)}</p>}
            </div>
            <button type='button' disabled={busy || Boolean(loadError)} onClick={() => toggle(item)} className='rounded-lg border border-green-300/35 px-3 py-2 text-xs font-bold text-green-100 enabled:hover:bg-green-300/15 disabled:opacity-50'>
              {item.enabled ? 'Pausar' : 'Reanudar'}
            </button>
          </li>
        ))}
      </ul>
      {items?.length === 0 && <p className='mt-2 text-sm text-green-100/70'>No hay programaciones vigentes.</p>}
    </section>
  )
}
