// Cook mode (COOKBOOK_PLAN item 1): one step at a time, full screen, always
// dark. Large type, the ingredients each step mentions (scaled to the servings
// picked on the recipe page), tap-to-start timers for durations in the step,
// screen wake lock, and arrow-key / swipe navigation. Finishing logs the cook.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Icon from '../components/Icon'
import ScaleControls, { useScale } from '../components/ScaleControls'
import { Button, EmptyState, IconButton } from '../components/ui'
import {
  groupBySection,
  ingredientKeywords,
  renderIngredient,
  sectionTitle,
  stepMentions,
  stepTimers,
} from '../lib/ingredients'
import { useMarkCooked, useRecipe } from '../lib/queries'
import { toast } from '../stores/toast'

interface RunningTimer {
  id: number
  label: string
  endsAt: number
  pausedLeft: number | null // ms left while paused
}

function mmss(ms: number): string {
  const s = Math.max(0, Math.ceil(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

// Keep the screen on while cooking; re-acquired when the tab becomes visible.
function useWakeLock(): boolean {
  const [held, setHeld] = useState(false)
  useEffect(() => {
    const nav = navigator as Navigator & {
      wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void>; addEventListener: (e: string, f: () => void) => void }> }
    }
    if (!nav.wakeLock) return
    let lock: Awaited<ReturnType<NonNullable<typeof nav.wakeLock>['request']>> | null = null
    let cancelled = false
    const acquire = async () => {
      try {
        lock = await nav.wakeLock!.request('screen')
        if (cancelled) return void lock.release()
        setHeld(true)
        lock.addEventListener('release', () => setHeld(false))
      } catch {
        setHeld(false) // denied (battery saver, unfocused) — cook mode still works
      }
    }
    const onVisible = () => document.visibilityState === 'visible' && acquire()
    acquire()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisible)
      lock?.release().catch(() => {})
    }
  }, [])
  return held
}

function chime() {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const ctx = new Ctx()
    ;[0, 0.35, 0.7].forEach((t) => {
      const o = ctx.createOscillator()
      const g = ctx.createGain()
      o.frequency.value = 880
      g.gain.setValueAtTime(0.0001, ctx.currentTime + t)
      g.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + t + 0.02)
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + t + 0.3)
      o.connect(g).connect(ctx.destination)
      o.start(ctx.currentTime + t)
      o.stop(ctx.currentTime + t + 0.32)
    })
    setTimeout(() => ctx.close(), 1500)
  } catch {
    // no audio — the visual alert still shows
  }
  navigator.vibrate?.([300, 150, 300, 150, 300])
}

