import { useEffect, useState } from 'react'

const TABS = [
  { id: 'fixture', label: 'Fixture' },
  { id: 'tabla', label: 'Tabla' },
  { id: 'historial', label: 'Historial' },
]

function currentHash() {
  if (typeof window === 'undefined') return 'fixture'
  const hash = window.location.hash.slice(1)
  return TABS.some((tab) => tab.id === hash) ? hash : 'fixture'
}

export default function TournamentTabs() {
  const [activeTab, setActiveTab] = useState('fixture')

  useEffect(() => {
    function syncHash() {
      setActiveTab(currentHash())
    }

    syncHash()
    window.addEventListener('hashchange', syncHash)
    return () => window.removeEventListener('hashchange', syncHash)
  }, [])

  return (
    <nav
      aria-label='Secciones del torneo'
      className='mb-4 overflow-hidden rounded-xl border border-green-400/20 bg-[#123912] shadow-lg shadow-black/20'
    >
      <div className='grid grid-cols-3'>
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id
          return (
            <a
              key={tab.id}
              href={`#${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              aria-current={isActive ? 'location' : undefined}
              className={`relative px-3 py-2.5 text-center text-[11px] font-black uppercase tracking-[0.18em] transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-yellow-300 ${
                isActive
                  ? 'bg-green-400/15 text-yellow-300'
                  : 'text-green-300/70 hover:bg-green-950/40 hover:text-green-200'
              }`}
            >
              {tab.label}
              {isActive && (
                <span className='absolute inset-x-5 bottom-0 h-0.5 rounded-full bg-yellow-300' aria-hidden='true' />
              )}
            </a>
          )
        })}
      </div>
    </nav>
  )
}
