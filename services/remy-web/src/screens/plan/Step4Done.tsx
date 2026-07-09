// Plan step 4 — done / order report (DESIGN_BRIEF §4.6). Truthful grouped report
// (Added ✓ / Substituted ⚠ / Unavailable ✗), estimated total, the honesty copy
// (FR-18), and the flagship kroger.com handoff CTA. "Save & finish" clears the
// plan so the user can start a fresh one.
import { useMemo } from 'react'
import type { ExecItem, PlanSnapshot } from '../../lib/types'
import { money } from '../../lib/format'
import { Button, EmptyState, SectionLabel } from '../../components/ui'
import { sourceFor } from './Step3Cart'

export default function Step4Done({
  snapshot,
  onFinish,
}: {
  snapshot: PlanSnapshot
  onFinish: () => void
}) {
  const exec = snapshot.execution

  // Attribution per executed row: map its UPC back to the cart item's source
  // recipe title(s) (exec items carry only a UPC, cart items carry line_id).
  const titlesByUpc = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const item of snapshot.cart.items) {
      const upc = item.chosen?.upc
      if (!upc) continue
      const src = sourceFor(snapshot, item.line_id)
      if (src && src.titles.length > 0) map.set(upc, src.titles)
    }
    return map
  }, [snapshot])

  const groups = useMemo(() => {
    const items = exec?.items ?? []
    return {
      added: items.filter((i) => i.status === 'added' || i.status === 'stock_unknown'),
      substituted: items.filter((i) => i.status === 'substituted'),
      unavailable: items.filter((i) => i.status === 'failed' || i.status === 'unavailable'),
    }
  }, [exec])

  if (!exec) {
    return (
      <div className="px-[22px] py-16">
        <EmptyState glyph="🧾" message="No order report available." />
        <Button className="mt-4 w-full py-3.5" onClick={onFinish}>
          Start a new plan
        </Button>
      </div>
    )
  }

  const totalFailed = exec.status === 'failed'
  const addedCount = groups.added.length + groups.substituted.length
  const lineTotal = (i: ExecItem) => money((i.price ?? 0) * i.quantity)

  return (
    <div className="px-[22px] pb-9 pt-3.5">
      {totalFailed ? (
        <div className="mb-3.5 flex h-[54px] w-[54px] items-center justify-center rounded-full bg-danger-bg text-[26px] text-danger">
          ✕
        </div>
      ) : (
        <div className="mb-3.5 flex h-[54px] w-[54px] items-center justify-center rounded-full bg-success-bg text-[26px] text-success">
          ✓
        </div>
      )}

      <div className="font-serif text-[28px] font-semibold leading-tight tracking-tight">
        {totalFailed ? "We couldn't add your items." : 'Added to your Kroger cart.'}
      </div>
      {!totalFailed && (
        <div className="mt-1.5 text-sm text-muted">
          Estimated total{' '}
          <b className="tab-fig text-ink">{money(exec.estimated_total)}</b> · {addedCount}{' '}
          {addedCount === 1 ? 'item' : 'items'}
        </div>
      )}

      {/* Honesty copy (FR-18) */}
      <div className="my-4 rounded-[12px] border border-warn-border bg-warn-bg px-3.5 py-3 text-[13px] leading-relaxed text-warn-deep">
        Items are in your Kroger cart. Review, schedule pickup, and pay on kroger.com —{' '}
        <b>Remy can't see or change your cart from here.</b>
      </div>

      {totalFailed ? (
        <Button className="w-full py-4 text-base font-bold" onClick={onFinish}>
          Start a new plan
        </Button>
      ) : (
        <a
          href={exec.kroger_cart_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block rounded-[12px] bg-terracotta py-4 text-center text-base font-bold text-white shadow-terracotta hover:bg-terracotta-dark"
        >
          Finish checkout on kroger.com →
        </a>
      )}

      {exec.warnings.map((w, i) => (
        <div key={i} className="mt-3 text-[12.5px] text-muted">
          {w}
        </div>
      ))}

      <div className="mt-6">
        {groups.added.length > 0 && (
          <ReportGroup label={`Added · ${groups.added.length}`} tone="success">
            {groups.added.map((i, idx) => (
              <div key={idx} className="flex items-center gap-2.5 border-b border-divider px-3.5 py-2.5 last:border-0">
                <span className="text-success">✓</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] text-ink">{i.description}</span>
                  {titlesByUpc.get(i.upc) && (
                    <span className="block truncate text-[11.5px] text-hint">
                      {titlesByUpc.get(i.upc)!.join(', ')}
                    </span>
                  )}
                </span>
                <span className="tab-fig text-[13.5px] font-semibold">{lineTotal(i)}</span>
              </div>
            ))}
          </ReportGroup>
        )}

        {groups.substituted.length > 0 && (
          <ReportGroup label={`Substituted · ${groups.substituted.length}`} tone="warn">
            {groups.substituted.map((i, idx) => (
              <div key={idx} className="flex items-center gap-2.5 border-b border-divider px-3.5 py-2.5 last:border-0">
                <span className="text-warn-dot">⚠</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13.5px] text-ink">
                    {i.description}
                    {i.reason && <span className="text-warn"> · {i.reason}</span>}
                  </span>
                  {titlesByUpc.get(i.upc) && (
                    <span className="block truncate text-[11.5px] text-hint">
                      {titlesByUpc.get(i.upc)!.join(', ')}
                    </span>
                  )}
                </span>
                <span className="tab-fig text-[13.5px] font-semibold">{lineTotal(i)}</span>
              </div>
            ))}
          </ReportGroup>
        )}

        {groups.unavailable.length > 0 && (
          <ReportGroup label={`Unavailable · ${groups.unavailable.length}`} tone="danger">
            {groups.unavailable.map((i, idx) => (
              <div key={idx} className="flex items-center gap-2.5 border-b border-divider px-3.5 py-2.5 last:border-0">
                <span className="text-danger-dot">✕</span>
                <span className="flex-1 text-[13.5px] text-faint">{i.description}</span>
                {i.reason && <span className="text-[12px] text-faint">{i.reason}</span>}
              </div>
            ))}
          </ReportGroup>
        )}
      </div>

      <Button variant="secondary" className="mt-6 w-full py-3.5 text-[14.5px]" onClick={onFinish}>
        Save &amp; finish
      </Button>
    </div>
  )
}

function ReportGroup({
  label,
  tone,
  children,
}: {
  label: string
  tone: 'success' | 'warn' | 'danger'
  children: React.ReactNode
}) {
  return (
    <div className="mb-4">
      <SectionLabel tone={tone} className="mb-2">
        {label}
      </SectionLabel>
      <div className="overflow-hidden rounded-[13px] border border-line bg-surface">{children}</div>
    </div>
  )
}
