// Plan step 3 — review cart (THE FLAGSHIP, DESIGN_BRIEF §5). Stacked product
// cards (never a table), inline swap expander with ≤3 alternatives + manual
// search, substitution self-explain, "Not sure — check this" for low-confidence
// picks (alternatives open, "Keep this one" confirms), per-item matching
// skeletons, not_found manual search, scoped item retry, and a sticky live
// estimated-total bar.
import { useEffect, useRef, useState } from 'react'
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
  ScreenHeader,
  SectionLabel,
  Spinner,
  StatusPill,
  StickyBar,
} from '../../components/ui'
import Icon from '../../components/Icon'
import type { PillTone } from '../../components/ui'

const RESOLVED = new Set(['matched', 'substituted', 'stock_unknown', 'not_found', 'failed'])
const IN_CART = new Set(['matched', 'substituted', 'stock_unknown'])
// Below this the ranker's pick was right only ~1 time in 3 on past orders
// (scripts/eval_product_ranking.py), so ask the shopper to check it.
const UNSURE_BELOW = 0.6

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
      <div className="no-scrollbar flex-1 overflow-y-auto pb-8">
        <ScreenHeader
          className="!pt-4"
          title="Review your cart"
          subtitle={
            matching ? (
              <span className="flex items-center gap-2">
                <Spinner /> Matching products at {storeName} — {resolvedCount} of {cart.items.length}{' '}
                matched
              </span>
            ) : (
              `Prices from ${storeName}. Review before we add anything.`
            )
          }
        />
        {matching && (
          <div
            className="mx-5 mt-3 h-1 overflow-hidden rounded-full bg-chip"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={cart.items.length}
            aria-valuenow={resolvedCount}
          >
            <div
              className="h-full rounded-full bg-terracotta transition-[width] duration-500"
              style={{
                width: `${cart.items.length ? (resolvedCount / cart.items.length) * 100 : 0}%`,
              }}
            />
          </div>
        )}

        <div className="px-4 sm:px-5">
          {cart.warnings.map((w, i) => (
            <div key={i} className="mt-3">
              <DegradedBanner>{w}</DegradedBanner>
            </div>
          ))}

          <div className="mt-5 flex flex-col gap-3">
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
                onConfirm={() => applyEdit({ op: 'confirm', item_id: item.id })}
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
      </div>

      {/* Pinned to the bottom of the app's scrolling <main> so the action
          (and the live total) stays in reach while the list scrolls. */}
      <div className="sticky bottom-0 z-10">
        <StickyBar>
          <div className="mb-2.5 flex items-baseline justify-between gap-3">
            <span className="text-[13px] text-muted">
              <span className="font-semibold text-ink">Estimated total</span> · {itemCount}{' '}
              {itemCount === 1 ? 'item' : 'items'}
            </span>
            <span className="tab-fig font-serif text-[26px] font-medium leading-none tracking-[-0.01em] text-ink">
              {money(cart.estimated_total)}
            </span>
          </div>
          <Button
            className="h-[54px] w-full text-[16px] font-bold"
            busy={executeCart.isPending}
            disabled={!live || matching || itemCount === 0 || executeCart.isPending}
            onClick={onExecute}
          >
            {executeCart.isPending ? (
              'Adding to Kroger cart…'
            ) : (
              <>
                <Icon name="cart" size={19} strokeWidth={2.2} />
                {`Add ${itemCount} ${itemCount === 1 ? 'item' : 'items'} to Kroger cart`}
              </>
            )}
          </Button>
        </StickyBar>
      </div>
    </div>
  )
}

// Product photo tile. Kroger product shots are JPEGs on a baked-in white
// background, so the tile stays light in BOTH themes (surface in light, the
// warm off-white `ink` token in dark) and the image uses multiply blending so
// its white box melts into the tile instead of showing as a hard rectangle.
// A dark tile would either frame a glaring white square or (with multiply)
// muddy the product colors.
const PRODUCT_TILE = 'border border-tile bg-producttile dark:border-transparent'

