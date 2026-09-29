import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import {
  getSelectedTorneoId,
  listenToTorneoChange,
  withTorneoParam,
} from '../utils/torneoSelection'

export default function MobileMenu({ currentPath = '/' }) {
  const [isOpen, setIsOpen] = useState(false)
  const [isMounted, setIsMounted] = useState(false)
  const [selectedTorneoId, setSelectedTorneoId] = useState(() =>
    getSelectedTorneoId(null),
  )

  useEffect(() => listenToTorneoChange(setSelectedTorneoId), [])

  useEffect(() => setIsMounted(true), [])

  useEffect(() => {
    setIsOpen(false)
  }, [currentPath])

  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') setIsOpen(false)
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [])

  useEffect(() => {
    document.body.style.overflow = isOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [isOpen])

  const navItems = [
    { href: '/', label: 'Inicio', icon: 'home' },
    { href: '/clubes', label: 'Clubes', icon: 'users' },
    { href: '/historial', label: 'Historial', icon: 'history' },
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
    if (href === '/clubes') return currentPath === '/clubes' || currentPath.startsWith('/club/')
    return currentPath.startsWith(href)
  }

  const scopedHref = (href) => withTorneoParam(href, selectedTorneoId)

  const IconHome = () => (
    <svg className='w-5 h-5' fill='none' viewBox='0 0 24 24' stroke='currentColor'>
      <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={2} d='M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' />
    </svg>
  )

  const IconUsers = () => (
    <svg className='w-5 h-5' fill='none' viewBox='0 0 24 24' stroke='currentColor'>
      <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={2} d='M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656-.126-1.283-.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' />
    </svg>
  )

  return (
    <div className='lg:hidden'>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className='-mr-1 flex h-10 w-10 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border border-green-500/15 bg-green-400/[0.06] focus:outline-none focus-visible:ring-2 focus-visible:ring-green-400'
        aria-label={isOpen ? 'Cerrar menú' : 'Abrir menú'}
        aria-expanded={isOpen}
        aria-controls='mobile-navigation'
      >
        <span className={`block h-0.5 w-5 rounded-full bg-green-400 transition-transform ${isOpen ? 'translate-y-2 rotate-45' : ''}`} />
        <span className={`block h-0.5 w-5 rounded-full bg-green-400 transition-opacity ${isOpen ? 'opacity-0' : ''}`} />
        <span className={`block h-0.5 w-5 rounded-full bg-green-400 transition-transform ${isOpen ? '-translate-y-2 -rotate-45' : ''}`} />
      </button>

      {isMounted && createPortal(
        <>
          {isOpen && (
            <div
              className='fixed inset-0 z-[70] bg-black/70 backdrop-blur-sm'
              onClick={() => setIsOpen(false)}
              aria-hidden='true'
            />
          )}

          <div
            id='mobile-navigation'
            className={`fixed inset-y-0 right-0 z-[80] flex w-[min(22rem,calc(100vw-1.25rem))] flex-col overflow-hidden border-l border-green-400/20 bg-[#082416]/[0.99] shadow-[-24px_0_80px_rgba(0,0,0,0.6)] transition-transform duration-300 ${
              isOpen
                ? 'translate-x-0'
                : 'translate-x-full pointer-events-none'
            }`}
          >
            <div className='flex min-h-20 items-center justify-between border-b border-green-400/15 px-5 py-4'>
              <a href={scopedHref('/')} className='flex items-center gap-3' onClick={() => setIsOpen(false)}>
                <img src='/favicon-nobg.png' alt='' className='h-10 w-10 object-contain' />
                <span className='leading-none'>
                  <span className='block font-[var(--font-display)] text-xl font-black uppercase italic tracking-wide text-green-100'>Liga de Lincoln</span>
                  <span className='mt-1 block text-[8px] font-bold uppercase tracking-[0.22em] text-green-600'>Fútbol local</span>
                </span>
              </a>
              <button
                onClick={() => setIsOpen(false)}
                className='grid h-10 w-10 cursor-pointer place-items-center border-l-2 border-yellow-300 text-green-200 transition hover:text-yellow-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-green-400'
                aria-label='Cerrar menú'
              >
                <svg className='w-5 h-5' fill='none' viewBox='0 0 24 24' stroke='currentColor'>
                  <path strokeLinecap='round' strokeLinejoin='round' strokeWidth={2} d='M6 18L18 6M6 6l12 12' />
                </svg>
              </button>
            </div>

            <nav className='flex-1 overflow-y-auto px-3 py-4' aria-label='Navegación móvil'>
              <span className='mb-2 block px-3 text-[9px] font-extrabold uppercase tracking-[0.22em] text-green-600'>Principal</span>
              {navItems.map((item) => (
                <a
                  key={item.href}
                  href={scopedHref(item.href)}
                  className={`flex items-center gap-3 border-b border-dashed border-green-700/35 px-3 py-3 font-[var(--font-display)] text-sm font-bold uppercase tracking-wide transition ${
                    isActive(item.href)
                      ? 'border-transparent bg-green-400 text-[#072412]'
                      : 'text-green-100 hover:bg-green-400/10'
                  }`}
                >
                  {item.icon === 'home' && <IconHome />}
                  {item.icon === 'users' && <IconUsers />}
                  {item.icon === 'history' && <span className='w-5 h-5 flex items-center justify-center text-xs font-black'>H</span>}
                  {item.label}
                </a>
              ))}

              <span className='mb-2 mt-6 block px-3 text-[9px] font-extrabold uppercase tracking-[0.22em] text-green-600'>
                Divisiones
              </span>

              {categorias.map((cat) => (
                <a
                  key={cat.href}
                  href={cat.href}
                  className={`flex items-center gap-3 border-b border-dashed border-green-700/35 px-3 py-3 font-[var(--font-display)] text-sm font-bold uppercase tracking-wide transition ${
                    isActive(cat.href)
                      ? 'border-transparent bg-yellow-300 text-[#072412]'
                      : 'text-green-100 hover:bg-green-400/10'
                  }`}
                >
                  <span className='flex h-7 w-7 items-center justify-center rounded-lg border border-current/15 bg-black/10 text-xs font-black'>
                    {cat.num}
                  </span>
                  {cat.label}
                </a>
              ))}
            </nav>
            <div className='border-t border-green-400/10 px-5 py-4 text-[8px] font-bold uppercase tracking-[0.2em] text-green-800'>Liga Amateur de Deportes de Lincoln</div>
          </div>
        </>,
        document.body,
      )}
    </div>
  )
}
