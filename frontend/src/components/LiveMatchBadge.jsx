export default function LiveMatchBadge() {
  return (
    <span
      className='inline-flex items-center gap-1.5 font-[var(--font-display)] font-black uppercase tracking-[0.14em] text-red-300'
      role='status'
      aria-label='Partido en juego'
    >
      <span className='relative flex h-2.5 w-2.5' aria-hidden='true'>
        <span className='absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-70 motion-reduce:animate-none' />
        <span className='relative inline-flex h-2.5 w-2.5 rounded-full border border-red-200/70 bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.9)]' />
      </span>
      En juego
    </span>
  )
}