function ProductThumb({
  src,
  size,
  radius = 'rounded-[12px]',
}: {
  src: string | null | undefined
  size: number
  radius?: string
}) {
  if (!src) {
    return (
      <span
        className={`flex flex-none items-center justify-center bg-chip text-faint ${radius}`}
        style={{ width: size, height: size }}
        role="img"
        aria-label="No product photo"
      >
        <Icon name="bag" size={Math.round(size * 0.36)} strokeWidth={1.7} />
      </span>
    )
  }
  return (
    <span
      className={`flex flex-none items-center justify-center overflow-hidden ${PRODUCT_TILE} ${radius}`}
      style={{ width: size, height: size }}
    >
      <img src={src} alt="" className="h-full w-full object-contain p-1 mix-blend-multiply" />
    </span>
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
  onConfirm,
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
  onConfirm: () => void
  onManualSearch: (term: string) => void
  onRetry: () => void
}) {
  const [swapOpen, setSwapOpen] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [manualText, setManualText] = useState('')
  const [count, setCount] = useState(item.count)
  useEffect(() => setCount(item.count), [item.count])

  // An unsure pick opens its alternatives once, when it first resolves.
  const unsure =
    live &&
    item.pick_confidence != null &&
    item.pick_confidence < UNSURE_BELOW &&
    !!item.chosen &&
    item.alternatives.length > 0
  const autoOpened = useRef(false)
  useEffect(() => {
    if (unsure && !autoOpened.current) {
      autoOpened.current = true
      setSwapOpen(true)
    }
  }, [unsure])

  // --- pending / matching → skeleton --------------------------------------
  if (item.status === 'pending' || item.status === 'matching') {
    return (
      <div className="rounded-card border border-line bg-surface p-3.5 shadow-card" aria-hidden>
        <div className="flex gap-3.5">
          <div className="sk h-[72px] w-[72px] flex-none rounded-[12px]" />
          <div className="flex-1">
            <div className="flex justify-between gap-3">
              <div className="sk h-3.5 w-[70%] rounded" />
              <div className="sk h-3.5 w-12 rounded" />
            </div>
            <div className="sk mt-2 h-3 w-[35%] rounded" />
            <div className="sk mt-3 h-5 w-20 rounded-full" />
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
      <div className="rounded-card border border-line bg-surface p-2 shadow-card">
        <DegradedBanner tone="danger" onRetry={live ? onRetry : undefined} retrying={busy}>
          Matching failed for "{item.search_term}"{item.error ? ` — ${item.error}` : ''}.
        </DegradedBanner>
      </div>
    )
  }

  const pill = pillFor(item)
  const substituted = item.status === 'substituted'

  return (
    <div
      className={`rounded-card border bg-surface shadow-card ${
        notFound
          ? 'border-danger-border'
          : substituted
            ? 'border-warn-border'
            : unsure
              ? 'border-terracotta/50'
              : 'border-line'
      }`}
    >
      <div className="p-3.5">
        <div className="flex gap-3.5">
          {notFound ? (
            <span
              className="flex h-[72px] w-[72px] flex-none items-center justify-center rounded-[12px] bg-danger-bg text-danger"
              role="img"
              aria-label="Not found"
            >
              <Icon name="search" size={26} strokeWidth={1.9} />
            </span>
          ) : (
            <ProductThumb src={chosen?.image_url} size={72} />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex justify-between gap-3">
              <div className="text-[14.5px] font-semibold leading-snug text-ink">
                {notFound ? item.search_term : (chosen?.description ?? item.search_term)}
              </div>
              <div className="tab-fig whitespace-nowrap text-[15px] font-bold text-ink">
                {notFound ? '—' : money(chosen?.price)}
              </div>
            </div>
            {chosen?.size && <div className="mt-0.5 text-[12.5px] text-faint">{chosen.size}</div>}
            {source && <SourceLine source={source} />}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <StatusPill tone={pill.tone}>{pill.label}</StatusPill>
              {item.is_usual && (
                <span className="inline-flex items-center gap-1 rounded-md bg-badge-favbg px-2 py-[3px] text-[11px] font-semibold text-badge-favfg">
                  <Icon name="star" size={10} filled strokeWidth={0} />
                  Your usual
                </span>
              )}
              {substituted && (
                <span className="text-[11.5px] font-medium text-warn">wanted: {item.search_term}</span>
              )}
              {unsure && (
                <span className="inline-flex items-center gap-1 rounded-md bg-terracotta-soft px-2 py-[3px] text-[11px] font-semibold text-terracotta-deep">
                  <Icon name="info" size={11} strokeWidth={2.4} />
                  Not sure — check this
                </span>
              )}
            </div>
          </div>
        </div>

        {/* not_found → manual search */}
        {notFound && live && (
          <div className="mt-3 rounded-[14px] bg-danger-bg p-3">
            <div className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold text-danger">
              <Icon name="alert" size={15} className="flex-none" />
              Couldn't find "{item.search_term}" at your store.
            </div>
            <div className="flex gap-2">
              <input
                value={manualText}
                onChange={(e) => setManualText(e.target.value)}
                placeholder="Search for it manually"
                aria-label={`Search for ${item.search_term}`}
                className="h-11 min-w-0 flex-1 rounded-[12px] border border-danger-border bg-surface px-3 text-[14px] text-ink outline-none placeholder:text-faint focus:border-danger"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && manualText.trim()) onManualSearch(manualText.trim())
                }}
              />
              <button
                type="button"
                onClick={() => manualText.trim() && onManualSearch(manualText.trim())}
                className="inline-flex h-11 flex-none items-center gap-1.5 rounded-[12px] bg-danger px-3.5 text-[13.5px] font-semibold text-onaccent"
              >
                <Icon name="search" size={15} strokeWidth={2.4} />
                Search
              </button>
            </div>
          </div>
        )}

        {/* actions row */}
        {!notFound && (
          <div className="mt-3 flex items-center gap-2 border-t border-divider pt-3">
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
                className={`h-10 px-3.5 text-[13px] ${
                  swapOpen ? '!border-ink !bg-ink !text-cream' : substituted ? '!border-warn-border' : ''
                }`}
                aria-expanded={swapOpen}
                onClick={() => setSwapOpen((v) => !v)}
              >
                <Icon name="swap" size={15} strokeWidth={2.2} />
                Swap
              </Button>
            )}
            {live && (
              <Button variant="danger" className="h-10 px-3.5 text-[13px]" onClick={onDrop}>
                <Icon name="trash" size={15} strokeWidth={2.2} />
                Remove
              </Button>
            )}
          </div>
        )}

        {/* swap expander */}
        {swapOpen && !notFound && (
          <div className="mt-3 rounded-[14px] border border-line bg-cream p-2.5">
            <SectionLabel className="mb-2 pl-1 pt-0.5">
              {unsure ? `Remy wasn't sure which "${item.search_term}" you want` : 'Other matches'}
            </SectionLabel>
            <div className="flex flex-col gap-1.5">
              {unsure && (
                <button
                  type="button"
                  onClick={() => {
                    onConfirm()
                    setSwapOpen(false)
                  }}
                  className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-[12px] border border-terracotta/50 bg-surface text-[13.5px] font-semibold text-terracotta-deep hover:bg-terracotta-soft"
                >
                  <Icon name="check" size={15} strokeWidth={2.6} />
                  Keep this one
                </button>
              )}
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
                    aria-label="Search for something else"
                    className="h-11 min-w-0 flex-1 rounded-[12px] border border-line2 bg-surface px-3 text-[14px] text-ink outline-none placeholder:text-faint focus:border-terracotta"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && manualText.trim()) {
                        onManualSearch(manualText.trim())
                        setSwapOpen(false)
                      }
                    }}
                  />
                  <Button
                    className="h-11 px-3.5 text-[13.5px]"
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
                  type="button"
                  onClick={() => setManualOpen(true)}
                  className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-[12px] border border-dashed border-line2 text-[13px] font-semibold text-muted hover:border-terracotta hover:text-terracotta-deep"
                >
                  <Icon name="search" size={15} />
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
    <div className="mt-1 truncate text-[11.5px] text-faint" title={`${source.raw}${suffix}`}>
      <span className="italic">{source.raw}</span>
      {suffix}
    </div>
  )
}

