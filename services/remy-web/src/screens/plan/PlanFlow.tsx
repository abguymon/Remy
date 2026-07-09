// The one continuous, resumable plan journey (DESIGN_BRIEF §2.3). Reads the
// polling plan-state snapshot, derives the current step from status, and renders
// the matching step screen under a persistent tappable step indicator. Browser
// refresh resumes at the correct step because the step is derived purely from
// the server snapshot.
import { useEffect, useRef, useState } from 'react'
import { usePlanState } from '../../lib/queries'
import type { PlanSnapshot, PlanStatus } from '../../lib/types'
import { Button, Spinner, StepIndicator } from '../../components/ui'
import Step0Input from './Step0Input'
import Step1Pick from './Step1Pick'
import Step2List from './Step2List'
import Step3Cart from './Step3Cart'
import Step4Done from './Step4Done'

function stepForStatus(status: PlanStatus | undefined): number {
  switch (status) {
    case 'discovering':
    case 'selecting':
      return 1
    case 'reviewing_list':
      return 2
    case 'matching':
    case 'reviewing_cart':
    case 'executing':
      return 3
    case 'done':
      return 4
    default:
      return 0 // no plan / abandoned
  }
}

export default function PlanFlow() {
  const { data, isLoading } = usePlanState()

  // Preserve the terminal "done" report: once a plan finishes, GET /plan/state
  // starts 404-ing (done plans aren't "active"), so hold the last done snapshot
  // until the user starts fresh via "Save & finish".
  const [finished, setFinished] = useState<PlanSnapshot | null>(null)
  useEffect(() => {
    if (data?.status === 'done') setFinished(data)
  }, [data])

  const snapshot = data ?? finished
  // A needs-input plan is technically "discovering" but belongs on the input
  // screen (step 0) so the user can re-describe their meals.
  const liveStep = snapshot?.needs_input ? 0 : stepForStatus(snapshot?.status)

  const [viewStep, setViewStep] = useState(liveStep)
  const prevLive = useRef(liveStep)
  useEffect(() => {
    // When the live step advances (or the plan resets), follow it.
    if (prevLive.current !== liveStep) {
      setViewStep(liveStep)
      prevLive.current = liveStep
    }
  }, [liveStep])

  function finishPlan() {
    setFinished(null)
    setViewStep(0)
  }

  if (isLoading && !snapshot) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted">
        <Spinner /> Loading your plan…
      </div>
    )
  }

  const lookingBack = viewStep < liveStep
  const live = viewStep === liveStep

  return (
    <div className="flex min-h-full flex-col">
      <StepIndicator current={viewStep} reachable={liveStep} onStep={setViewStep} />

      {lookingBack && (
        <div className="mx-5 mb-1 flex items-center justify-between gap-2 rounded-[10px] bg-cream px-3 py-2 text-[12px] text-muted ring-1 ring-line">
          <span>You're looking back at a completed step.</span>
          <Button
            variant="ghost"
            className="!p-0 text-[12px] font-semibold text-terracotta"
            onClick={() => setViewStep(liveStep)}
          >
            Back to current →
          </Button>
        </div>
      )}

      {viewStep === 0 && (
        <Step0Input snapshot={snapshot} onResume={() => setViewStep(liveStep)} />
      )}
      {viewStep === 1 && snapshot && <Step1Pick snapshot={snapshot} live={live} />}
      {viewStep === 2 && snapshot && <Step2List snapshot={snapshot} live={live} />}
      {viewStep === 3 && snapshot && <Step3Cart snapshot={snapshot} live={live} />}
      {viewStep === 4 && snapshot && <Step4Done snapshot={snapshot} onFinish={finishPlan} />}
    </div>
  )
}
