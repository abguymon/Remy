// Plan step 3 — review cart (THE FLAGSHIP, DESIGN_BRIEF §5). Stacked product
// cards (never a table), inline swap expander with ≤3 alternatives + manual
// search, substitution self-explain, per-item matching skeletons, not_found
// manual search, scoped item retry, and a sticky live estimated-total bar.
import { useEffect, useState } from 'react'
import { ApiError } from '../../lib/api'
import {
  useCartEdits,
  useExecuteCart,
  useHideUsual,
  useRetry,
  useSettings,
  useUnhideUsual,
  useUsuals,
} from '../../lib/queries'
import type { Alternative, CartEdit, MatchItem, PlanSnapshot, Usual } from '../../lib/types'
import { money, stockLabel } from '../../lib/format'
import { toast } from '../../stores/toast'
import {
  Button,
  CountStepper,
  DegradedBanner,
  Spinner,
  StatusPill,
  StickyBar,
} from '../../components/ui'
import type { PillTone } from '../../components/ui'

const RESOLVED = new Set(['matched', 'substituted', 'stock_unknown', 'not_found', 'failed'])
const IN_CART = new Set(['matched', 'substituted', 'stock_unknown'])

// Recipe attribution for a cart item: the raw ingredient line it came from plus
// the recipe title(s) that contributed it (snapshot carries this via line_id →
// shopping_list.lines[].contributing). Lets the reviewer see *why* an item is in
// the cart — e.g. "1 cup milk (or cream) · Best Mashed Potatoes".
export interface ItemSource {
  raw: string
  titles: string[]
}

export function sourceFor(snapshot: PlanSnapshot, lineId: string): ItemSource | null {
  const line = snapshot.shopping_list.lines.find((l) => l.id === lineId)
  if (!line || line.contributing.length === 0) return null
  const raw = line.contributing[0].raw?.trim() || line.display
  const titles = [...new Set(line.contributing.map((c) => c.recipe_title).filter(Boolean))]
  if (!raw && titles.length === 0) return null
  return { raw, titles }
}

export default function Step3Cart({ snapshot, live }: { snapshot: PlanSnapshot; live: boolean }) {
  const cart = snapshot.cart
  const cartEdits = useCartEdits()
  const executeCart = useExecuteCart()
  const retry = useRetry()
  const settings = useSettings()

  const items = cart.items.filter((it) => it.status !== 'dropped')
  const matching = cart.status === 'matching'
  const resolvedCount = cart.items.filter((it) => RESOLVED.has(it.status)).length
  const inCart = items.filter((it) => IN_CART.has(it.status))
  const itemCount = inCart.reduce((n, it) => n + it.count, 0)
  const storeName = settings.data?.store_name ?? 'your store'

  async function applyEdit(op: CartEdit) {
    try {
      await cartEdits.mutateAsync([op])
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Edit failed.')
    }
  }

  async function onExecute() {
    try {
      await executeCart.mutateAsync()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'kroger_not_connected') {
        toast('Connect your Kroger account in Settings to place the order.')
      } else {
        toast(err instanceof ApiError ? err.message : 'Could not add items.')
      }
    }
  }

  async function retryItem(itemId: string) {
    try {
      await retry.mutateAsync({ scope: 'item', id: itemId })
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Retry failed.')
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="no-scrollbar flex-1 overflow-y-auto px-[18px] pb-8 pt-2">
        <div className="font-serif text-[26px] font-semibold tracking-tight">Review your cart</div>
        {matching ? (
          <div className="mt-1 flex items-center gap-2 text-[13.5px] text-muted">
            <Spinner /> Matching products at {storeName} — {resolvedCount} of {cart.items.length}{' '}
            matched
          </div>
        ) : (
          <div className="mt-1 text-[13.5px] text-muted">
            Prices from {storeName}. Review before we add anything.
          </div>
        )}

        {cart.warnings.map((w, i) => (
          <div key={i} className="mt-3">
            <DegradedBanner>{w}</DegradedBanner>
          </div>
        ))}

        <div className="mt-4 flex flex-col gap-3">
          {items.map((item) => (
            <CartItemCard
              key={item.id}
              item={item}
              source={sourceFor(snapshot, item.line_id)}
              live={live}
              busy={cartEdits.isPending || retry.isPending}
              onSetCount={(n) => applyEdit({ op: 'set_count', item_id: item.id, count: n })}
              onSwap={(altId) =>
                applyEdit({ op: 'swap', item_id: item.id, alternative_id: altId })
              }
              onDrop={() => applyEdit({ op: 'drop', item_id: item.id })}
              onManualSearch={(term) =>
                applyEdit({ op: 'manual_search', item_id: item.id, term })
              }
              onRetry={() => retryItem(item.id)}
            />
          ))}
        </div>
      </div>

      {live && !matching && (
        <UsualsStrip snapshot={snapshot} onAdd={(upc) => applyEdit({ op: 'add_upc', upc })} />
      )}

      <StickyBar>
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-[13px] text-muted">
            Estimated total · {itemCount} {itemCount === 1 ? 'item' : 'items'}
          </span>
          <span className="tab-fig font-serif text-[22px] font-semibold text-ink">
            {money(cart.estimated_total)}
          </span>
        </div>
        <Button
          className="w-full py-3.5 text-[15.5px] font-bold"
          disabled={!live || matching || itemCount === 0 || executeCart.isPending}
          onClick={onExecute}
        >
          {executeCart.isPending
            ? 'Adding to Kroger cart…'
            : `Add ${itemCount} ${itemCount === 1 ? 'item' : 'items'} to Kroger cart`}
        </Button>
      </StickyBar>
    </div>
  )
}