function AltRow({ alt, onChoose }: { alt: Alternative; onChoose: () => void }) {
  return (
    <button
      type="button"
      onClick={onChoose}
      className="flex min-h-[56px] items-center gap-3 rounded-[12px] border border-line bg-surface p-2 pr-3 text-left hover:border-terracotta"
    >
      <ProductThumb src={alt.image_url} size={44} radius="rounded-[10px]" />
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 block text-[13.5px] font-semibold leading-tight text-ink">
          {alt.description}
        </span>
        {alt.size && <span className="mt-0.5 block text-[12px] text-faint">{alt.size}</span>}
      </span>
      <span className="tab-fig flex-none text-[14px] font-bold text-ink">{money(alt.price)}</span>
    </button>
  )
}

// "Add your usuals?" — a horizontal strip of remembered products NOT already in
// the current cart draft (compared by UPC, including dropped items). Tapping a
// chip appends it via the add_upc cart edit; the chip's close button hides it (with undo).
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
    <section className="mt-7">
      <SectionLabel className="mb-1 flex items-center gap-1.5 px-5">
        <Icon name="star" size={12} filled strokeWidth={0} />
        Add your usuals?
      </SectionLabel>
      <div className="no-scrollbar flex gap-2.5 overflow-x-auto px-5 pb-2 pt-1.5">
        {suggestions.map((u) => (
          <UsualChip key={`${u.food_key}-${u.upc}`} usual={u} onAdd={() => onAdd(u.upc)} onHide={() => onHide(u)} />
        ))}
      </div>
    </section>
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
    <div className="relative w-[116px] flex-none">
      <button
        type="button"
        onClick={onAdd}
        className="flex w-full flex-col items-center gap-1.5 rounded-[14px] border border-line bg-surface p-2.5 text-center shadow-card hover:border-terracotta"
      >
        <ProductThumb src={usual.image_url} size={52} radius="rounded-[10px]" />
        <span className="line-clamp-2 min-h-[2.4em] text-[11.5px] font-semibold leading-tight text-ink">
          {usual.description ?? usual.food_key}
        </span>
        <span className="tab-fig inline-flex items-center gap-0.5 text-[12px] font-bold text-terracotta-deep">
          <Icon name="plus" size={12} strokeWidth={2.8} />
          {usual.last_price != null ? money(usual.last_price) : 'Add'}
        </span>
      </button>
      <button
        type="button"
        aria-label={`Hide ${usual.description ?? usual.food_key}`}
        onClick={onHide}
        className="absolute -right-1.5 -top-1.5 flex h-6 w-6 items-center justify-center rounded-full border border-line2 bg-surface text-muted shadow-card before:absolute before:-inset-2.5 before:content-[''] hover:text-ink"
      >
        <Icon name="x" size={12} strokeWidth={2.6} />
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
