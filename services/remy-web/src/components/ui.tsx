// Shared component library (DESIGN_BRIEF §6). Every value here is mined from the
// prototype in design/src. Phone-first, ≥44px touch targets, AA contrast.
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { fetchBlobUrl } from '../lib/api'
import { useToast } from '../stores/toast'
import Icon from './Icon'
import type { IconName } from './Icon'

// --- Button ----------------------------------------------------------------

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

const buttonBase =
  'inline-flex items-center justify-center gap-2 font-semibold rounded-[14px] transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer'

const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'bg-terracotta text-onaccent shadow-terracotta hover:bg-terracotta-dark',
  secondary: 'bg-surface border border-line2 text-ink hover:bg-cream',
  ghost: 'bg-transparent text-muted hover:text-ink',
  danger: 'bg-transparent border border-danger-border text-danger hover:bg-danger-bg',
}

export function Button({
  variant = 'primary',
  className = '',
  children,
  busy = false,
  busyLabel,
  disabled,
  ...rest
}: {
  variant?: ButtonVariant
  className?: string
  children: ReactNode
  busy?: boolean
  busyLabel?: ReactNode
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const spinnerClass =
    variant === 'primary'
      ? '!border-onaccent/40 !border-t-onaccent'
      : variant === 'danger'
        ? '!border-danger-border !border-t-danger'
        : ''

  return (
    <button
      className={`${buttonBase} ${buttonVariants[variant]} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy && <Spinner className={spinnerClass} />}
      {busy && busyLabel !== undefined ? busyLabel : children}
    </button>
  )
}

// --- Spinner ---------------------------------------------------------------

export function Spinner({ className = '' }: { className?: string }) {
  return (
    <span
      className={`inline-block rounded-full border-2 border-line2 border-t-terracotta animate-spin ${className}`}
      style={{ width: 13, height: 13, animationDuration: '.8s' }}
      aria-hidden
    />
  )
}

// --- Step indicator (5 steps, tappable-back) -------------------------------
// A segmented progress bar with labels; each segment is a
// ≥44px-tall button so reachable steps stay tappable.

const STEPS = ['Plan', 'Pick', 'List', 'Cart', 'Done']

export function StepIndicator({
  current,
  reachable,
  onStep,
}: {
  current: number // 0..4
  reachable: number // furthest reachable step index
  onStep: (n: number) => void
}) {
  return (
    <nav aria-label="Plan steps" className="grid grid-cols-5 gap-1.5 px-5 pt-2">
      {STEPS.map((label, i) => {
        const done = i < current
        const active = i === current
        const canGo = i <= reachable
        return (
          <button
            key={label}
            onClick={() => canGo && onStep(i)}
            disabled={!canGo}
            className="flex min-h-[44px] flex-col justify-center gap-1.5 text-left disabled:cursor-default"
            aria-current={active ? 'step' : undefined}
          >
            <span
              className={`h-1 rounded-full ${
                done || active ? 'bg-terracotta' : canGo ? 'bg-terracotta/40' : 'bg-line2'
              }`}
            />
            <span
              className={`flex items-center gap-1 text-[11.5px] font-semibold ${
                active ? 'text-terracotta-deep' : done ? 'text-ink' : 'text-faint'
              }`}
            >
              {done && <Icon name="check" size={12} strokeWidth={3} />}
              {label}
            </span>
          </button>
        )
      })}
    </nav>
  )
}

// --- Status pill -----------------------------------------------------------

export type PillTone = 'success' | 'warn' | 'danger' | 'neutral'

const pillTones: Record<PillTone, { bg: string; fg: string; dot: string }> = {
  success: { bg: 'bg-success-bg', fg: 'text-success', dot: 'bg-success-dot' },
  warn: { bg: 'bg-warn-bg', fg: 'text-warn', dot: 'bg-warn-dot' },
  danger: { bg: 'bg-danger-bg', fg: 'text-danger', dot: 'bg-danger-dot' },
  neutral: { bg: 'bg-badge-webbg', fg: 'text-muted', dot: 'bg-hint' },
}

export function StatusPill({ tone, children }: { tone: PillTone; children: ReactNode }) {
  const t = pillTones[tone]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-[3px] text-[11px] font-semibold ${t.bg} ${t.fg}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${t.dot}`} />
      {children}
    </span>
  )
}

// --- Origin badge ----------------------------------------------------------

export function OriginBadge({ origin }: { origin: 'saved' | 'favorite' | 'web' }) {
  const meta = {
    saved: { text: 'Saved', cls: 'bg-badge-savedbg text-badge-savedfg' },
    favorite: { text: 'Favorite site', cls: 'bg-badge-favbg text-badge-favfg' },
    web: { text: 'Web', cls: 'bg-badge-webbg text-badge-webfg' },
  }[origin]
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-bold ${meta.cls}`}
    >
      {origin === 'favorite' && <Icon name="star" size={10} filled strokeWidth={0} />}
      {meta.text}
    </span>
  )
}

// --- Photo fallback --------------------------------------------------------

export function PhotoFallback({
  src,
  alt,
  className = '',
  label = 'recipe photo',
}: {
  src?: string | null
  alt?: string
  className?: string
  label?: string
}) {
  const [failed, setFailed] = useState(false)
  if (src && !failed) {
    return (
      <img
        src={src}
        alt={alt ?? ''}
        onError={() => setFailed(true)}
        className={`h-full w-full object-cover ${className}`}
      />
    )
  }
  return (
    <div
      className={`photo-fallback flex h-full w-full items-center justify-center text-faint ${className}`}
      role="img"
      aria-label={label}
    >
      <Icon name="utensils" size={28} strokeWidth={1.6} />
    </div>
  )
}

// --- Authed image (recipe photos) ------------------------------------------
// Loads a Bearer-protected image endpoint via blob fetch, shows a shimmer while
// loading, and falls back to the warm crosshatch placeholder on error/absence.

export function AuthedImage({
  path,
  alt,
  className = '',
  label = 'recipe photo',
}: {
  path?: string | null
  alt?: string
  className?: string
  label?: string
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!path) {
      setFailed(true)
      return
    }
    setFailed(false)
    setUrl(null)
    let active = true
    let objUrl: string | null = null
    fetchBlobUrl(path)
      .then((u) => {
        if (active) {
          objUrl = u
          setUrl(u)
        } else {
          URL.revokeObjectURL(u)
        }
      })
      .catch(() => active && setFailed(true))
    return () => {
      active = false
      if (objUrl) URL.revokeObjectURL(objUrl)
    }
  }, [path])

  if (failed || !path) {
    return <PhotoFallback className={className} label={label} />
  }
  if (!url) {
    return <div className={`sk h-full w-full ${className}`} />
  }
  return <img src={url} alt={alt ?? ''} className={`h-full w-full object-cover ${className}`} />
}

// --- Sticky action bar -----------------------------------------------------

export function StickyBar({ children }: { children: ReactNode }) {
  return (
    <div className="flex-none border-t border-line bg-surface/95 px-5 pb-4 pt-3 backdrop-blur">
      {children}
    </div>
  )
}

// --- Skeleton candidate card ----------------------------------------------

export function CandidateSkeleton() {
  return (
    <div className="w-[210px] flex-none">
      <div className="sk h-[150px] rounded-card" />
      <div className="sk mt-2.5 h-3 w-[90%] rounded" />
      <div className="sk mt-1.5 h-3 w-[55%] rounded" />
    </div>
  )
}

// --- Degraded / error banner with scoped retry -----------------------------

export function DegradedBanner({
  children,
  onRetry,
  tone = 'warn',
  retrying = false,
}: {
  children: ReactNode
  onRetry?: () => void
  tone?: 'warn' | 'danger'
  retrying?: boolean
}) {
  const styles =
    tone === 'danger'
      ? 'bg-danger-bg border-danger-border text-danger'
      : 'bg-warn-bg border-warn-border text-warn'
  const btn = tone === 'danger' ? 'bg-danger' : 'bg-warn'
  const icon = tone === 'danger' ? 'alert' : 'info'
  return (
    <div
      className={`flex items-center justify-between gap-2.5 rounded-[14px] border px-3.5 py-3 text-[13px] ${styles}`}
    >
      <Icon name={icon} size={17} className="flex-none" />
      <span className="flex-1">{children}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          disabled={retrying}
          className={`flex-none rounded-[10px] px-3 py-1.5 text-[12.5px] font-semibold text-cream disabled:opacity-60 ${btn}`}
        >
          {retrying ? 'Retrying…' : 'Retry'}
        </button>
      )}
    </div>
  )
}

// --- Empty state block -----------------------------------------------------

export function EmptyState({
  icon = 'utensils',
  message,
  action,
}: {
  icon?: IconName
  message: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-2.5 rounded-panel border border-dashed border-line2 bg-surface/50 px-6 py-9 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-chip text-muted">
        <Icon name={icon} size={22} strokeWidth={1.8} />
      </div>
      <div className="text-[14px] text-muted">{message}</div>
      {action}
    </div>
  )
}

// --- Confirm dialog (destructive) ------------------------------------------

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  body?: string
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-30 flex animate-pop items-center justify-center bg-dark/50 p-6"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-[340px] rounded-panel bg-surface p-6 shadow-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="font-serif text-[22px] font-medium tracking-tight">{title}</div>
        {body && <div className="mt-1.5 text-[13px] leading-relaxed text-muted">{body}</div>}
        <div className="mt-4 flex gap-2.5">
          <Button variant="secondary" className="flex-1 py-3 text-sm" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? 'danger' : 'primary'}
            className="flex-1 py-3 text-sm"
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}

// --- Toast host ------------------------------------------------------------

export function ToastHost() {
  const { message, action, dismiss } = useToast()
  if (!message) return null
  return (
    <div
      className="absolute bottom-24 left-1/2 z-20 flex -translate-x-1/2 animate-pop items-center gap-3 whitespace-nowrap rounded-[14px] bg-ink px-4 py-3 text-[13.5px] font-medium text-cream shadow-toast"
      role="status"
    >
      <span className="cursor-pointer" onClick={dismiss}>
        {message}
      </span>
      {action && (
        <button
          onClick={() => {
            action.run()
            dismiss()
          }}
          className="flex-none font-bold text-terracotta-soft"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}

// --- Section label (uppercase eyebrow) -------------------------------------

export function SectionLabel({
  children,
  tone = 'hint',
  className = '',
}: {
  children: ReactNode
  tone?: 'hint' | 'success' | 'warn' | 'danger' | 'terracotta'
  className?: string
}) {
  const colors = {
    hint: 'text-faint',
    success: 'text-success',
    warn: 'text-warn',
    danger: 'text-danger',
    terracotta: 'text-terracotta',
  }
  return (
    <div
      className={`text-[11.5px] font-bold uppercase tracking-[.07em] ${colors[tone]} ${className}`}
    >
      {children}
    </div>
  )
}

// --- Count stepper ---------------------------------------------------------

export function CountStepper({
  count,
  onChange,
  min = 1,
}: {
  count: number
  onChange: (next: number) => void
  min?: number
}) {
  return (
    <div className="flex items-center overflow-hidden rounded-[12px] border border-line2 bg-cream">
      <button
        onClick={() => onChange(Math.max(min, count - 1))}
        disabled={count <= min}
        className="flex h-10 w-10 items-center justify-center text-muted disabled:opacity-40"
        aria-label="Decrease quantity"
      >
        <Icon name="minus" size={16} strokeWidth={2.4} />
      </button>
      <span className="tab-fig w-[30px] text-center text-sm font-semibold">{count}</span>
      <button
        onClick={() => onChange(count + 1)}
        className="flex h-10 w-10 items-center justify-center text-muted"
        aria-label="Increase quantity"
      >
        <Icon name="plus" size={16} strokeWidth={2.4} />
      </button>
    </div>
  )
}

// useDebouncedCallback — used by count steppers to batch API writes.
export function useDebounced<T extends (...args: never[]) => void>(fn: T, delay = 500): T {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fnRef = useRef(fn)
  useEffect(() => {
    fnRef.current = fn
  })
  return ((...args: never[]) => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => fnRef.current(...args), delay)
  }) as T
}

// --- v2 style primitives -----------------------------------------------------
// The redesign's shared vocabulary: big serif screen titles, serif section
// headings, pill chips, round 44px icon buttons, segmented controls.

export function ScreenHeader({
  title,
  subtitle,
  action,
  className = '',
}: {
  title: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <header className={`flex items-start justify-between gap-3 px-5 pt-7 ${className}`}>
      <div className="min-w-0">
        <h1 className="font-serif text-[34px] font-medium leading-[1.05] tracking-[-0.02em]">{title}</h1>
        {subtitle && <div className="mt-1.5 text-[13.5px] text-muted">{subtitle}</div>}
      </div>
      {action && <div className="flex-none">{action}</div>}
    </header>
  )
}

export function SectionHeading({
  children,
  sub,
  action,
  id,
  className = '',
}: {
  children: ReactNode
  sub?: ReactNode
  action?: ReactNode
  id?: string
  className?: string
}) {
  return (
    <div className={`flex items-end justify-between gap-3 ${className}`}>
      <div className="min-w-0">
        <h2 id={id} className="font-serif text-[22px] font-medium tracking-[-0.01em]">
          {children}
        </h2>
        {sub && <div className="mt-0.5 text-[13px] text-muted">{sub}</div>}
      </div>
      {action && <div className="flex-none text-[13.5px] font-semibold text-terracotta-deep">{action}</div>}
    </div>
  )
}

export function Chip({
  children,
  active = false,
  onClick,
  icon,
  className = '',
}: {
  children: ReactNode
  active?: boolean
  onClick?: () => void
  icon?: IconName
  className?: string
}) {
  const cls = `inline-flex h-9 flex-none items-center gap-1.5 rounded-full border px-3.5 text-[13.5px] font-semibold ${
    active ? 'border-ink bg-ink text-cream' : 'border-line bg-surface text-ink'
  } ${className}`
  const inner = (
    <>
      {icon && <Icon name={icon} size={14} filled={icon === 'heart' || icon === 'star'} strokeWidth={icon === 'heart' || icon === 'star' ? 0 : 2} />}
      {children}
    </>
  )
  if (!onClick) return <span className={cls}>{inner}</span>
  return (
    <button type="button" onClick={onClick} aria-pressed={active} className={cls}>
      {inner}
    </button>
  )
}

export function IconButton({
  icon,
  label,
  variant = 'surface',
  size = 44,
  iconSize = 20,
  className = '',
  ...rest
}: {
  icon: IconName
  label: string
  variant?: 'surface' | 'glass' | 'accent' | 'plain'
  size?: number
  iconSize?: number
  className?: string
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'children'>) {
  const variants = {
    surface: 'border border-line bg-surface text-ink hover:bg-cream',
    glass: 'bg-surface/85 text-ink backdrop-blur',
    accent: 'bg-terracotta text-onaccent shadow-terracotta hover:bg-terracotta-dark',
    plain: 'text-ink hover:bg-chip',
  }
  return (
    <button
      type="button"
      aria-label={label}
      className={`inline-flex flex-none items-center justify-center rounded-full disabled:opacity-40 ${variants[variant]} ${className}`}
      style={{ width: size, height: size }}
      {...rest}
    >
      <Icon name={icon} size={iconSize} strokeWidth={2.2} />
    </button>
  )
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
  className = '',
}: {
  value: T
  options: { value: T; label: ReactNode }[]
  onChange: (v: T) => void
  label: string
  className?: string
}) {
  return (
    <div role="group" aria-label={label} className={`flex rounded-[12px] bg-chip p-[3px] ${className}`}>
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={`flex h-9 flex-1 items-center justify-center gap-1.5 rounded-[9px] px-3 text-[13px] font-semibold ${
              on ? 'bg-surface text-ink shadow-card' : 'text-muted hover:text-ink'
            }`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