function CartItemCard({
  item,
  source,
  live,
  busy,
  onSetCount,
  onSwap,
  onDrop,
  onManualSearch,
  onRetry,
}: {
  item: MatchItem
  source: ItemSource | null
  live: boolean
  busy: boolean
  onSetCount: (n: number) => void
  onSwap: (alternativeId: string) => void
  onDrop: () => void
  onManualSearch: (term: string) => void
  onRetry: () => void
}) {
  const [swapOpen, setSwapOpen] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [manualText, setManualText] = useState('')
  const [count, setCount] = useState(item.count)
  useEffect(() => setCount(item.count), [item.count])

  // --- pending / matching → skeleton --------------------------------------
  if (item.status === 'pending' || item.status === 'matching') {
    return (
      <div className="overflow-hidden rounded-[15px] border border-line bg-surface shadow-card">
        <div className="flex gap-3 p-3.5">
          <div className="sk h-[66px] w-[66px] flex-none rounded-[11px]" />
          <div className="flex-1">
            <div className="sk h-3.5 w-[85%] rounded" />
            <div className="sk mt-2 h-3 w-[40%] rounded" />
            <div className="sk mt-3 h-5 w-20 rounded-md" />
          </div>
        </div>
      </div>
    )
  }

  const chosen = item.chosen
  const notFound = item.status === 'not_found'
  const failed = item.status === 'failed'

  // --- failed → scoped retry ----------------------------------------------
  if (failed) {
    return (
      <div className="overflow-hidden rounded-[15px] border border-line bg-surface shadow-card">
        <div className="p-3.5">
          <DegradedBanner tone="danger" onRetry={live ? onRetry : undefined} retrying={busy}>
            Matching failed for "{item.search_term}"{item.error ? ` — ${item.error}` : ''}.
          </DegradedBanner>
        </div>
      </div>
    )
  }

  const pill = pillFor(item)

  return (
    <div className="overflow-hidden rounded-[15px] border border-line bg-surface shadow-card">
      <div className="p-3.5">
        <div className="flex gap-3">
          <div className="flex h-[66px] w-[66px] flex-none items-center justify-center rounded-[11px] border border-tile bg-white">
            {notFound ? (
              <span className="text-2xl text-danger-dot">?</span>
            ) : chosen?.image_url ? (
              <img
                src={chosen.image_url}
                alt=""
                className="h-full w-full rounded-[11px] object-contain p-1"
              />
            ) : (
              <span className="font-mono text-[9px] text-hint">product</span>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex justify-between gap-2">
              <div className="text-[14px] font-semibold leading-snug text-ink">
                {notFound ? item.search_term : (chosen?.description ?? item.search_term)}
              </div>
              <div className="tab-fig whitespace-nowrap text-[14.5px] font-bold text-ink">
                {notFound ? '—' : money(chosen?.price)}
              </div>
            </div>
            {chosen?.size && <div className="mt-0.5 text-[12px] text-faint">{chosen.size}</div>}
            {source && <SourceLine source={source} />}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <StatusPill tone={pill.tone}>{pill.label}</StatusPill>
              {item.is_usual && (
                <span className="inline-flex items-center gap-1 rounded-md bg-badge-favbg px-2 py-[3px] text-[11px] font-semibold text-badge-favfg">
                  ★ Your usual
                </span>
              )}
              {item.status === 'substituted' && (
                <span className="text-[11px] text-warn">wanted: {item.search_term}</span>
              )}
            </div>
          </div>
        </div>

        {/* not_found → manual search */}
        {notFound && live && (
          <div className="mt-3 rounded-[10px] bg-danger-bg p-3">
            <div className="mb-2 text-[12.5px] font-semibold text-danger">
              Couldn't find "{item.search_term}" at your store.
            </div>
            <div className="flex gap-2">
              <input
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
                placeholder="Search for it manually"
                className="flex-1 rounded-[8px] border border-danger-border bg-surface px-2.5 py-2 text-[12.5px] outline-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && manualText.trim()) onManualSearch(manualText.trim())
                }}
              />
              <button
                onClick={() => manualText.trim() && onManualSearch(manualText.trim())}
                className="rounded-[8px] bg-danger px-3 py-2 text-[12.5px] font-semibold text-white"
              >
                Search
              </button>
            </div>
          </div>
        )}

        {/* actions row */}
        {!notFound && (
          <div className="mt-3 flex items-center gap-2.5 border-t border-divider pt-3">
            <CountStepper
              count={count}
              onChange={(n) => {
                setCount(n)
                if (live) onSetCount(n)
              }}
            />
            <div className="flex-1" />
            {live && item.alternatives.length > 0 && (
              <Button
                variant="secondary"
                className="px-3 py-2 text-[12.5px]"
                onClick={() => setSwapOpen((v) => !v)}
              >
                Swap
              </Button>
            )}
            {live && (
              <Button variant="danger" className="px-3 py-2 text-[12.5px]" onClick={onDrop}>
                Remove
              </Button>
            )}
          </div>
        )}

        {/* swap expander */}
        {swapOpen && !notFound && (
          <div className="mt-3 rounded-[11px] bg-cream p-2.5">
            <div className="mb-2 pl-0.5 text-[11px] font-bold uppercase tracking-[.05em] text-faint">
              Other matches
            </div>
            <div className="flex flex-col gap-1.5">
              {item.alternatives.map((alt) => (
                <AltRow
                  key={alt.alternative_id}
                  alt={alt}
                  onChoose={() => {
                    onSwap(alt.alternative_id)
                    setSwapOpen(false)
                  }}
                />
              ))}
              {manualOpen ? (
                <div className="flex gap-2 pt-1">
                  <input
                    autoFocus
                    value={manualText}
                    onChange={(e) => setManualText(e.target.value)}
                    placeholder="Search for something else"
                    className="flex-1 rounded-[8px] border border-line2 bg-surface px-2.5 py-2 text-[12.5px] outline-none focus:border-terracotta"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && manualText.trim()) {
                        onManualSearch(manualText.trim())
                        setSwapOpen(false)
                      }
                    }}
                  />
                  <Button
                    className="px-3 py-2 text-[12.5px]"
                    disabled={!manualText.trim()}
                    onClick={() => {
                      onManualSearch(manualText.trim())
                      setSwapOpen(false)
                    }}
                  >
                    Search
                  </Button>
                </div>
              ) : (
                <button
                  onClick={() => setManualOpen(true)}
                  className="rounded-[10px] border border-dashed border-line2 py-2.5 text-[12.5px] font-semibold text-muted hover:text-ink"
                >
                  Search for something else
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// Muted attribution line: the raw ingredient text (truncated) · recipe title(s).
function SourceLine({ source }: { source: ItemSource }) {
  const suffix = source.titles.length > 0 ? ` · ${source.titles.join(', ')}` : ''
  return (
    <div className="mt-1 truncate text-[11.5px] text-hint" title={`${source.raw}${suffix}`}>
      <span className="italic">{source.raw}</span>
      {suffix}
    </div>
  )
}

function AltRow({ alt, onChoose }: { alt: Alternative; onChoose: () => void }) {
  return (
    <button
      onClick={onChoose}
      className="flex items-center gap-2.5 rounded-[10px] border border-line bg-surface p-2.5 text-left"
    >
      <span className="flex h-10 w-10 flex-none items-center justify-center overflow-hidden rounded-[8px] border border-tile bg-white">
        {alt.image_url ? (
          <img src={alt.image_url} alt="" className="h-full w-full object-contain p-0.5" />
        ) : (
          <span className="font-mono text-[8px] text-hint">img</span>
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] font-semibold leading-tight text-ink">
          {alt.description}
        </span>
        {alt.size && <span className="block text-[11.5px] text-faint">{alt.size}</span>}
      </span>
      <span className="tab-fig text-[13.5px] font-bold">{money(alt.price)}</span>
    </button>
  )
}

// "Add your usuals?" — a horizontal strip of remembered products NOT already in
// the current cart draft (compared by UPC, including dropped items). Tapping a
// chip appends it via the add_upc cart edit; the chip's ✕ hides it (with undo).
// Renders nothing when there is nothing to suggest (cold-start silence).
function UsualsStrip({
  snapshot,
  onAdd,
}: {
  snapshot: PlanSnapshot
  onAdd: (upc: string) => void
}) {
  const usuals = useUsuals(24)
  const hide = useHideUsual()
  const unhide = useUnhideUsual()

  // Every UPC currently represented in the draft — dropped lines included, so a
  // just-removed item isn't re-suggested back at the user.
  const inCart = new Set(
    snapshot.cart.items.map((it) => it.chosen?.upc).filter((u): u is string => !!u),
  )
  const suggestions = (usuals.data ?? []).filter((u) => !inCart.has(u.upc))
  if (suggestions.length === 0) return null

  async function onHide(u: Usual) {
    try {
      await hide.mutateAsync(u.upc)
      toast(`Hid ${u.description ?? 'usual'}`, {
        label: 'Undo',
        run: () => {
          unhide.mutate(u.upc)
        },
      })
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not hide.')
    }
  }

  return (
    <div className="flex-none border-t border-line bg-surface/95 px-[18px] pb-1 pt-3">
      <div className="mb-2 text-[11px] font-bold uppercase tracking-[.05em] text-faint">
        Add your usuals?
      </div>
      <div className="no-scrollbar -mx-[18px] flex gap-2.5 overflow-x-auto px-[18px] pb-2">
        {suggestions.map((u) => (
          <UsualChip key={`${u.food_key}-${u.upc}`} usual={u} onAdd={() => onAdd(u.upc)} onHide={() => onHide(u)} />
        ))}
      </div>
    </div>
  )
}

function UsualChip({
  usual,
  onAdd,
  onHide,
}: {
  usual: Usual
  onAdd: () => void
  onHide: () => void
}) {
  return (
    <div className="relative w-[112px] flex-none">
      <button
        onClick={onAdd}
        className="flex w-full flex-col items-center gap-1.5 rounded-[13px] border border-line2 bg-cream/60 p-2.5 text-center hover:border-terracotta"
      >
        <span className="flex h-[52px] w-[52px] items-center justify-center overflow-hidden rounded-[10px] border border-tile bg-white">
          {usual.image_url ? (
            <img src={usual.image_url} alt="" className="h-full w-full object-contain p-1" />
          ) : (
            <span className="font-mono text-[8px] text-hint">img</span>
          )}
        </span>
        <span className="line-clamp-2 text-[11.5px] font-semibold leading-tight text-ink">
          {usual.description ?? usual.food_key}
        </span>
        <span className="tab-fig text-[11.5px] font-bold text-terracotta">
          {usual.last_price != null ? `＋ ${money(usual.last_price)}` : '＋ Add'}
        </span>
      </button>
      <button
        aria-label={`Hide ${usual.description ?? usual.food_key}`}
        onClick={onHide}
        className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-line2 bg-surface text-[10px] leading-none text-muted shadow-sm"
      >
        ✕
      </button>
    </div>
  )
}

function pillFor(item: MatchItem): { tone: PillTone; label: string } {
  switch (item.status) {
    case 'substituted':
      return { tone: 'warn', label: 'Substituted' }
    case 'stock_unknown':
      return { tone: 'warn', label: 'Stock unknown' }
    case 'not_found':
      return { tone: 'danger', label: 'Not found' }
    case 'matched': {
      const level = (item.chosen?.stock_level ?? '').toUpperCase()
      if (level === 'LOW') return { tone: 'warn', label: 'Low stock' }
      return { tone: 'success', label: stockLabel(item.chosen?.stock_level) }
    }
    default:
      return { tone: 'neutral', label: item.status }
  }
}
