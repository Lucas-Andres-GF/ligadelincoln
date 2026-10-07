import { useCallback, useEffect, useMemo, useState } from 'react'
import { createClient } from '@supabase/supabase-js'
import { ACTIVE_TORNEO_ID } from '../config/torneo'

const OPERATIONS = [
  {
    id: 'horarios',
    eyebrow: 'Agenda',
    title: 'Horarios',
    description: 'Fecha, hora y cancha desde el cronograma oficial.',
  },
  {
    id: 'resultados',
    eyebrow: 'Partidos',
    title: 'Resultados',
    description: 'Marcadores y tablas de posiciones.',
  },
  {
    id: 'alineaciones',
    eyebrow: 'Primera',
    title: 'Alineaciones',
    description: 'Jugadores, técnicos, árbitro y goleadores.',
  },
  {
    id: 'resultados_alineaciones',
    eyebrow: 'Jornada',
    title: 'Resultados + alineaciones',
    description: 'Ejecuta ambos procesos en ese orden.',
  },
]

const CATEGORIES = [
  ['', 'Todas las categorías'],
  ['primera', 'Primera'],
  ['septima', 'Séptima'],
  ['octava', 'Octava'],
  ['novena', 'Novena'],
  ['decima', 'Décima'],
]

const STATUS_META = {
  queued: { label: 'En cola', tone: 'border-yellow-300/30 bg-yellow-300/10 text-yellow-200', dot: 'bg-yellow-300' },
  running: { label: 'Ejecutando', tone: 'border-cyan-300/30 bg-cyan-300/10 text-cyan-100', dot: 'bg-cyan-300 animate-pulse' },
  succeeded: { label: 'Completado', tone: 'border-green-300/30 bg-green-300/10 text-green-200', dot: 'bg-green-300' },
  failed: { label: 'Falló', tone: 'border-red-300/30 bg-red-300/10 text-red-200', dot: 'bg-red-400' },
}

