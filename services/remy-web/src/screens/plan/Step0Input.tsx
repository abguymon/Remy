// Plan step 0 — the emotional start (DESIGN_BRIEF §4.2). Meal input, first-run
// explainer, Kroger-not-connected notice, resume card for an in-flight plan,
// and the needs_input reprompt.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../lib/api'
import { useAbandonPlan, useCreatePlan, useKrogerStatus } from '../../lib/queries'
import type { PlanSnapshot } from '../../lib/types'
import { toast } from '../../stores/toast'
import { Button, ConfirmDialog, SectionLabel } from '../../components/ui'

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
      <div className="px-[22px] pb-10 pt-3">
        <div className="my-2 font-serif text-[30px] font-semibold leading-tight tracking-tight">
          Welcome back.
        </div>
        <div className="mb-5 text-[14.5px] text-muted">
          You're mid-plan — pick up where you left off.
        </div>
        <div className="rounded-panel border border-line bg-surface p-[18px] shadow-card">
          <SectionLabel tone="terracotta" className="mb-2.5">
            In progress
          </SectionLabel>
          <div className="mb-4 flex gap-4">
            <div>
              <div className="tab-fig font-serif text-[26px] font-semibold">{picked}</div>
              <div className="text-xs text-muted">recipes picked</div>
            </div>
            <div className="w-px bg-line" />
            <div>
              <div className="font-serif text-[26px] font-semibold leading-tight">
                {PHASE_LABEL[status ?? ''] ?? 'In progress'}
              </div>
              <div className="text-xs text-muted">current step</div>
            </div>
          </div>
          <Button className="w-full py-3.5 text-[15px]" onClick={onResume}>
            Continue plan
          </Button>
          <Button
            variant="danger"
            className="mt-2 w-full py-2.5 text-[13.5px]"
            onClick={() => setConfirmReset(true)}
          >
            Start over
          </Button>
          <div className="mt-2 text-center text-[11.5px] text-fainter">
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
    <div className="px-[22px] pb-10 pt-3">
      {needsInput && (
        <div className="mb-3 rounded-[12px] border border-warn-border bg-warn-bg px-3.5 py-3 text-[13px] text-warn">
          We couldn't pick out any meals from that. Try naming the dishes you want to cook — e.g.
          "chicken tikka masala and street tacos".
        </div>
      )}

      <div className="mb-1.5 mt-3 font-serif text-[31px] font-semibold leading-tight tracking-tight">
        What are we cooking this week?
      </div>
      <div className="mb-4 text-[14.5px] text-muted">
        List meals in plain words, or paste a recipe link — we'll find options for each.
      </div>

      {krogerQuery.isSuccess && !krogerConnected && (
        <div className="mb-3 rounded-[12px] border border-warn-border bg-warn-bg px-3.5 py-3 text-[13px] text-warn">
          Kroger isn't connected yet — you can plan, but not order.{' '}
          <Link to="/settings" className="font-semibold underline">
            Connect in Settings
          </Link>
          .
        </div>
      )}

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="e.g. chicken tikka masala, some kind of salmon bowl, and street tacos on Friday"
        className="min-h-[130px] w-full resize-none rounded-[14px] border border-line2 bg-surface p-4 text-[15px] leading-relaxed shadow-cardsoft outline-none focus:border-terracotta"
      />
      <Button
        className="mt-3 w-full py-3.5 text-[15.5px] font-bold"
        onClick={submit}
        disabled={!text.trim() || createPlan.isPending}
      >
        {createPlan.isPending ? 'Finding recipes…' : 'Find recipes →'}
      </Button>

      <div className="mt-5 rounded-[14px] border border-line bg-surface p-4">
        <SectionLabel className="mb-3">How Remy works</SectionLabel>
        <div className="flex flex-col gap-3">
          {[
            'Pick a recipe for each meal from ~5 options.',
            'We build one shopping list and match each item to a real Kroger product.',
            'Review, then we fill your cart — you check out on kroger.com.',
          ].map((line, i) => (
            <div key={i} className="flex gap-3">
              <span className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-full bg-terracotta-soft font-serif text-[13px] font-semibold text-terracotta-deep">
                {i + 1}
              </span>
              <div className="pt-0.5 text-[13.5px] leading-snug text-ink/90">{line}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
