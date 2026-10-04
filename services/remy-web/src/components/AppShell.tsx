// App chrome: bottom tab bar on phone, left sidebar ≥1024px (DESIGN_BRIEF §4).
// The content column scrolls; sticky action bars live inside each screen and
// sit above the phone tab bar. ToastHost is mounted here so toasts float over
// every screen.
import { useEffect, useRef, useState } from 'react'
import { useIsFetching, useIsMutating } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router-dom'
import { ToastHost } from './ui'
import RatIcon from './RatIcon'
import Icon from './Icon'
import type { IconName } from './Icon'

const TABS: { to: string; label: string; icon: IconName; end: boolean }[] = [
  { to: '/app', label: 'Plan', icon: 'plan', end: true },
  { to: '/app/cookbook', label: 'Cookbook', icon: 'book', end: false },
  { to: '/app/cart', label: 'Cart', icon: 'cart', end: false },
  { to: '/app/settings', label: 'Settings', icon: 'settings', end: false },
]

export default function AppShell() {
  return (
    <div className="mx-auto flex h-full max-w-[1200px] flex-row bg-cream">
      {/* Desktop sidebar */}
      <aside className="hidden w-[230px] flex-none flex-col gap-1.5 border-r border-line bg-surface px-4 py-6 lg:flex">
        <div className="flex items-center gap-2 px-2 pb-4">
          <RatIcon size={26} hole="rgb(var(--c-surface))" className="text-terracotta" />
          <span className="font-serif text-[26px] font-medium tracking-tight">Remy</span>
        </div>
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              `flex min-h-[44px] items-center gap-3 rounded-[12px] px-3 text-[14.5px] font-semibold ${
                isActive ? 'bg-terracotta-soft text-terracotta-deep' : 'text-muted hover:bg-cream hover:text-ink'
              }`
            }
          >
            <Icon name={t.icon} size={20} strokeWidth={1.8} />
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
        <nav aria-label="Main" className="flex flex-none border-t border-line bg-surface px-2 pb-5 pt-2 lg:hidden">
          {TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) =>
                `flex min-h-[48px] flex-1 flex-col items-center justify-center gap-[3px] text-[11.5px] ${
                  isActive ? 'font-bold text-terracotta-deep' : 'font-semibold text-muted'
                }`
              }
            >
              <Icon name={t.icon} size={22} strokeWidth={1.8} />
              {t.label}
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
