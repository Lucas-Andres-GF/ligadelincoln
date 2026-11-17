export default function MatchRoundBadge({ fechaId, className = '' }) {
  const value = String(fechaId ?? '').trim()
  if (!value) return null

  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border border-yellow-300/25 bg-yellow-300/[0.08] px-2 py-0.5 font-[var(--font-display)] text-[8px] font-black uppercase tracking-[0.14em] text-yellow-200 sm:text-[9px] ${className}`}
      aria-label={`Fecha ${value}`}
    >
      <span className='mr-1 text-yellow-400/70'>Fecha</span>
      {value}
    </span>
  )
}
