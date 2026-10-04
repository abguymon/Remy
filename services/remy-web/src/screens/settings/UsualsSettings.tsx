// Settings → Usuals (post-launch purchase memory). Lists the user's usuals
// (photo, name, size, price, source badge, remove), an "Add a usual" store
// search that pins a product, and an "Import from order history" sheet
// (upload receipt / paste text → review matched products → confirm-seed).
// Edit register, 390px-first.
import { useMemo, useRef, useState } from 'react'
import { ApiError } from '../../lib/api'
import {
  useConfirmImport,
  useImportUsuals,
  usePinUsual,
  useProductSearch,
  useRemoveUsual,
  useUsuals,
} from '../../lib/queries'
import type {
  ImportProductMatch,
  ImportReviewItem,
  ProductSearchResult,
  SettingsResponse,
  Usual,
} from '../../lib/types'
import { money } from '../../lib/format'
import { toast } from '../../stores/toast'
import {
  Button,
  DegradedBanner,
  IconButton,
  SectionHeading,
  SectionLabel,
  SegmentedControl,
  Spinner,
} from '../../components/ui'
import Icon from '../../components/Icon'

const MAX_IMPORT_FILES = 6
const MAX_IMPORT_BYTES = 15_000_000

const inputClass =
  'h-11 w-full min-w-0 rounded-[12px] border border-line2 bg-cream px-3.5 text-[14px] text-ink outline-none placeholder:text-faint focus:border-terracotta'

const SOURCE_BADGE: Record<string, string> = {
  order: 'Ordered',
  swap: 'Preferred',
  pinned: 'Pinned',
  import: 'Imported',
}

// Small square product thumbnail (Kroger CDN URLs load directly — external, no auth).
function ProductThumb({ src, size = 52 }: { src?: string | null; size?: number }) {
  return (
    <span
      className="flex flex-none items-center justify-center overflow-hidden rounded-[12px] border border-line bg-surface"
      style={{ width: size, height: size }}
    >
      {src ? (
        <img src={src} alt="" className="h-full w-full rounded-[10px] object-contain p-1" />
      ) : (
        <Icon name="bag" size={Math.round(size * 0.4)} className="text-faint" />
      )}
    </span>
  )
}

export default function UsualsSettings({ settings }: { settings: SettingsResponse }) {
  const usuals = useUsuals(24)
  const remove = useRemoveUsual()
  const hasStore = !!settings.store_location_id
  const [importOpen, setImportOpen] = useState(false)

  const rows = usuals.data ?? []

  return (
    <section className="mt-9 px-5">
      <SectionHeading
        className="mb-3"
        sub="Products Remy reaches for first when it recognizes an ingredient — built from what you order and swap. Pin favorites or import your order history to jump-start it."
      >
        Usuals
      </SectionHeading>
      <div className="divide-y divide-divider overflow-hidden rounded-card border border-line bg-surface shadow-card">
        {/* Current usuals list */}
        {usuals.isLoading ? (
          <div className="flex items-center gap-2 px-4 py-4 text-[13.5px] text-muted">
            <Spinner /> Loading…
          </div>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-6 text-center text-[13.5px] text-muted">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-chip text-muted">
              <Icon name="bag" size={19} />
            </span>
            No usuals yet. Add one below, or import your order history.
          </div>
        ) : (
          <ul className="divide-y divide-divider">
            {rows.map((u) => (
              <UsualRow
                key={`${u.food_key}-${u.upc}`}
                usual={u}
                busy={remove.isPending}
                onRemove={async () => {
                  try {
                    await remove.mutateAsync(u.upc)
                    toast('Removed from usuals')
                  } catch (err) {
                    toast(err instanceof ApiError ? err.message : 'Could not remove.')
                  }
                }}
              />
            ))}
          </ul>
        )}

        {/* Add a usual (store product search) */}
        <AddUsual hasStore={hasStore} />

        {/* Import from order history */}
        <button
          onClick={() => setImportOpen(true)}
          className="flex min-h-[60px] w-full items-center gap-3 px-4 py-3 text-left hover:bg-cream"
        >
          <span className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-terracotta-soft text-terracotta-deep">
            <Icon name="upload" size={18} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[14.5px] font-semibold text-ink">Import from order history</span>
            <span className="block text-[12.5px] text-faint">Receipt photo, screenshot, PDF or pasted text</span>
          </span>
          <Icon name="chevronRight" size={18} className="flex-none text-faint" />
        </button>
      </div>

      {importOpen && <ImportSheet hasStore={hasStore} onClose={() => setImportOpen(false)} />}
    </section>
  )
}

