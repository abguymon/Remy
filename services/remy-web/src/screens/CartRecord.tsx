// Cart tab (DESIGN_BRIEF §4.9) — Remy's *record*, never a live cart. Permanent
// honesty banner + order history with per-item outcomes and estimated totals.
// The real cart lives on kroger.com (FR-18).
import { useState } from 'react'
import { cartHost, money, shortDate } from '../lib/format'
import { useOrders, useSettings } from '../lib/queries'
import type { OrderItem, OrderRecord } from '../lib/types'
import { EmptyState, ScreenHeader, SectionHeading, StatusPill } from '../components/ui'
import Icon from '../components/Icon'
import type { PillTone } from '../components/ui'

const DEFAULT_CART_URL = 'https://www.kroger.com/cart'

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
  const settings = useSettings()
  // Banner-aware handoff: the API resolves the user's store to its banner cart
  // (e.g. fredmeyer.com); fall back to kroger.com before settings load.
  const cartUrl = settings.data?.cart_url ?? DEFAULT_CART_URL
  const cartLabel = cartHost(cartUrl)
  const count = orders.data?.length ?? 0

  return (
    <div className="pb-12">
      <ScreenHeader title="Cart" subtitle="A log of what Remy added for you" />

      {/* Permanent honesty label (FR-18): a record, not a live cart. */}
      <div className="mx-5 mt-5 flex items-start gap-3 rounded-card border border-line bg-surface p-4 shadow-card">
        <span className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-chip text-muted">
          <Icon name="receipt" size={18} />
        </span>
        <div className="min-w-0 flex-1 text-[13.5px] leading-snug text-muted">
          <div className="font-semibold text-ink">Remy's record — not a live cart</div>
          <div className="mt-0.5">
            Your real cart lives on{' '}
            <a
              href={cartUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-0.5 font-semibold text-terracotta-deep underline-offset-2 hover:underline"
            >
              {cartLabel}
              <Icon name="external" size={13} strokeWidth={2.4} />
            </a>{' '}
            — this is a log of what we added.
          </div>
        </div>
      </div>

      <section className="mt-8 px-5">
        {orders.isLoading ? (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="sk h-[108px] rounded-card" />
            ))}
          </div>
        ) : count === 0 ? (
          <EmptyState icon="cart" message="Nothing ordered yet. Finish a plan and it'll show up here." />
        ) : (
          <>
            <SectionHeading
              className="mb-3"
              sub={`${count} ${count === 1 ? 'order' : 'orders'} · totals are estimates`}
            >
              Order history
            </SectionHeading>
            <div className="flex flex-col gap-3">
              {orders.data!.map((o, i) => (
                <OrderCard
                  key={o.id}
                  order={o}
                  defaultOpen={i === 0}
                  cartUrl={cartUrl}
                  cartLabel={cartLabel}
                />
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  )
}

function OrderCard({
  order,
  defaultOpen,
  cartUrl,
  cartLabel,
}: {
  order: OrderRecord
  defaultOpen: boolean
  cartUrl: string
  cartLabel: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  const items = order.items ?? []

  return (
    <div className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-3 px-4 pb-2 pt-3.5 text-left"
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <div className="font-serif text-[18px] font-medium leading-tight">
              {shortDate(order.created_at) || 'Order'}
            </div>
            <div className="tab-fig text-[15px] font-bold">
              {order.estimated_total != null && (
                <span className="mr-1 text-[11.5px] font-semibold text-faint">est.</span>
              )}
              {money(order.estimated_total)}
            </div>
          </div>
          <div className="mt-1 text-[12.5px] text-faint">{summarize(items)}</div>
        </div>
      </button>
      <div className="flex items-center gap-1 px-2 pb-1.5 text-[13px] font-semibold text-terracotta-deep">
        <button
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="inline-flex min-h-[40px] items-center gap-1 rounded-full px-2"
        >
          {open ? 'Hide items' : 'View items'}
          <Icon
            name="chevronDown"
            size={15}
            strokeWidth={2.4}
            className={`transition-transform ${open ? 'rotate-180' : ''}`}
          />
        </button>
        <span className="text-line2" aria-hidden>
          ·
        </span>
        <a
          href={cartUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-[40px] items-center gap-1 rounded-full px-2"
        >
          Open {cartLabel}/cart
          <Icon name="external" size={14} strokeWidth={2.4} />
        </a>
      </div>

      {open && items.length > 0 && (
        <div className="divide-y divide-divider border-t border-divider">
          {items.map((it, idx) => {
            const o = outcome(it.status)
            return (
              <div key={idx} className="flex items-center gap-2.5 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13.5px] text-ink">
                    {it.description || '—'}
                    {it.quantity > 1 && <span className="text-faint"> ×{it.quantity}</span>}
                  </div>
                  {it.reason && <div className="text-[12px] text-faint">{it.reason}</div>}
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
