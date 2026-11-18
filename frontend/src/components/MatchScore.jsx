function RedCards({ count = 0, team }) {
  if (!count) return null
  const label = `${team}: ${count} ${count === 1 ? 'expulsado' : 'expulsados'}`

  return (
    <span role='img' aria-label={label} title={label} className='mx-1 flex max-w-8 flex-wrap justify-center gap-0.5'>
      {Array.from({ length: count }, (_, index) => (
        <span key={index} aria-hidden='true' className='h-2.5 w-1.5 shrink-0 rounded-[1px] bg-red-500' />
      ))}
    </span>
  )
}

export default function MatchScore({ match }) {
  return (
    <>
      <RedCards count={match.redCards?.local} team={match.local?.nombre || 'Local'} />
      <span className='text-base font-black tabular-nums text-white sm:text-lg'>{match.goles_local}</span>
      <span className='mx-1 text-green-700'>–</span>
      <span className='text-base font-black tabular-nums text-white sm:text-lg'>{match.goles_visitante}</span>
      <RedCards count={match.redCards?.visitor} team={match.visitante?.nombre || 'Visitante'} />
    </>
  )
}
