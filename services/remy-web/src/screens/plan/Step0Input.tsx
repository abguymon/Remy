// Plan step 0 — the emotional start (DESIGN_BRIEF §4.2). Meal input, first-run
// explainer, Kroger-not-connected notice, resume card for an in-flight plan,
// and the needs_input reprompt.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../lib/api'
import { useAbandonPlan, useCreatePlan, useKrogerStatus } from '../../lib/queries'
import type { PlanSnapshot } from '../../lib/types'
import { toast } from '../../stores/toast'
import { Button, ConfirmDialog, DegradedBanner, ScreenHeader, SectionLabel } from '../../components/ui'
import Icon from '../../components/Icon'
import type { IconName } from '../../components/Icon'

const HOW_IT_WORKS: { icon: IconName; text: string }[] = [
  { icon: 'utensils', text: 'Pick a recipe for each meal from ~5 options.' },
  {
    icon: 'list',
    text: 'We build one shopping list and match each item to a real Kroger product.',
  },
  { icon: 'cart', text: 'Review, then we fill your cart — you check out on kroger.com.' },
]

const PHASE_LABEL: Record<string, string> = {
  discovering: 'Finding recipes',
  selecting: 'Pick recipes',
  reviewing_list: 'Review list',
  matching: 'Matching products',
  reviewing_cart: 'Review cart',
  executing: 'Placing order',
}

export default function Step0Input({
  snapshot,
  onResume,
}: {
  snapshot: PlanSnapshot | null
  onResume: () => void
}) {
  const [text, setText] = useState('')
  const [confirmReset, setConfirmReset] = useState(false)
  const createPlan = useCreatePlan()
  const abandon = useAbandonPlan()
  const krogerQuery = useKrogerStatus()

  const status = snapshot?.status
  const needsInput = !!snapshot?.needs_input
  const inFlight = !!snapshot && !needsInput && status !== 'done' && status !== 'abandoned'

  async function submit() {
    if (!text.trim()) return
    try {
      await createPlan.mutateAsync(text.trim())
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not start the plan.')
    }
  }

  async function startOver() {
    setConfirmReset(false)
    try {
      await abandon.mutateAsync()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not start over.')
    }
  }

  // --- resume card ---------------------------------------------------------
  if (inFlight) {
    const picked = Object.values(snapshot!.selections).filter((s) => s.status === 'saved').length
    return (
      <div className="pb-10">
        <ScreenHeader
          className="!pt-4"
          title="Welcome back."
          subtitle="You're mid-plan — pick up where you left off."
        />
        <div className="mx-5 mt-5 rounded-panel border border-line bg-surface p-5 shadow-card">
          <SectionLabel tone="terracotta" className="mb-3 flex items-center gap-1.5 !text-terracotta-deep">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-terracotta" aria-hidden />
            In progress
          </SectionLabel>
          <div className="mb-5 grid grid-cols-[auto_1px_1fr] items-end gap-x-4">
            <div className="tab-fig font-serif text-[34px] font-medium leading-none tracking-[-0.02em]">
              {picked}
            </div>
            <div className="row-span-2 self-stretch bg-line" />
            <div className="min-w-0 font-serif text-[26px] font-medium leading-[1.05] tracking-[-0.01em]">
              {PHASE_LABEL[status ?? ''] ?? 'In progress'}
            </div>
            <div className="mt-1.5 text-[12.5px] text-muted">recipes picked</div>
            <div className="mt-1.5 text-[12.5px] text-muted">current step</div>
          </div>
          <Button className="h-[54px] w-full text-[16px] font-bold" onClick={onResume}>
            Continue plan
            <Icon name="chevronRight" size={18} strokeWidth={2.4} />
          </Button>
          <Button
            variant="danger"
            className="mt-2.5 h-11 w-full text-[14px]"
            onClick={() => setConfirmReset(true)}
          >
            Start over
          </Button>
          <div className="mt-2.5 text-center text-[12px] text-faint">
            Starting over discards this plan. Your saved recipes are kept.
          </div>
        </div>
        <ConfirmDialog
          open={confirmReset}
          title="Start over?"
          body="This discards your current plan. Recipes you've already picked stay in your cookbook."
          confirmLabel="Start over"
          destructive
          onConfirm={startOver}
          onCancel={() => setConfirmReset(false)}
        />
      </div>
    )
  }

  // --- meal input ----------------------------------------------------------
  const krogerConnected = krogerQuery.data?.connected

  return (
    <div className="pb-10">
      {needsInput && (
        <div className="mx-5 mt-3">
          <DegradedBanner>
            We couldn't pick out any meals from that. Try naming the dishes you want to cook — e.g.
            "chicken tikka masala and street tacos".
          </DegradedBanner>
        </div>
      )}

      <ScreenHeader
        className="!pt-4"
        title="What are we cooking this week?"
        subtitle="List meals in plain words, or paste a recipe link — we'll find options for each."
      />

      <div className="px-5 pt-5">
        {krogerQuery.isSuccess && !krogerConnected && (
          <div className="mb-3">
            <DegradedBanner>
              Kroger isn't connected yet — you can plan, but not order.{' '}
              <Link to="/app/settings" className="font-semibold underline underline-offset-2">
                Connect in Settings
              </Link>
              .
            </DegradedBanner>
          </div>
        )}

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Meals to cook this week"
          placeholder="e.g. chicken tikka masala, some kind of salmon bowl, and street tacos on Friday"
          className="block min-h-[150px] w-full resize-none rounded-card border border-line2 bg-surface px-4 py-3.5 text-[16px] leading-relaxed text-ink shadow-card outline-none transition-colors placeholder:text-faint focus:border-terracotta"
        />
        <Button
          className="mt-3 h-[54px] w-full text-[16px] font-bold"
          onClick={submit}
          busy={createPlan.isPending}
          disabled={!text.trim() || createPlan.isPending}
        >
          {createPlan.isPending ? (
            'Finding recipes…'
          ) : (
            <>
              Find recipes
              <Icon name="chevronRight" size={18} strokeWidth={2.4} />
            </>
          )}
        </Button>

        <section aria-labelledby="how-remy-works" className="mt-9">
          <h2
            id="how-remy-works"
            className="font-serif text-[22px] font-medium tracking-[-0.01em]"
          >
            How Remy works
          </h2>
          <ol className="mt-3 overflow-hidden rounded-card border border-line bg-surface">
            {HOW_IT_WORKS.map((step, i) => (
              <li
                key={i}
                className="flex items-center gap-3.5 border-b border-divider px-4 py-3.5 last:border-0"
              >
                <span className="relative flex h-11 w-11 flex-none items-center justify-center rounded-full bg-terracotta-soft text-terracotta-deep">
                  <Icon name={step.icon} size={19} strokeWidth={1.9} />
                  <span className="tab-fig absolute -right-1 -top-1 flex h-[18px] w-[18px] items-center justify-center rounded-full border-2 border-surface bg-terracotta text-[10px] font-bold text-onaccent">
                    {i + 1}
                  </span>
                </span>
                <div className="text-[14px] leading-snug text-ink">{step.text}</div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  )
}