export default function CookMode() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const recipe = useRecipe(id)
  const cooked = useMarkCooked(id ?? '')
  const scale = useScale(recipe.data)
  const wakeLock = useWakeLock()
  const [step, setStep] = useState(0)
  const [showIngredients, setShowIngredients] = useState(false)
  const [timers, setTimers] = useState<RunningTimer[]>([])
  const [now, setNow] = useState(() => Date.now())
  const fired = useRef<Set<number>>(new Set())
  const touchX = useRef<number | null>(null)

  const r = recipe.data
  const steps = r?.instructions ?? []
  const last = steps.length - 1
  const exit = useCallback(() => navigate(`/app/cookbook/${id}`), [navigate, id])

  const go = useCallback(
    (delta: number) => setStep((s) => Math.min(Math.max(0, s + delta), Math.max(0, last))),
    [last],
  )

  // Arrow keys / space while cooking (ignored when typing in the sheet).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (showIngredients || (e.target as HTMLElement)?.closest('input,textarea')) return
      if (e.key === 'ArrowRight' || e.key === ' ') {
        e.preventDefault()
        go(1)
      } else if (e.key === 'ArrowLeft') go(-1)
      else if (e.key === 'Escape') exit()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, exit, showIngredients])

  // Timer clock: tick while any timer runs; chime once per finished timer.
  useEffect(() => {
    if (!timers.some((t) => t.pausedLeft == null)) return
    const iv = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(iv)
  }, [timers])
  useEffect(() => {
    for (const t of timers) {
      if (t.pausedLeft == null && t.endsAt <= now && !fired.current.has(t.id)) {
        fired.current.add(t.id)
        chime()
      }
    }
  }, [now, timers])

  // Which ingredients each step mentions (matched on key food words).
  const perStep = useMemo(() => {
    if (!r) return []
    const keyed = r.ingredients.map((ing) => ({ ing, keys: ingredientKeywords(ing.raw, ing.food) }))
    return steps.map((text) => keyed.filter((k) => k.keys.length && stepMentions(text, k.keys)).map((k) => k.ing))
  }, [r, steps])

  if (recipe.isLoading) {
    return <div className="dark h-full bg-cream" aria-busy />
  }
  if (recipe.isError || !r) {
    return (
      <div className="dark flex h-full items-center bg-cream px-5 text-ink">
        <EmptyState icon="info" message="That recipe isn't here." />
      </div>
    )
  }
  if (steps.length === 0) {
    return (
      <div className="dark flex h-full flex-col items-center justify-center gap-4 bg-cream px-5 text-ink">
        <EmptyState icon="list" message="This recipe has no steps to cook through." />
        <Button variant="secondary" className="h-11 px-5 text-sm" onClick={exit}>
          Back to recipe
        </Button>
      </div>
    )
  }

  const text = steps[step]
  const uses = perStep[step] ?? []
  const suggestions = stepTimers(text)

  function startTimer(label: string, seconds: number) {
    setNow(Date.now())
    setTimers((ts) => [...ts, { id: Date.now() + Math.random(), label, endsAt: Date.now() + seconds * 1000, pausedLeft: null }])
  }
  function togglePause(t: RunningTimer) {
    setTimers((ts) =>
      ts.map((x) =>
        x.id !== t.id
          ? x
          : x.pausedLeft == null
            ? { ...x, pausedLeft: x.endsAt - Date.now() }
            : { ...x, endsAt: Date.now() + x.pausedLeft, pausedLeft: null },
      ),
    )
    setNow(Date.now())
  }
  const removeTimer = (t: RunningTimer) => setTimers((ts) => ts.filter((x) => x.id !== t.id))

  async function finish() {
    try {
      await cooked.mutateAsync()
      toast('Nice — logged as cooked')
    } catch {
      toast("Couldn't log the cook — try again from the recipe")
    }
    exit()
  }

  const servingsNote = scale.servings
    ? `${scale.servings} ${scale.servings === 1 ? scale.noun.one : scale.noun.many}`
    : scale.factor !== 1
      ? `${scale.factor}× batch`
      : null

  return (
    <div
      className="dark flex h-full flex-col bg-cream text-ink"
      onTouchStart={(e) => (touchX.current = e.touches[0].clientX)}
      onTouchEnd={(e) => {
        if (touchX.current == null) return
        const dx = e.changedTouches[0].clientX - touchX.current
        touchX.current = null
        if (Math.abs(dx) > 70) go(dx < 0 ? 1 : -1)
      }}
    >
      <div className="mx-auto flex min-h-0 w-full max-w-[760px] flex-1 flex-col px-5 pb-6 pt-4 lg:px-8 lg:pt-8">
        {/* Top bar */}
        <div className="flex items-center justify-between gap-3">
          <IconButton icon="x" label="Exit cook mode" variant="plain" className="bg-surface" onClick={exit} />
          <div className="min-w-0 text-center">
            <div className="truncate font-serif text-[17px] font-medium">{r.title}</div>
            <div className="mt-0.5 flex items-center justify-center gap-1.5 text-[12px] text-faint">
              {wakeLock && (
                <>
                  <Icon name="sun" size={12} strokeWidth={2.2} />
                  Screen stays on
                </>
              )}
              {wakeLock && servingsNote && <span aria-hidden>·</span>}
              {servingsNote}
            </div>
          </div>
          <IconButton
            icon="list"
            label="All ingredients"
            variant="plain"
            className="bg-surface"
            onClick={() => setShowIngredients(true)}
          />
        </div>

        {/* Progress */}
        <div
          role="progressbar"
          aria-label="Recipe progress"
          aria-valuemin={1}
          aria-valuemax={steps.length}
          aria-valuenow={step + 1}
          className="mt-5 flex gap-1.5"
        >
          {steps.map((_, i) => (
            <button
              key={i}
              type="button"
              aria-label={`Go to step ${i + 1}`}
              onClick={() => setStep(i)}
              className="flex h-4 flex-1 items-center"
            >
              <span className={`h-1 w-full rounded-full ${i <= step ? 'bg-terracotta' : 'bg-line'}`} />
            </button>
          ))}
        </div>

        {/* Running timers */}
        {timers.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2" aria-live="polite">
            {timers.map((t) => {
              const left = t.pausedLeft ?? t.endsAt - now
              const done = left <= 0
              return (
                <div
                  key={t.id}
                  className={`flex h-10 items-center gap-1 rounded-full pl-3.5 pr-1 text-[13.5px] font-bold tab-fig ${
                    done ? 'animate-pulse bg-terracotta text-onaccent' : 'bg-terracotta-soft text-terracotta-deep'
                  }`}
                >
                  <Icon name="clock" size={15} strokeWidth={2.2} />
                  <span className="ml-1">
                    {t.label} · {done ? 'Done!' : mmss(left)}
                  </span>
                  {!done && (
                    <button
                      type="button"
                      onClick={() => togglePause(t)}
                      className="ml-1 h-8 rounded-full px-2 text-[12px] font-semibold underline-offset-2 hover:underline"
                    >
                      {t.pausedLeft != null ? 'Resume' : 'Pause'}
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label={`Dismiss ${t.label} timer`}
                    onClick={() => removeTimer(t)}
                    className="flex h-8 w-8 items-center justify-center rounded-full"
                  >
                    <Icon name="x" size={14} strokeWidth={2.4} />
                  </button>
                </div>
              )
            })}
          </div>
        )}

        {/* Step — scrolls on its own so Back/Next stay put */}
        <div className="no-scrollbar -mx-1 mt-1 min-h-0 flex-1 overflow-y-auto px-1 pb-2">
        <div className="mt-4 text-[12.5px] font-bold uppercase tracking-[.08em] text-terracotta-deep">
          Step {step + 1} of {steps.length}
        </div>
        <p
          key={step}
          className={`mt-3 animate-pop font-serif leading-[1.42] lg:leading-[1.4] ${
            text.length > 320 ? 'text-[20px] lg:text-[26px]' : 'text-[23px] lg:text-[30px]'
          }`}
          aria-live="polite"
        >
          {text}
        </p>

        {uses.length > 0 && (
          <div className="mt-5">
            <div className="text-[11.5px] font-bold uppercase tracking-[.08em] text-faint">For this step</div>
            <ul className="mt-2.5 flex flex-wrap gap-2">
              {uses.map((ing) => {
                const s = renderIngredient(ing, scale.factor, scale.system)
                return (
                  <li
                    key={ing.id}
                    className="rounded-[12px] border border-line bg-surface px-3 py-1.5 text-[14px] leading-snug"
                  >
                    {s.amount && <strong className="font-bold text-terracotta-deep">{s.amount} </strong>}
                    {s.rest}
                  </li>
                )
              })}
            </ul>
          </div>
        )}

        {suggestions.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-[13px] text-faint">Timer</span>
            {suggestions.map((t) => (
              <button
                key={t.seconds}
                type="button"
                onClick={() => startTimer(t.label, t.seconds)}
                className="inline-flex h-10 items-center gap-1.5 rounded-full border border-line px-3.5 text-[13.5px] font-semibold hover:bg-surface"
              >
                <Icon name="clock" size={15} strokeWidth={2.2} />
                {t.label}
              </button>
            ))}
          </div>
        )}

        </div>

        {/* Nav */}
        <div className="mt-3 grid flex-none grid-cols-[1fr_2fr] gap-2.5">
          <Button
            variant="secondary"
            className="h-[58px] !rounded-[18px] !border-line text-[16px]"
            disabled={step === 0}
            onClick={() => go(-1)}
          >
            <Icon name="back" size={18} strokeWidth={2.4} />
            Back
          </Button>
          {step < last ? (
            <Button className="h-[58px] !rounded-[18px] text-[17px] font-bold" onClick={() => go(1)}>
              Next step
              <Icon name="chevronRight" size={18} strokeWidth={2.4} />
            </Button>
          ) : (
            <Button
              className="h-[58px] !rounded-[18px] text-[17px] font-bold"
              busy={cooked.isPending}
              onClick={finish}
            >
              {!cooked.isPending && <Icon name="check" size={18} strokeWidth={2.6} />}
              Done — I cooked it
            </Button>
          )}
        </div>
      </div>

      {/* All-ingredients sheet */}
      {showIngredients && (
        <div
          className="fixed inset-0 z-30 flex items-end justify-center bg-dark/60 sm:items-center sm:p-6"
          onClick={() => setShowIngredients(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="cook-ing-h"
            className="flex max-h-[85vh] w-full max-w-[520px] animate-pop flex-col rounded-t-panel bg-surface sm:rounded-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 pb-2 pt-5">
              <h2 id="cook-ing-h" className="font-serif text-[22px] font-medium">
                Ingredients
              </h2>
              <IconButton icon="x" label="Close" variant="plain" onClick={() => setShowIngredients(false)} />
            </div>
            <div className="overflow-y-auto px-5 pb-6">
              <ScaleControls recipe={r} />
              {groupBySection(r.ingredients).map((group, gi) => (
                <div key={gi}>
                  {group.section && (
                    <h3 className="mt-5 font-serif text-[17px] font-medium">{sectionTitle(group.section)}</h3>
                  )}
                  <ul className={group.section ? 'mt-1' : 'mt-2'}>
                    {group.items.map((ing) => {
                      const s = renderIngredient(ing, scale.factor, scale.system)
                      return (
                        <li key={ing.id} className="border-b border-line py-3 text-[15.5px] leading-[1.4]">
                          {s.amount && <strong className="font-bold">{s.amount} </strong>}
                          {s.rest}
                        </li>
                      )
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