const formatDateTime = (value) => {
  if (!value) return '—'
  return new Intl.DateTimeFormat('es-AR', {
    timeZone: 'America/Argentina/Buenos_Aires',
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

const operationTitle = (id) => OPERATIONS.find((item) => item.id === id)?.title || id

function StatusPill({ status }) {
  const meta = STATUS_META[status] || STATUS_META.queued
  return (
    <span className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.12em] ${meta.tone}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  )
}

export default function AdminScrapers({ supabaseUrl, supabaseKey }) {
  const supabase = useMemo(() => createClient(supabaseUrl, supabaseKey), [supabaseUrl, supabaseKey])
  const [scraper, setScraper] = useState('horarios')
  const [mode, setMode] = useState('preview')
  const [categoria, setCategoria] = useState('')
  const [fecha, setFecha] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [jobs, setJobs] = useState([])
  const [worker, setWorker] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [expandedJob, setExpandedJob] = useState(null)

  const needsFecha = scraper === 'alineaciones' || scraper === 'resultados_alineaciones'
  const acceptsCategory = scraper === 'resultados' || scraper === 'resultados_alineaciones'
  const activeJob = jobs.find((job) => ['queued', 'running'].includes(job.status))
  const workerOnline = worker?.last_seen_at
    ? Date.now() - new Date(worker.last_seen_at).getTime() < 30_000
    : false

  const refresh = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setLoading(true)
    const [jobsResult, workersResult] = await Promise.all([
      supabase
        .from('scraper_jobs')
        .select('id,scraper,mode,torneo_id,categoria,fecha,status,requested_at,started_at,finished_at,exit_code,output,error_message,worker_id')
        .order('requested_at', { ascending: false })
        .limit(12),
      supabase
        .from('scraper_workers')
        .select('worker_id,hostname,last_seen_at,current_job_id,version')
        .order('last_seen_at', { ascending: false })
        .limit(1),
    ])

    if (jobsResult.error || workersResult.error) {
      const message = jobsResult.error?.message || workersResult.error?.message
      setError(message?.includes('does not exist')
        ? 'La cola remota todavía no fue instalada en Supabase.'
        : message || 'No se pudo consultar el centro de operaciones.')
    } else {
      setJobs(jobsResult.data || [])
      setWorker(workersResult.data?.[0] || null)
      setError('')
    }
    if (!quiet) setLoading(false)
  }, [supabase])

  useEffect(() => {
    refresh()
    const interval = window.setInterval(() => refresh({ quiet: true }), 4000)
    return () => window.clearInterval(interval)
  }, [refresh])

  useEffect(() => {
    setConfirmation('')
    setNotice('')
    if (!acceptsCategory) setCategoria('')
    if (!needsFecha) setFecha('')
  }, [scraper, mode, acceptsCategory, needsFecha])

  async function submitJob(event) {
    event.preventDefault()
    setError('')
    setNotice('')

    if (ACTIVE_TORNEO_ID === null) {
      setError('No hay un torneo activo válido configurado.')
      return
    }
    if (needsFecha && (!Number.isSafeInteger(Number(fecha)) || Number(fecha) <= 0)) {
      setError('Ingresá un número de fecha válido.')
      return
    }
    if (mode === 'execute' && confirmation !== 'ESCRIBIR') {
      setError('Para ejecutar cambios escribí ESCRIBIR exactamente.')
      return
    }
    if (activeJob) {
      setError('Ya hay un trabajo en cola o ejecutándose. Esperá a que termine.')
      return
    }

    const payload = {
      scraper,
      mode,
      torneo_id: ACTIVE_TORNEO_ID,
      categoria: acceptsCategory && categoria ? categoria : null,
      fecha: needsFecha ? Number(fecha) : null,
    }

    setSubmitting(true)
    const { data, error: insertError } = await supabase
      .from('scraper_jobs')
      .insert(payload)
      .select()
      .single()
    setSubmitting(false)

    if (insertError) {
      setError(insertError.code === '23505'
        ? 'Ya hay otro trabajo activo. Actualizá el estado y volvé a intentar.'
        : insertError.message)
      return
    }

    setNotice(`Trabajo #${data.id} enviado a Mint.`)
    setConfirmation('')
    setExpandedJob(data.id)
    await refresh({ quiet: true })
  }

  return (
    <section className='mb-8 overflow-hidden rounded-2xl border border-green-400/20 bg-[#071d10]/95 shadow-[0_24px_70px_rgba(0,0,0,.25)]'>
      <div className='relative overflow-hidden border-b border-green-400/15 px-4 py-5 sm:px-6'>
        <div className='pointer-events-none absolute -right-12 -top-20 h-48 w-48 rounded-full bg-green-400/10 blur-3xl' />
        <div className='relative flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between'>
          <div>
            <p className='font-[var(--font-display)] text-[11px] font-black uppercase tracking-[0.22em] text-green-400'>Control remoto</p>
            <h2 className='mt-1 font-[var(--font-display)] text-2xl font-black uppercase tracking-tight text-white sm:text-3xl'>Centro de operaciones</h2>
            <p className='mt-1 max-w-2xl text-sm text-green-100/55'>Enviá una orden segura desde cualquier red. Mint la procesa y devuelve el registro acá.</p>
          </div>
          <div className={`flex w-fit items-center gap-3 rounded-xl border px-3 py-2 ${workerOnline ? 'border-green-300/25 bg-green-300/10' : 'border-yellow-300/25 bg-yellow-300/10'}`}>
            <span className={`relative flex h-2.5 w-2.5 ${workerOnline ? '' : 'opacity-70'}`}>
              {workerOnline && <span className='absolute inline-flex h-full w-full animate-ping rounded-full bg-green-300 opacity-50' />}
              <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${workerOnline ? 'bg-green-300' : 'bg-yellow-300'}`} />
            </span>
            <div>
              <div className='text-[10px] font-black uppercase tracking-[0.14em] text-white'>{workerOnline ? 'Mint conectado' : 'Mint sin conexión'}</div>
              <div className='text-[10px] text-green-100/45'>{worker?.last_seen_at ? `Última señal ${formatDateTime(worker.last_seen_at)}` : 'Sin señales registradas'}</div>
            </div>
          </div>
        </div>
      </div>

      <form onSubmit={submitJob} className='grid gap-0 lg:grid-cols-[1.2fr_.8fr]'>
        <div className='border-b border-green-400/15 p-4 sm:p-6 lg:border-b-0 lg:border-r'>
          <div className='grid grid-cols-1 gap-2 sm:grid-cols-2'>
            {OPERATIONS.map((operation) => {
              const selected = scraper === operation.id
              return (
                <button
                  key={operation.id}
                  type='button'
                  onClick={() => setScraper(operation.id)}
                  aria-pressed={selected}
                  className={`min-h-28 rounded-xl border p-4 text-left transition-all ${selected ? 'border-green-300/55 bg-green-300/12 shadow-[inset_3px_0_0_#86efac]' : 'border-green-400/12 bg-black/10 hover:border-green-300/30 hover:bg-green-300/[.06]'}`}
                >
                  <span className={`text-[9px] font-black uppercase tracking-[0.18em] ${selected ? 'text-green-300' : 'text-green-700'}`}>{operation.eyebrow}</span>
                  <strong className='mt-1 block font-[var(--font-display)] text-lg font-black uppercase leading-none text-white'>{operation.title}</strong>
                  <span className='mt-2 block text-xs leading-relaxed text-green-100/45'>{operation.description}</span>
                </button>
              )
            })}
          </div>

          <div className='mt-5 grid gap-4 sm:grid-cols-2'>
            {acceptsCategory && (
              <label className='block'>
                <span className='mb-1.5 block text-[10px] font-black uppercase tracking-[0.14em] text-green-500'>Categoría</span>
                <select value={categoria} onChange={(event) => setCategoria(event.target.value)} className='w-full rounded-xl border border-green-400/20 bg-[#0a2816] px-3 py-3 text-sm text-white outline-none focus:border-green-300/60'>
                  {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
            )}
            {needsFecha && (
              <label className='block'>
                <span className='mb-1.5 block text-[10px] font-black uppercase tracking-[0.14em] text-green-500'>Número de fecha</span>
                <input type='number' min='1' inputMode='numeric' value={fecha} onChange={(event) => setFecha(event.target.value)} placeholder='Ej. 4' className='w-full rounded-xl border border-green-400/20 bg-[#0a2816] px-3 py-3 text-sm text-white outline-none placeholder:text-green-900 focus:border-green-300/60' />
              </label>
            )}
          </div>
        </div>

        <div className='flex flex-col justify-between p-4 sm:p-6'>
          <div>
            <span className='text-[10px] font-black uppercase tracking-[0.14em] text-green-500'>Modo de operación</span>
            <div className='mt-2 grid grid-cols-2 rounded-xl border border-green-400/15 bg-black/15 p-1'>
              <button type='button' onClick={() => setMode('preview')} className={`rounded-lg px-3 py-2.5 text-xs font-black uppercase tracking-wide transition ${mode === 'preview' ? 'bg-green-300 text-[#082310]' : 'text-green-500 hover:text-green-200'}`}>Previsualizar</button>
              <button type='button' onClick={() => setMode('execute')} className={`rounded-lg px-3 py-2.5 text-xs font-black uppercase tracking-wide transition ${mode === 'execute' ? 'bg-yellow-300 text-[#201b03]' : 'text-green-500 hover:text-yellow-200'}`}>Ejecutar</button>
            </div>

            <div className={`mt-4 rounded-xl border p-3 ${mode === 'execute' ? 'border-yellow-300/25 bg-yellow-300/[.07]' : 'border-green-300/15 bg-green-300/[.05]'}`}>
              <p className='text-xs leading-relaxed text-green-100/60'>
                {mode === 'execute'
                  ? 'Este modo modifica los datos públicos. La orden se audita y se ejecuta una sola vez.'
                  : 'No escribe en la base. Revisá primero la salida y luego enviá una ejecución real.'}
              </p>
              {mode === 'execute' && (
                <label className='mt-3 block'>
                  <span className='mb-1 block text-[9px] font-black uppercase tracking-[0.12em] text-yellow-300'>Confirmación</span>
                  <input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete='off' placeholder='Escribí ESCRIBIR' className='w-full rounded-lg border border-yellow-300/25 bg-black/20 px-3 py-2.5 text-sm font-bold text-yellow-100 outline-none placeholder:text-yellow-900 focus:border-yellow-300/70' />
                </label>
              )}
            </div>
          </div>

          <button
            type='submit'
            disabled={submitting || loading || Boolean(activeJob) || (mode === 'execute' && confirmation !== 'ESCRIBIR')}
            className={`mt-5 w-full rounded-xl px-4 py-3.5 font-[var(--font-display)] text-base font-black uppercase tracking-[0.08em] transition enabled:hover:-translate-y-0.5 disabled:opacity-35 ${mode === 'execute' ? 'bg-yellow-300 text-[#1d1904] enabled:hover:bg-yellow-200' : 'bg-green-300 text-[#06200e] enabled:hover:bg-green-200'}`}
          >
            {submitting ? 'Enviando…' : activeJob ? `Trabajo #${activeJob.id} activo` : mode === 'execute' ? 'Enviar ejecución a Mint' : 'Enviar previsualización'}
          </button>
        </div>
      </form>

      {(error || notice) && (
        <div className={`border-t px-4 py-3 text-sm sm:px-6 ${error ? 'border-red-400/20 bg-red-400/[.07] text-red-200' : 'border-green-300/20 bg-green-300/[.07] text-green-200'}`} role='status'>
          {error || notice}
        </div>
      )}

      <div className='border-t border-green-400/15 bg-black/10 px-4 py-5 sm:px-6'>
        <div className='mb-3 flex items-center justify-between'>
          <div>
            <span className='text-[10px] font-black uppercase tracking-[0.18em] text-green-600'>Auditoría</span>
            <h3 className='font-[var(--font-display)] text-lg font-black uppercase text-white'>Últimas ejecuciones</h3>
          </div>
          <button type='button' onClick={() => refresh()} className='rounded-full border border-green-400/20 px-3 py-1.5 text-[10px] font-black uppercase tracking-wider text-green-400 hover:border-green-300/50 hover:text-green-200'>Actualizar</button>
        </div>

        {loading ? (
          <div className='rounded-xl border border-green-400/10 px-4 py-8 text-center text-sm text-green-700'>Consultando la cola…</div>
        ) : jobs.length === 0 ? (
          <div className='rounded-xl border border-dashed border-green-400/15 px-4 py-8 text-center text-sm text-green-100/35'>Todavía no hay ejecuciones remotas.</div>
        ) : (
          <div className='space-y-2'>
            {jobs.map((job) => {
              const expanded = expandedJob === job.id
              return (
                <article key={job.id} className='overflow-hidden rounded-xl border border-green-400/12 bg-[#082411]/70'>
                  <button type='button' onClick={() => setExpandedJob(expanded ? null : job.id)} className='grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 px-3 py-3 text-left sm:px-4'>
                    <span className='font-[var(--font-display)] text-base font-black tabular-nums text-green-700'>#{job.id}</span>
                    <span className='min-w-0'>
                      <strong className='block truncate text-sm text-white'>{operationTitle(job.scraper)}</strong>
                      <span className='block truncate text-[10px] uppercase tracking-wide text-green-100/40'>{job.mode === 'execute' ? 'Ejecución real' : 'Previsualización'} · {formatDateTime(job.requested_at)}</span>
                    </span>
                    <StatusPill status={job.status} />
                  </button>
                  {expanded && (
                    <div className='border-t border-green-400/10 p-3 sm:p-4'>
                      <div className='mb-3 grid grid-cols-2 gap-2 text-[10px] uppercase tracking-wide text-green-100/45 sm:grid-cols-4'>
                        <span>Torneo <strong className='block text-xs text-green-100'>{job.torneo_id}</strong></span>
                        <span>Fecha <strong className='block text-xs text-green-100'>{job.fecha || '—'}</strong></span>
                        <span>Categoría <strong className='block text-xs text-green-100'>{job.categoria || 'Todas'}</strong></span>
                        <span>Finalizó <strong className='block text-xs text-green-100'>{formatDateTime(job.finished_at)}</strong></span>
                      </div>
                      <pre className='max-h-80 overflow-auto whitespace-pre-wrap rounded-lg border border-black/30 bg-[#031008] p-3 font-mono text-[11px] leading-relaxed text-green-100/70'>{job.output || (job.status === 'queued' ? 'Esperando que Mint tome el trabajo…' : 'El proceso todavía no produjo salida.')}</pre>
                      {job.error_message && <p className='mt-2 text-xs font-bold text-red-300'>{job.error_message}</p>}
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
}

