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
import { Button, SectionLabel, Spinner } from '../../components/ui'

const MAX_IMPORT_FILES = 6
const MAX_IMPORT_BYTES = 15_000_000

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
      className="flex flex-none items-center justify-center overflow-hidden rounded-[10px] border border-tile bg-white"
      style={{ width: size, height: size }}
    >
      {src ? (
        <img src={src} alt="" className="h-full w-full object-contain p-1" />
      ) : (
        <span className="font-mono text-[8px] text-hint">img</span>
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
    <div className="mt-6">
      <SectionLabel className="mb-2">Usuals</SectionLabel>
      <div className="rounded-card border border-line bg-surface p-4">
        <div className="text-[13px] leading-relaxed text-muted">
          Products Remy reaches for first when it recognizes an ingredient — built from what you
          order and swap. Pin favorites or import your order history to jump-start it.
        </div>

        {/* Current usuals list */}
        {usuals.isLoading ? (
          <div className="mt-4 flex items-center gap-2 text-[13px] text-muted">
            <Spinner /> Loading…
          </div>
        ) : rows.length === 0 ? (
          <div className="mt-4 rounded-[11px] border border-dashed border-line2 bg-cream/60 px-3.5 py-4 text-center text-[13px] text-muted">
            No usuals yet. Add one below, or import your order history.
          </div>
        ) : (
          <ul className="mt-4 flex flex-col gap-2">
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
          className="mt-3 w-full rounded-[11px] border border-dashed border-[#D8CDB9] bg-transparent py-3 text-[13px] font-semibold text-terracotta"
        >
          ⬆ Import from order history
        </button>
      </div>

      {importOpen && <ImportSheet hasStore={hasStore} onClose={() => setImportOpen(false)} />}
    </div>
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
    <li className="flex items-center gap-3 rounded-[12px] border border-line2 bg-cream/50 p-2.5">
      <ProductThumb src={usual.image_url} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13.5px] font-semibold text-ink">
          {usual.description ?? usual.food_key}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11.5px] text-faint">
          {usual.size && <span>{usual.size}</span>}
          {usual.size && <span>·</span>}
          <span className="rounded bg-badge-webbg px-1.5 py-[1px] font-semibold text-muted">
            {badge}
          </span>
          {usual.times_ordered >= 2 && <span>· ordered {usual.times_ordered}×</span>}
        </div>
      </div>
      <span className="tab-fig flex-none text-[13px] font-bold text-ink">{money(usual.last_price)}</span>
      <button
        aria-label={`Remove ${usual.description ?? usual.food_key}`}
        disabled={busy}
        onClick={onRemove}
        className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-line2 text-[13px] leading-none text-muted disabled:opacity-50"
      >
        ✕
      </button>
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
    <div className="mt-4 border-t border-divider pt-4">
      <SectionLabel tone="terracotta" className="mb-2">
        Add a usual
      </SectionLabel>
      <div className="flex gap-2">
        <input
          placeholder="Search products (e.g. whole milk)"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
          className="flex-1 rounded-[10px] border border-line2 bg-cream px-3 py-2.5 text-sm outline-none focus:border-terracotta"
        />
        <Button className="px-4 py-2.5 text-sm" onClick={run} disabled={search.isPending || !hasStore}>
          {search.isPending ? '…' : 'Search'}
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
        <ul className="mt-3 flex flex-col gap-2">
          {results.map((p) => (
            <li key={p.upc}>
              <button
                disabled={pin.isPending}
                onClick={() => pinProduct(p)}
                className="flex w-full items-center gap-3 rounded-[12px] border border-line2 bg-surface p-2.5 text-left hover:bg-cream disabled:opacity-60"
              >
                <ProductThumb src={p.image_url} size={46} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-semibold text-ink">{p.description}</div>
                  {p.size && <div className="text-[11.5px] text-faint">{p.size}</div>}
                </div>
                <span className="tab-fig flex-none text-[13px] font-bold text-ink">
                  {money(p.price)}
                </span>
                <span className="flex-none text-[16px] font-semibold text-terracotta">＋</span>
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
      className="fixed inset-0 z-30 flex animate-pop items-end justify-center sm:items-center"
      style={{ background: 'rgba(40,30,20,.4)' }}
      onClick={() => {
        if (!busy.current) onClose()
      }}
    >
      <div
        className="max-h-[92%] w-full max-w-[420px] overflow-y-auto rounded-t-[22px] bg-surface p-[22px] shadow-modal sm:rounded-[18px]"
        onClick={(e) => e.stopPropagation()}
      >
        {review ? (
          <ImportReview items={review} onClose={onClose} onBack={() => setReview(null)} />
        ) : (
          <>
            <div className="font-serif text-xl font-semibold">Import order history</div>
            {!hasStore && (
              <div className="mt-3 rounded-[10px] border border-warn-border bg-warn-bg px-3 py-2.5 text-[12.5px] text-warn">
                Select a store in Settings first so we can match products.
              </div>
            )}
            <div className="mt-3 flex gap-1 rounded-[11px] border border-line2 bg-cream p-1">
              <ModeTab active={mode === 'upload'} onClick={() => setMode('upload')} label="Upload" />
              <ModeTab active={mode === 'text'} onClick={() => setMode('text')} label="Paste text" />
            </div>
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

function ModeTab({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-[9px] py-2 text-[13px] font-semibold ${active ? 'bg-surface text-ink shadow-sm' : 'text-muted'}`}
    >
      {label}
    </button>
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
        <div className="mt-3 rounded-[10px] border border-danger-border bg-danger-bg px-3 py-2.5 text-[13px] text-danger">
          {localError || error}
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
        <ul className="mt-3 flex flex-col gap-2">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center gap-2.5 rounded-[11px] border border-line2 bg-cream p-2"
            >
              <span className="text-[18px]">{f.type.startsWith('image/') ? '🧾' : '📄'}</span>
              <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">{f.name}</span>
              <button
                aria-label="Remove"
                onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                className="rounded-[7px] px-2 py-1 text-[13px] text-danger"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      <button
        onClick={() => inputRef.current?.click()}
        disabled={pending || files.length >= MAX_IMPORT_FILES}
        className="mt-3 w-full rounded-[11px] border border-dashed border-[#D8CDB9] bg-transparent py-3 text-[13px] font-semibold text-terracotta disabled:opacity-40"
      >
        {files.length === 0 ? '＋ Choose receipt or screenshot' : '＋ Add another'}
      </button>
      {pending && (
        <div className="mt-3 flex items-center gap-2 text-[12.5px] text-muted">
          <Spinner /> Reading and matching products…
        </div>
      )}
      <Button
        className="mt-4 w-full py-3 text-sm"
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
        <div className="mt-3 rounded-[10px] border border-danger-border bg-danger-bg px-3 py-2.5 text-[13px] text-danger">
          {error}
        </div>
      )}
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={'Whole Milk 1 gal\nLarge Eggs 12 ct\nBananas\n…'}
        rows={6}
        className="mt-3 w-full resize-y rounded-[11px] border border-line2 bg-cream px-3.5 py-3 text-sm outline-none focus:border-terracotta"
      />
      {pending && (
        <div className="mt-3 flex items-center gap-2 text-[12.5px] text-muted">
          <Spinner /> Reading and matching products…
        </div>
      )}
      <Button
        className="mt-4 w-full py-3 text-sm"
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
      <div className="font-serif text-xl font-semibold">Review matches</div>
      <div className="mt-1 text-[13px] text-muted">
        Pick the right product for each item, or exclude ones you don't want.
      </div>
      <ul className="mt-4 flex flex-col gap-3">
        {choices.map((c, i) => (
          <li key={`${c.food_key}-${i}`} className="rounded-[12px] border border-line2 bg-cream/50 p-3">
            <div className="text-[11.5px] font-semibold uppercase tracking-[.04em] text-faint">
              {c.extracted_name}
            </div>
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
                      className={`flex items-center gap-2.5 rounded-[10px] border p-2 text-left ${
                        active ? 'border-terracotta bg-surface' : 'border-line2 bg-surface/60'
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
                        className={`flex h-5 w-5 flex-none items-center justify-center rounded-full text-[11px] ${
                          active ? 'bg-terracotta text-white' : 'border border-line2 text-transparent'
                        }`}
                      >
                        ✓
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
        <Button variant="secondary" className="flex-1 py-3 text-sm" onClick={onBack}>
          Back
        </Button>
        <Button
          className="flex-1 py-3 text-sm"
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
