// Cart tab (DESIGN_BRIEF §4.9) — Remy's *record*, never a live cart. Permanent
// honesty banner + order history with per-item outcomes and estimated totals.
// The real cart lives on kroger.com (FR-18).
import { useState } from 'react'
import { money, shortDate } from '../lib/format'
import { useOrders } from '../lib/queries'
import type { OrderItem, OrderRecord } from '../lib/types'
import { EmptyState, StatusPill } from '../components/ui'
import type { PillTone } from '../components/ui'

const KROGER_CART_URL = 'https://www.kroger.com/cart'

function outcome(status: string): { tone: PillTone; label: string; added: boolean } {
  switch (status) {
    case 'added':
      return { tone: 'success', label: 'Added', added: true }
    case 'stock_unknown':
      return { tone: 'success', label: 'Added', added: true }
    case 'substituted':
      return { tone: 'warn', label: 'Substituted', added: true }
    case 'failed':
      return { tone: 'danger', label: 'Failed', added: false }
    default:
      return { tone: 'danger', label: 'Unavailable', added: false }
  }
}

function summarize(items: OrderItem[]): string {
  let added = 0
  let substituted = 0
  let unavailable = 0
  for (const it of items) {
    const o = outcome(it.status)
    if (it.status === 'substituted') substituted += 1
    else if (o.added) added += 1
    else unavailable += 1
  }
  const parts = [`${added} added`]
  if (substituted) parts.push(`${substituted} substituted`)
  if (unavailable) parts.push(`${unavailable} unavailable`)
  return parts.join(' · ')
}

export default function CartRecord() {
  const orders = useOrders()

  return (
    <div className="px-5 pb-8 pt-3.5">
      <div className="font-serif text-[28px] font-semibold tracking-tight">Cart</div>

      <div className="my-3.5 rounded-[12px] border border-line2 bg-badge-favbg px-3.5 py-3 text-[12.5px] leading-snug text-muted">
        <b className="text-ink">Remy's record.</b> Your real cart lives on{' '}
        <a
          href={KROGER_CART_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold text-terracotta"
        >
          kroger.com
        </a>{' '}
        — this is a log of what we added, not a live cart.
      </div>

      {orders.isLoading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="sk h-[92px] rounded-card" />
          ))}
        </div>
      ) : (orders.data?.length ?? 0) === 0 ? (
        <EmptyState glyph="🛒" message="Nothing ordered yet. Finish a plan and it'll show up here." />
      ) : (
        <>
          <div className="mb-2 text-xs font-bold uppercase tracking-[.06em] text-hint">
            Order history
          </div>
          <div className="flex flex-col gap-2.5">
            {orders.data!.map((o, i) => (
              <OrderCard key={o.id} order={o} defaultOpen={i === 0} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function OrderCard({ order, defaultOpen }: { order: OrderRecord; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const items = order.items ?? []

  return (
    <div className="overflow-hidden rounded-card border border-line bg-surface shadow-cardsoft">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full px-4 py-3.5 text-left"
        aria-expanded={open}
      >
        <div className="flex items-baseline justify-between gap-3">
          <div className="text-[15px] font-semibold">{shortDate(order.created_at) || 'Order'}</div>
          <div className="tab-fig text-[15px] font-bold">{money(order.estimated_total)}</div>
        </div>
        <div className="mt-0.5 text-[12.5px] text-faint">{summarize(items)}</div>
        <div className="mt-2 flex items-center gap-2 text-[12.5px]">
          <span className="font-semibold text-terracotta">{open ? 'Hide items' : 'View items'}</span>
          <span className="text-line2">·</span>
          <a
            href={KROGER_CART_URL}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="font-semibold text-terracotta"
          >
            Open kroger.com/cart
          </a>
        </div>
      </button>

      {open && items.length > 0 && (
        <div className="border-t border-divider">
          {items.map((it, idx) => {
            const o = outcome(it.status)
            return (
              <div
                key={idx}
                className="flex items-center gap-2.5 border-b border-divider px-4 py-2.5 last:border-0"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13.5px] text-ink">
                    {it.description || '—'}
                    {it.quantity > 1 && <span className="text-faint"> ×{it.quantity}</span>}
                  </div>
                  {it.reason && <div className="text-[11.5px] text-faint">{it.reason}</div>}
                </div>
                {it.price != null && o.added && (
                  <span className="tab-fig text-[13px] font-semibold">
                    {money(it.price * it.quantity)}
                  </span>
                )}
                <StatusPill tone={o.tone}>{o.label}</StatusPill>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