function UsualRow({
  usual,
  busy,
  onRemove,
}: {
  usual: Usual
  busy: boolean
  onRemove: () => void
}) {
  const badge = SOURCE_BADGE[usual.source] ?? usual.source
  return (
    <li className="flex items-center gap-3 py-2.5 pl-3 pr-2">
      <ProductThumb src={usual.image_url} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-semibold text-ink">
          {usual.description ?? usual.food_key}
        </div>
        <div className="mt-1 flex items-center gap-1.5 overflow-hidden text-[12px] text-faint">
          <span className="flex-none rounded-full bg-chip px-2 py-[1px] text-[11.5px] font-semibold text-muted">
            {badge}
          </span>
          <span className="truncate">
            {[usual.size, usual.times_ordered >= 2 ? `${usual.times_ordered}× ordered` : null]
              .filter(Boolean)
              .join(' · ')}
          </span>
        </div>
      </div>
      <span className="tab-fig flex-none text-[13px] font-bold text-ink">{money(usual.last_price)}</span>
      <IconButton
        icon="x"
        variant="plain"
        size={36}
        iconSize={16}
        label={`Remove ${usual.description ?? usual.food_key}`}
        disabled={busy}
        onClick={onRemove}
        className="text-faint"
      />
    </li>
  )
}

