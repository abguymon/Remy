// App chrome: bottom tab bar on phone, left sidebar ≥1024px (DESIGN_BRIEF §4).
// The content column scrolls; sticky action bars live inside each screen and
// sit above the phone tab bar. ToastHost is mounted here so toasts float over
// every screen.
import { useEffect, useRef, useState } from 'react'
import { useIsFetching, useIsMutating } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router-dom'
import { ToastHost } from './ui'
import RatIcon from './RatIcon'

const TABS = [
  { to: '/', label: 'Plan', glyph: '🍳', end: true },
  { to: '/cookbook', label: 'Cookbook', glyph: '📖', end: false },
  { to: '/cart', label: 'Cart', glyph: '🛒', end: false },
  { to: '/settings', label: 'Settings', glyph: '⚙', end: false },
]

export default function AppShell() {
  return (
    <div className="mx-auto flex h-full max-w-[1200px] flex-row bg-cream">
      {/* Desktop sidebar */}
      <aside className="hidden w-[230px] flex-none flex-col gap-1.5 border-r border-line bg-surface px-4 py-6 lg:flex">
        <div className="flex items-center gap-2 px-2 pb-4">
          <RatIcon size={26} hole="#FFFFFF" className="text-terracotta" />
          <span className="font-serif text-2xl font-semibold tracking-tight">Remy</span>
        </div>
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-[9px] px-3 py-2.5 text-sm font-semibold ${
                isActive ? 'bg-cream text-ink' : 'text-muted hover:text-ink'
              }`
            }
          >
            <span className="text-base">{t.glyph}</span>
            {t.label}
          </NavLink>
        ))}
      </aside>

      {/* Content column */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        <GlobalActivityIndicator />
        <main className="no-scrollbar relative flex-1 overflow-y-auto">
          <div className="mx-auto w-full lg:max-w-[780px]">
            <Outlet />
          </div>
        </main>

        {/* Phone tab bar */}
        <nav className="flex flex-none border-t border-line bg-surface px-2 pb-5 pt-2.5 lg:hidden">
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className="flex flex-1 flex-col items-center gap-1 p-1"
            >
              {({ isActive }) => (
                <>
                  <span className={`text-lg leading-none ${isActive ? '' : 'opacity-50'}`}>
                    {t.glyph}
                  </span>
                  <span
                    className={`text-[10.5px] font-semibold ${isActive ? 'text-ink' : 'text-faint'}`}
                  >
                    {t.label}
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        <ToastHost />
      </div>
    </div>
  )
}

// A quiet, app-wide fallback for requests without a more local progress state.
// Delaying its appearance avoids a distracting flash for fast cache refreshes;
// once shown, it remains long enough to be perceived rather than flickering.
function GlobalActivityIndicator() {
  const fetching = useIsFetching()
  const mutating = useIsMutating()
  const active = fetching + mutating > 0
  const [visible, setVisible] = useState(false)
  const shownAt = useRef(0)

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    if (active && !visible) {
      timer = setTimeout(() => {
        shownAt.current = Date.now()
        setVisible(true)
      }, 180)
    } else if (!active && visible) {
      const remaining = Math.max(0, 450 - (Date.now() - shownAt.current))
      timer = setTimeout(() => setVisible(false), remaining)
    }
    return () => clearTimeout(timer)
  }, [active, visible])

  if (!visible) return null

  return (
    <div
      className="pointer-events-none absolute inset-x-0 top-0 z-50"
      role="status"
      aria-live="polite"
    >
      <div className="h-[3px] overflow-hidden bg-terracotta-soft">
        <div className="activity-bar h-full w-1/3 rounded-full bg-terracotta" />
      </div>
      <div className="absolute right-3 top-2 flex items-center gap-2 rounded-full border border-line2 bg-surface/95 px-3 py-1.5 text-[11.5px] font-semibold text-muted shadow-cardsoft backdrop-blur">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-terracotta" aria-hidden />
        {mutating > 0 ? 'Working…' : 'Updating…'}
      </div>
    </div>
  )
}
