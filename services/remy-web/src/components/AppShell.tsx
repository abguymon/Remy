// App chrome: bottom tab bar on phone, left sidebar ≥1024px (DESIGN_BRIEF §4).
// The content column scrolls; sticky action bars live inside each screen and
// sit above the phone tab bar. ToastHost is mounted here so toasts float over
// every screen.
import { NavLink, Outlet } from 'react-router-dom'
import { ToastHost } from './ui'

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
        <div className="font-serif text-2xl font-semibold tracking-tight px-2 pb-4">Remy</div>
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
