export default function RankingToggle({ expanded, controls, onToggle, moreLabel = 'Ver más', className = '' }) {
  return (
    <button
      type='button'
      onClick={onToggle}
      aria-expanded={expanded}
      aria-controls={controls}
      className={`flex w-full cursor-pointer items-center justify-center gap-1.5 bg-[#082a17] px-4 py-2.5 font-[var(--font-display)] text-[10px] font-black uppercase tracking-[0.16em] text-green-200 transition-colors hover:bg-green-400/10 hover:text-yellow-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-yellow-300 ${className}`}
    >
      {expanded ? 'Ver menos' : moreLabel}
      <svg viewBox='0 0 20 20' fill='none' stroke='currentColor' strokeWidth='2.5'
        className={`h-3 w-3 transition-transform ${expanded ? 'rotate-180' : ''}`} aria-hidden='true'>
        <path d='m5 7.5 5 5 5-5' strokeLinecap='round' strokeLinejoin='round' />
      </svg>
    </button>
  )
}