function AddUsual({ hasStore }: { hasStore: boolean }) {
  const [term, setTerm] = useState('')
  const search = useProductSearch()
  const pin = usePinUsual()
  const [error, setError] = useState<string | null>(null)

  async function run() {
    const q = term.trim()
    if (!q) return
    setError(null)
    try {
      await search.mutateAsync(q)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'no_store_selected') {
        setError('Select a store above to search products.')
      } else {
        setError(err instanceof ApiError ? err.message : 'Search failed.')
      }
    }
  }

  async function pinProduct(p: ProductSearchResult) {
    try {
      await pin.mutateAsync({
        upc: p.upc,
        description: p.description,
        size: p.size,
        image_url: p.image_url,
        price: p.price,
        food_key: term.trim(),
      })
      toast(`Pinned ${p.description ?? 'product'}`)
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not pin.')
    }
  }

  const results = search.data ?? []

  return (
    <div className="p-4">
      <SectionLabel className="mb-2">Add a usual</SectionLabel>
      <div className="flex gap-2">
        <div className="relative min-w-0 flex-1">
          <Icon
            name="search"
            size={17}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            placeholder="Search, e.g. whole milk"
            aria-label="Search products"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && run()}
            className={`${inputClass} pl-10`}
          />
        </div>
        <Button
          className="h-11 flex-none px-4 text-[13.5px]"
          onClick={run}
          disabled={!hasStore}
          busy={search.isPending}
          busyLabel="…"
        >
          Search
        </Button>
      </div>
      {!hasStore && (
        <div className="mt-2 text-[12.5px] text-muted">Select a store above to search products.</div>
      )}
      {error && <div className="mt-2 text-[12.5px] text-danger">{error}</div>}

      {search.isSuccess && results.length === 0 && (
        <div className="mt-3 text-[13px] text-muted">No products found for "{term.trim()}".</div>
      )}

      {results.length > 0 && (
        <ul className="mt-3 divide-y divide-divider overflow-hidden rounded-[14px] border border-line2">
          {results.map((p) => (
            <li key={p.upc}>
              <button
                disabled={pin.isPending}
                onClick={() => pinProduct(p)}
                className="flex w-full items-center gap-3 p-2.5 text-left hover:bg-cream disabled:opacity-60"
              >
                <ProductThumb src={p.image_url} size={46} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-semibold text-ink">{p.description}</div>
                  {p.size && <div className="text-[11.5px] text-faint">{p.size}</div>}
                </div>
                <span className="tab-fig flex-none text-[13px] font-bold text-ink">
                  {money(p.price)}
                </span>
                <span
                  aria-hidden
                  className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-terracotta-soft text-terracotta-deep"
                >
                  <Icon name="plus" size={16} strokeWidth={2.4} />
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// --- Import from order history sheet ---------------------------------------

type ImportMode = 'upload' | 'text'

function ImportSheet({ hasStore, onClose }: { hasStore: boolean; onClose: () => void }) {
  const [mode, setMode] = useState<ImportMode>('upload')
  const [review, setReview] = useState<ImportReviewItem[] | null>(null)
  const busy = useRef(false)

  return (
    <div
      className="fixed inset-0 z-30 flex animate-pop items-end justify-center bg-dark/50 sm:items-center sm:p-6"
      onClick={() => {
        if (!busy.current) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Import order history"
        className="max-h-[92%] w-full max-w-[440px] overflow-y-auto rounded-t-panel bg-surface p-6 shadow-modal sm:rounded-panel"
        onClick={(e) => e.stopPropagation()}
      >
        {review ? (
          <ImportReview items={review} onClose={onClose} onBack={() => setReview(null)} />
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <div className="font-serif text-[22px] font-medium tracking-[-0.01em]">
                Import order history
              </div>
              <IconButton
                icon="x"
                variant="plain"
                size={36}
                iconSize={18}
                label="Close"
                className="-mr-2 -mt-1 text-muted"
                onClick={() => {
                  if (!busy.current) onClose()
                }}
              />
            </div>
            {!hasStore && (
              <div className="mt-3">
                <DegradedBanner>Select a store in Settings first so we can match products.</DegradedBanner>
              </div>
            )}
            <SegmentedControl<ImportMode>
              label="Import source"
              className="mt-4"
              value={mode}
              onChange={setMode}
              options={[
                { value: 'upload', label: <><Icon name="camera" size={16} />Upload</> },
                { value: 'text', label: <><Icon name="list" size={16} />Paste text</> },
              ]}
            />
            {mode === 'upload' ? (
              <ImportUpload
                disabled={!hasStore}
                onReviewed={setReview}
                onBusy={(b) => (busy.current = b)}
              />
            ) : (
              <ImportText
                disabled={!hasStore}
                onReviewed={setReview}
                onBusy={(b) => (busy.current = b)}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}

function useImportSubmit(onReviewed: (items: ImportReviewItem[]) => void, onBusy: (b: boolean) => void) {
  const imp = useImportUsuals()
  const [error, setError] = useState<string | null>(null)

  async function submit(payload: { files?: File[]; text?: string }) {
    setError(null)
    onBusy(true)
    try {
      const res = await imp.mutateAsync(payload)
      if (!res.found_items || res.items.length === 0) {
        setError("We couldn't find any grocery items in that. Try a clearer receipt or order page.")
        return
      }
      onReviewed(res.items)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Import failed. Try again.')
    } finally {
      onBusy(false)
    }
  }

  return { submit, pending: imp.isPending, error }
}

function ImportUpload({
  disabled,
  onReviewed,
  onBusy,
}: {
  disabled: boolean
  onReviewed: (items: ImportReviewItem[]) => void
  onBusy: (b: boolean) => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const { submit, pending, error } = useImportSubmit(onReviewed, onBusy)
  const [localError, setLocalError] = useState<string | null>(null)

  function addFiles(list: FileList | null) {
    if (!list) return
    setLocalError(null)
    const incoming = Array.from(list).filter((f) => {
      if (f.size > MAX_IMPORT_BYTES) {
        setLocalError(`"${f.name}" is larger than 15 MB.`)
        return false
      }
      return true
    })
    setFiles((prev) => [...prev, ...incoming].slice(0, MAX_IMPORT_FILES))
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <>
      <div className="mt-3 text-[13px] text-muted">
        Upload a photo, screenshot, or PDF of a receipt or order-history page.
      </div>
      {(localError || error) && (
        <div className="mt-3">
          <DegradedBanner tone="danger">{localError || error}</DegradedBanner>
        </div>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/*,application/pdf"
        multiple
        capture="environment"
        className="hidden"
        onChange={(e) => addFiles(e.target.files)}
      />
      {files.length > 0 && (
        <ul className="mt-3 divide-y divide-divider overflow-hidden rounded-[14px] border border-line2">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center gap-2.5 py-1.5 pl-3 pr-1.5">
              <span className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-chip text-muted">
                <Icon name={f.type.startsWith('image/') ? 'camera' : 'file'} size={16} />
              </span>
              <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{f.name}</span>
              <IconButton
                icon="x"
                variant="plain"
                size={36}
                iconSize={16}
                label={`Remove ${f.name}`}
                className="text-faint"
                onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
              />
            </li>
          ))}
        </ul>
      )}
      <button
        onClick={() => inputRef.current?.click()}
        disabled={pending || files.length >= MAX_IMPORT_FILES}
        className="mt-3 flex h-12 w-full items-center justify-center gap-2 rounded-[14px] border border-dashed border-line2 bg-transparent text-[13.5px] font-semibold text-terracotta-deep hover:bg-cream disabled:opacity-40"
      >
        <Icon name="plus" size={16} strokeWidth={2.4} />
        {files.length === 0 ? 'Choose receipt or screenshot' : 'Add another'}
      </button>
      {pending && (
        <div className="mt-3 flex items-center gap-2 text-[12.5px] text-muted">
          <Spinner /> Reading and matching products…
        </div>
      )}
      <Button
        className="mt-4 h-12 w-full text-[14.5px]"
        disabled={disabled || pending || files.length === 0}
        onClick={() => submit({ files })}
      >
        {pending ? 'Reading…' : 'Find products'}
      </Button>
    </>
  )
}

function ImportText({
  disabled,
  onReviewed,
  onBusy,
}: {
  disabled: boolean
  onReviewed: (items: ImportReviewItem[]) => void
  onBusy: (b: boolean) => void
}) {
  const [text, setText] = useState('')
  const { submit, pending, error } = useImportSubmit(onReviewed, onBusy)

  return (
    <>
      <div className="mt-3 text-[13px] text-muted">
        Paste your order history or a receipt — one item per line works best.
      </div>
      {error && (
        <div className="mt-3">
          <DegradedBanner tone="danger">{error}</DegradedBanner>
        </div>
      )}
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={'Whole Milk 1 gal\nLarge Eggs 12 ct\nBananas\n…'}
        rows={6}
        aria-label="Order history text"
        className="mt-3 w-full resize-y rounded-[14px] border border-line2 bg-cream px-3.5 py-3 text-[14px] text-ink outline-none placeholder:text-faint focus:border-terracotta"
      />
      {pending && (
        <div className="mt-3 flex items-center gap-2 text-[12.5px] text-muted">
          <Spinner /> Reading and matching products…
        </div>
      )}
      <Button
        className="mt-4 h-12 w-full text-[14.5px]"
        disabled={disabled || pending || !text.trim()}
        onClick={() => submit({ text })}
      >
        {pending ? 'Reading…' : 'Find products'}
      </Button>
    </>
  )
}

// Per extracted item: its matched product with a picker to swap among
// alternatives or exclude the item; Confirm seeds the included ones.
interface ReviewChoice {
  food_key: string
  extracted_name: string
  options: ImportProductMatch[]
  selectedUpc: string | null // null = excluded / no match
}

function ImportReview({
  items,
  onClose,
  onBack,
}: {
  items: ImportReviewItem[]
  onClose: () => void
  onBack: () => void
}) {
  const confirm = useConfirmImport()
  const [choices, setChoices] = useState<ReviewChoice[]>(() =>
    items.map((it) => {
      const options = it.matched ? [it.matched, ...it.alternatives] : it.alternatives
      return {
        food_key: it.food_key,
        extracted_name: it.extracted_name,
        options,
        selectedUpc: it.matched?.upc ?? options[0]?.upc ?? null,
      }
    }),
  )

  const includedCount = useMemo(() => choices.filter((c) => c.selectedUpc).length, [choices])

  function setSelected(index: number, upc: string | null) {
    setChoices((prev) => prev.map((c, i) => (i === index ? { ...c, selectedUpc: upc } : c)))
  }

  async function confirmImport() {
    const selections = choices
      .filter((c) => c.selectedUpc)
      .map((c) => {
        const p = c.options.find((o) => o.upc === c.selectedUpc)!
        return {
          food_key: c.food_key,
          upc: p.upc,
          description: p.description,
          size: p.size,
          image_url: p.image_url,
          price: p.price,
        }
      })
    if (selections.length === 0) {
      onClose()
      return
    }
    try {
      const res = await confirm.mutateAsync(selections)
      toast(`Added ${res.seeded} ${res.seeded === 1 ? 'usual' : 'usuals'}`)
      onClose()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not save.')
    }
  }

  return (
    <>
      <div className="font-serif text-[22px] font-medium tracking-[-0.01em]">Review matches</div>
      <div className="mt-1 text-[13px] text-muted">
        Pick the right product for each item, or exclude ones you don't want.
      </div>
      <ul className="mt-4 flex flex-col gap-3">
        {choices.map((c, i) => (
          <li key={`${c.food_key}-${i}`} className="rounded-card border border-line bg-cream p-3">
            <SectionLabel>{c.extracted_name}</SectionLabel>
            {c.options.length === 0 ? (
              <div className="mt-1.5 text-[12.5px] text-muted">No product match — will be skipped.</div>
            ) : (
              <div className="mt-2 flex flex-col gap-1.5">
                {c.options.slice(0, 3).map((p) => {
                  const active = c.selectedUpc === p.upc
                  return (
                    <button
                      key={p.upc}
                      onClick={() => setSelected(i, active ? null : p.upc)}
                      aria-pressed={active}
                      className={`flex items-center gap-2.5 rounded-[12px] border p-2 text-left ${
                        active ? 'border-terracotta bg-surface ring-1 ring-terracotta' : 'border-line bg-surface/70'
                      }`}
                    >
                      <ProductThumb src={p.image_url} size={40} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12.5px] font-semibold text-ink">
                          {p.description}
                        </span>
                        {p.size && <span className="block text-[11px] text-faint">{p.size}</span>}
                      </span>
                      <span className="tab-fig flex-none text-[12.5px] font-bold">{money(p.price)}</span>
                      <span
                        className={`flex h-6 w-6 flex-none items-center justify-center rounded-full ${
                          active ? 'bg-terracotta text-onaccent' : 'border border-line2 text-transparent'
                        }`}
                      >
                        <Icon name="check" size={14} strokeWidth={3} />
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-4 flex gap-2.5">
        <Button variant="secondary" className="h-12 flex-1 text-sm" onClick={onBack}>
          Back
        </Button>
        <Button
          className="h-12 flex-1 text-sm"
          disabled={confirm.isPending}
          onClick={confirmImport}
        >
          {confirm.isPending
            ? 'Saving…'
            : includedCount > 0
              ? `Add ${includedCount} ${includedCount === 1 ? 'usual' : 'usuals'}`
              : 'Done'}
        </Button>
      </div>
    </>
  )
}
