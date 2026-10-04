// Plan step 4 — done / order report (DESIGN_BRIEF §4.6). Truthful grouped report
// (Added / Substituted / Unavailable), estimated total, the honesty copy
// (FR-18), and the flagship kroger.com handoff CTA. "Save & finish" clears the
// plan so the user can start a fresh one.
import { useMemo } from 'react'
import type { ExecItem, PlanSnapshot } from '../../lib/types'
import { cartHost, money } from '../../lib/format'
import { Button, EmptyState, SectionLabel } from '../../components/ui'
import Icon from '../../components/Icon'
import type { IconName } from '../../components/Icon'
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
      <div className="px-5 py-16">
        <EmptyState icon="receipt" message="No order report available." />
        <Button className="mt-4 h-[52px] w-full text-[15px]" onClick={onFinish}>
          Start a new plan
        </Button>
      </div>
    )
  }

  const totalFailed = exec.status === 'failed'
  const addedCount = groups.added.length + groups.substituted.length
  const lineTotal = (i: ExecItem) => money((i.price ?? 0) * i.quantity)
  // Banner-aware handoff label, e.g. "fredmeyer.com" (API owns the URL mapping).
  const cartLabel = cartHost(exec.kroger_cart_url)

  return (
    <div className="px-5 pb-10 pt-5">
      <div
        className={`mb-4 flex h-16 w-16 items-center justify-center rounded-full ${
          totalFailed ? 'bg-danger-bg text-danger' : 'bg-success-bg text-success'
        }`}
      >
        <Icon name={totalFailed ? 'x' : 'check'} size={30} strokeWidth={2.6} />
      </div>

      <h1 className="font-serif text-[34px] font-medium leading-[1.05] tracking-[-0.02em]">
        {totalFailed ? "We couldn't add your items." : 'Added to your Kroger cart.'}
      </h1>
      {!totalFailed && (
        <div className="mt-2 text-[14px] text-muted">
          Estimated total{' '}
          <b className="tab-fig font-semibold text-ink">{money(exec.estimated_total)}</b> · {addedCount}{' '}
          {addedCount === 1 ? 'item' : 'items'}
        </div>
      )}

      {/* Honesty copy (FR-18) */}
      <div className="my-5 flex gap-2.5 rounded-[14px] border border-warn-border bg-warn-bg px-3.5 py-3 text-[13px] leading-relaxed text-warn-deep">
        <Icon name="info" size={17} className="mt-0.5 flex-none text-warn" />
        <span>
          Items are in your Kroger cart. Review, schedule pickup, and pay on {cartLabel} —{' '}
          <b>Remy can't see or change your cart from here.</b>
        </span>
      </div>

      {totalFailed ? (
        <Button className="h-14 w-full text-[16px] font-bold" onClick={onFinish}>
          Start a new plan
        </Button>
      ) : (
        <a
          href={exec.kroger_cart_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex h-14 items-center justify-center gap-2 rounded-[14px] bg-terracotta px-4 text-center text-[16px] font-bold text-onaccent shadow-terracotta hover:bg-terracotta-dark"
        >
          Finish checkout on {cartLabel}
          <Icon name="external" size={18} strokeWidth={2.4} className="flex-none" />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      )}

      {exec.warnings.map((w, i) => (
        <div key={i} className="mt-3 flex items-start gap-2 text-[12.5px] text-muted">
          <Icon name="info" size={14} className="mt-px flex-none text-faint" />
          {w}
        </div>
      ))}

      <div className="mt-8">
        {groups.added.length > 0 && (
          <ReportGroup label="Added" count={groups.added.length} tone="success" icon="check">
            {groups.added.map((i, idx) => (
              <ReportRow
                key={idx}
                icon="check"
                iconClass="bg-success-bg text-success"
                title={<span className="text-ink">{i.description}</span>}
                sub={titlesByUpc.get(i.upc)?.join(', ')}
                right={<span className="tab-fig text-[14px] font-semibold text-ink">{lineTotal(i)}</span>}
              />
            ))}
          </ReportGroup>
        )}

        {groups.substituted.length > 0 && (
          <ReportGroup
            label="Substituted"
            count={groups.substituted.length}
            tone="warn"
            icon="swap"
          >
            {groups.substituted.map((i, idx) => (
              <ReportRow
                key={idx}
                icon="swap"
                iconClass="bg-warn-bg text-warn"
                title={
                  <span className="text-ink">
                    {i.description}
                    {i.reason && <span className="text-warn"> · {i.reason}</span>}
                  </span>
                }
                sub={titlesByUpc.get(i.upc)?.join(', ')}
                right={<span className="tab-fig text-[14px] font-semibold text-ink">{lineTotal(i)}</span>}
              />
            ))}
          </ReportGroup>
        )}

        {groups.unavailable.length > 0 && (
          <ReportGroup
            label="Unavailable"
            count={groups.unavailable.length}
            tone="danger"
            icon="x"
          >
            {groups.unavailable.map((i, idx) => (
              <ReportRow
                key={idx}
                icon="x"
                iconClass="bg-danger-bg text-danger"
                title={<span className="text-muted">{i.description}</span>}
                right={i.reason && <span className="text-right text-[12px] text-faint">{i.reason}</span>}
              />
            ))}
          </ReportGroup>
        )}
      </div>

      <Button variant="secondary" className="mt-4 h-[52px] w-full text-[15px]" onClick={onFinish}>
        Save &amp; finish
      </Button>
    </div>
  )
}

function ReportGroup({
  label,
  count,
  tone,
  icon,
  children,
}: {
  label: string
  count: number
  tone: 'success' | 'warn' | 'danger'
  icon: IconName
  children: React.ReactNode
}) {
  return (
    <section className="mb-5">
      <SectionLabel tone={tone} className="mb-2.5 flex items-center gap-1.5">
        <Icon name={icon} size={13} strokeWidth={2.6} />
        {label} · <span className="tab-fig">{count}</span>
      </SectionLabel>
      <div className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
        {children}
      </div>
    </section>
  )
}

function ReportRow({
  icon,
  iconClass,
  title,
  sub,
  right,
}: {
  icon: IconName
  iconClass: string
  title: React.ReactNode
  sub?: string
  right?: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-3 border-b border-divider px-3.5 py-3 last:border-0">
      <span className={`flex h-7 w-7 flex-none items-center justify-center rounded-full ${iconClass}`}>
        <Icon name={icon} size={14} strokeWidth={2.6} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] leading-snug">{title}</span>
        {sub && <span className="mt-0.5 block truncate text-[12px] text-faint">{sub}</span>}
      </span>
      {right && <span className="flex-none">{right}</span>}
    </div>
  )
}
