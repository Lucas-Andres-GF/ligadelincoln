import { useState, useEffect } from 'react'

export default function MobileMenu({ currentPath = '/' }) {
  const [isOpen, setIsOpen] = useState(false)

  // Cerrar cuando cambia la ruta (detectar cambio en window.location)
  useEffect(() => {
    setIsOpen(false)
  }, [currentPath])

  // Cerrar con Escape
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') setIsOpen(false)
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [])

  // Lock body scroll cuando está abierto
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [isOpen])

  const navItems = [
    { href: '/', label: 'Inicio', icon: 'home' },
    { href: '/clubes', label: 'Clubes', icon: 'users' },
  ]

  const categorias = [
    { href: '/primera', label: 'Primera', num: '1' },
    { href: '/septima', label: 'Séptima', num: '7' },
    { href: '/octava', label: 'Octava', num: '8' },
    { href: '/novena', label: 'Novena', num: '9' },
    { href: '/decima', label: 'Décima', num: '10' },
  ]

  const isActive = (href) => {
    if (href === '/') return currentPath === '/'
    return currentPath.startsWith(href)
  }

  const IconHome = () => (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
    </svg>
  )

  const IconUsers = () => (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
  )

  return (
    <div className="md:hidden">
      {/* Botón Hamburguesa */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex flex-col gap-1.5 cursor-pointer p-2 -mr-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-green-400 rounded"
        aria-label={isOpen ? 'Cerrar menú' : 'Abrir menú'}
        aria-expanded={isOpen}
      >
        <span className={`block w-6 h-0.5 bg-green-400 rounded-full transition-transform ${isOpen ? 'rotate-45 translate-y-2' : ''}`} />
        <span className={`block w-6 h-0.5 bg-green-400 rounded-full transition-opacity ${isOpen ? 'opacity-0' : ''}`} />
        <span className={`block w-6 h-0.5 bg-green-400 rounded-full transition-transform ${isOpen ? '-rotate-45 -translate-y-2' : ''}`} />
      </button>

      {/* Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[70]"
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Menu */}
      <div
        className={`absolute right-0 top-14 z-[80] bg-[#143814] rounded-xl shadow-2xl border border-green-900/40 p-2 w-56 transition-all duration-200 ${
          isOpen
            ? 'opacity-100 translate-y-0'
            : 'opacity-0 -translate-y-2 pointer-events-none'
        }`}
      >
        {/* Header del menú */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-green-900/30 mb-2">
          <span className="text-green-400 font-bold text-sm uppercase">Menú</span>
          <button
            onClick={() => setIsOpen(false)}
            className="text-green-500 hover:text-green-300 cursor-pointer p-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-green-400 rounded"
            aria-label="Cerrar menú"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav className="flex flex-col gap-1">
          {navItems.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition text-sm font-medium ${
                isActive(item.href)
                  ? 'bg-green-500/20 text-green-400'
                  : 'text-green-200 hover:bg-green-900/30'
              }`}
            >
              {item.icon === 'home' && <IconHome />}
              {item.icon === 'users' && <IconUsers />}
              {item.label}
            </a>
          ))}

          <div className="h-px bg-green-900/40 my-2" />

          <span className="px-3 py-1 text-xs text-green-600 font-semibold uppercase">
            Categorías
          </span>

          {categorias.map((cat) => (
            <a
              key={cat.href}
              href={cat.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg transition text-sm ${
                isActive(cat.href)
                  ? 'bg-green-500/20 text-green-400'
                  : 'text-green-200 hover:bg-green-900/30'
              }`}
            >
              <span className="w-6 h-6 rounded bg-green-900/50 flex items-center justify-center text-xs font-bold">
                {cat.num}
              </span>
              {cat.label}
            </a>
          ))}
        </nav>
      </div>
    </div>
  )
}