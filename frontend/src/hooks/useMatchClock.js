import { useEffect, useState } from 'react'

export function useMatchClock(intervalMs = 30_000) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const updateClock = () => setNow(Date.now())
    const interval = window.setInterval(updateClock, intervalMs)
    document.addEventListener('visibilitychange', updateClock)
    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', updateClock)
    }
  }, [intervalMs])

  return now
}
