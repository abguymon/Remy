// Shared component library (DESIGN_BRIEF §6). Every value here is mined from the
// prototype in design/src. Phone-first, ≥44px touch targets, AA contrast.
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useToast } from '../stores/toast'

// --- Button ----------------------------------------------------------------

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

const buttonBase =
  'inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer'

const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'bg-terracotta text-white shadow-terracotta hover:bg-terracotta-dark',
  secondary: 'bg-surface border border-line2 text-ink hover:bg-cream',
  ghost: 'bg-transparent text-muted hover:text-ink',
  danger: 'bg-transparent border border-danger-border text-danger hover:bg-danger-bg',
}

export function Button({
  variant = 'primary',
  className = '',
  children,
  ...rest
}: {
  variant?: ButtonVariant
  className?: string
  children: ReactNode
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`${buttonBase} ${buttonVariants[variant]} ${className}`} {...rest}>
      {children}
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
    <div className="flex items-center px-5 pt-3.5 pb-3">
      {STEPS.map((label, i) => {
        const done = i < current
        const active = i === current
        const canGo = i <= reachable
        const circle =
          done || active
            ? 'bg-terracotta text-white'
            : canGo
              ? 'bg-terracotta-soft text-terracotta-deep'
              : 'bg-line2 text-muted'
        return (
          <div key={label} className="flex flex-1 items-center last:flex-none">
            <button
              onClick={() => canGo && onStep(i)}
              disabled={!canGo}
              className="flex flex-1 flex-col items-center gap-1.5 disabled:cursor-default"
              aria-current={active ? 'step' : undefined}
            >
              <span
                className={`flex h-[26px] w-[26px] items-center justify-center rounded-full text-xs font-bold ${circle}`}
              >
                {done ? '✓' : i + 1}
              </span>
              <span
                className={`text-[9.5px] font-semibold ${active || done ? 'text-ink' : 'text-muted'}`}
              >
                {label}
              </span>
            </button>
            {i < STEPS.length - 1 && <span className="h-0.5 w-2 flex-none bg-line2" />}
          </div>
        )
      })}
    </div>
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
    favorite: { text: '★ Favorite site', cls: 'bg-badge-favbg text-badge-favfg' },
    web: { text: 'Web', cls: 'bg-badge-webbg text-badge-webfg' },
  }[origin]
  return (
    <span className={`rounded-md px-[7px] py-0.5 text-[10px] font-bold ${meta.cls}`}>
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
    <div className={`photo-fallback flex h-full w-full items-end p-2.5 ${className}`}>
      <span className="rounded bg-surface/70 px-1.5 py-0.5 font-mono text-[10px] text-[#A0937E]">
        {label}
      </span>
    </div>
  )
}

// --- Sticky action bar -----------------------------------------------------

export function StickyBar({ children }: { children: ReactNode }) {
  return (
    <div className="flex-none border-t border-line bg-surface/95 px-5 pb-3.5 pt-3 backdrop-blur">
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
  return (
    <div
      className={`flex items-center justify-between gap-2 rounded-[10px] border px-3 py-2.5 text-[12.5px] ${styles}`}
    >
      <span>{children}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          disabled={retrying}
          className={`flex-none rounded-md px-2.5 py-1 text-[11.5px] font-semibold text-white disabled:opacity-60 ${btn}`}
        >
          {retrying ? 'Retrying…' : 'Retry'}
        </button>
      )}
    </div>
  )
}

// --- Empty state block -----------------------------------------------------

export function EmptyState({
  glyph = '🍽',
  message,
  action,
}: {
  glyph?: string
  message: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-panel border border-dashed border-line2 bg-surface/50 px-6 py-8 text-center">
      <div className="text-2xl">{glyph}</div>
      <div className="text-[13.5px] text-muted">{message}</div>
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
      className="absolute inset-0 z-30 flex animate-pop items-center justify-center p-6"
      style={{ background: 'rgba(40,30,20,.4)' }}
      onClick={onCancel}
    >
      <div
        className="w-full max-w-[340px] rounded-[18px] bg-surface p-[22px] shadow-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="font-serif text-xl font-semibold">{title}</div>
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
  const { message, dismiss } = useToast()
  if (!message) return null
  return (
    <div
      onClick={dismiss}
      className="absolute bottom-24 left-1/2 z-20 -translate-x-1/2 animate-pop cursor-pointer whitespace-nowrap rounded-xl bg-ink px-4 py-2.5 text-[13px] font-medium text-cream shadow-toast"
      role="status"
    >
      {message}
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
    hint: 'text-hint',
    success: 'text-success',
    warn: 'text-warn',
    danger: 'text-danger',
    terracotta: 'text-terracotta',
  }
  return (
    <div
      className={`text-xs font-bold uppercase tracking-[.06em] ${colors[tone]} ${className}`}
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
    <div className="flex items-center overflow-hidden rounded-[9px] border border-line2">
      <button
        onClick={() => onChange(Math.max(min, count - 1))}
        disabled={count <= min}
        className="h-9 w-9 bg-cream text-lg text-muted disabled:opacity-40"
        aria-label="Decrease quantity"
      >
        −
      </button>
      <span className="tab-fig w-[30px] text-center text-sm font-semibold">{count}</span>
      <button
        onClick={() => onChange(count + 1)}
        className="h-9 w-9 bg-cream text-lg text-muted"
        aria-label="Increase quantity"
      >
        +
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
