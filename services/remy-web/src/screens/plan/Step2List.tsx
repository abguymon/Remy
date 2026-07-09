// Plan step 2 — review shopping list (DESIGN_BRIEF §4.4). Edit register: three
// groups (To buy / Excluded by you / Pantry — skipping), consolidated qty +
// contributing-recipe expansion, conflict display, qty edit, delete, add-item
// row, and a sticky "Find products at {store} →" bar.
import { useState } from 'react'
import { ApiError } from '../../lib/api'
import { useApproveList, useListEdits, useSettings } from '../../lib/queries'
import type { ListEdit, ListLine, PlanSnapshot } from '../../lib/types'
import { toast } from '../../stores/toast'
import { Button, SectionLabel, Spinner, StickyBar } from '../../components/ui'

export default function Step2List({ snapshot, live }: { snapshot: PlanSnapshot; live: boolean }) {
  const listEdits = useListEdits()
  const approve = useApproveList()
  const settings = useSettings()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [editingQty, setEditingQty] = useState<string | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [addText, setAddText] = useState('')

  const lines = snapshot.shopping_list.lines
  const building = snapshot.shopping_list.status === 'building' || snapshot.shopping_list.status === 'pending'
  const toBuy = lines.filter((l) => l.group === 'to_buy')
  const excluded = lines.filter((l) => l.group === 'user_excluded')
  const pantry = lines.filter((l) => l.group === 'pantry_skipped')

  async function edit(op: ListEdit) {
    try {
      await listEdits.mutateAsync([op])
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Edit failed.')
    }
  }

  async function onApprove() {
    try {
      await approve.mutateAsync()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'no_store_selected') {
        toast('Pick a store in Settings before matching products.')
      } else {
        toast(err instanceof ApiError ? err.message : 'Could not continue.')
      }
    }
  }

  const storeName = settings.data?.store_name ?? 'your store'

  if (building) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted">
        <Spinner /> Building your shopping list…
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="no-scrollbar flex-1 overflow-y-auto px-5 pb-8 pt-2">
        <div className="font-serif text-[26px] font-semibold tracking-tight">Review your list</div>
        <div className="mt-0.5 text-sm text-muted">
          Merged across your recipes. Uncheck anything you already have.
        </div>

        {/* To buy */}
        <div className="mb-2 mt-6">
          <SectionLabel tone="success">To buy · {toBuy.length}</SectionLabel>
        </div>
        <div className="overflow-hidden rounded-card border border-line bg-surface shadow-cardsoft">
          {toBuy.map((line) => (
            <LineRow
              key={line.id}
              line={line}
              live={live}
              expanded={!!expanded[line.id]}
              editingQty={editingQty === line.id}
              onToggleExpand={() =>
                setExpanded((e) => ({ ...e, [line.id]: !e[line.id] }))
              }
              onCheck={() => edit({ op: 'exclude', line_id: line.id })}
              onDelete={() => edit({ op: 'delete', line_id: line.id })}
              onStartEditQty={() => setEditingQty(line.id)}
              onCommitQty={(q) => {
                setEditingQty(null)
                if (q != null) edit({ op: 'set_quantity', line_id: line.id, quantity: q, unit: line.unit })
              }}
            />
          ))}
          {live && (
            <>
              {addOpen ? (
                <div className="flex gap-2 p-3">
                  <input
                    autoFocus
                    value={addText}
                    onChange={(e) => setAddText(e.target.value)}
                    placeholder="e.g. 1 bunch parsley"
                    className="flex-1 rounded-[8px] border border-line2 bg-surface px-3 py-2 text-[14px] outline-none focus:border-terracotta"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && addText.trim()) {
                        edit({ op: 'add', text: addText.trim() })
                        setAddText('')
                        setAddOpen(false)
                      }
                    }}
                  />
                  <Button
                    className="px-3 py-2 text-[13px]"
                    disabled={!addText.trim()}
                    onClick={() => {
                      edit({ op: 'add', text: addText.trim() })
                      setAddText('')
                      setAddOpen(false)
                    }}
                  >
                    Add
                  </Button>
                </div>
              ) : (
                <button
                  onClick={() => setAddOpen(true)}
                  className="w-full py-3.5 pl-[49px] text-left text-[13.5px] font-semibold text-terracotta"
                >
                  ＋ Add an item
                </button>
              )}
            </>
          )}
        </div>

        {/* Excluded by you */}
        {excluded.length > 0 && (
          <>
            <SectionLabel className="mb-2 mt-5">Excluded by you</SectionLabel>
            <div className="overflow-hidden rounded-card border border-dashed border-line2 bg-[#F3ECDF]">
              {excluded.map((line) => (
                <div
                  key={line.id}
                  className="flex items-center gap-3 border-b border-[#EAE1D2] px-3.5 py-2.5 opacity-70 last:border-0"
                >
                  <button
                    onClick={() => live && edit({ op: 'include', line_id: line.id })}
                    className="h-6 w-6 flex-none rounded-[7px] border-[1.5px] border-[#C6BCA9]"
                    aria-label="Add back"
                  />
                  <div className="flex-1 text-[14.5px] text-faint line-through">{line.display}</div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Pantry — skipping */}
        {pantry.length > 0 && (
          <>
            <SectionLabel className="mb-1 mt-5">Pantry — skipping</SectionLabel>
            <div className="mb-2 text-[12.5px] text-faint">
              You told us you keep these on hand. Tap to add back.
            </div>
            <div className="overflow-hidden rounded-card border border-line bg-surface">
              {pantry.map((line) => (
                <div
                  key={line.id}
                  className="flex items-center gap-3 border-b border-divider px-3.5 py-2.5 last:border-0"
                >
                  <button
                    onClick={() => live && edit({ op: 'include', line_id: line.id })}
                    className="h-6 w-6 flex-none rounded-[7px] border-[1.5px] border-line2"
                    aria-label="Add back"
                  />
                  <div className="flex-1 text-[14.5px] text-faint">
                    <span className="text-muted">{line.display}</span>
                  </div>
                  <span className="text-[11px] text-hint">pantry</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <StickyBar>
        <Button
          className="w-full py-3.5 text-[15.5px] font-bold"
          disabled={!live || approve.isPending}
          onClick={onApprove}
        >
          {approve.isPending ? 'Finding products…' : `Find products at ${storeName} →`}
        </Button>
      </StickyBar>
    </div>
  )
}

function LineRow({
  line,
  live,
  expanded,
  editingQty,
  onToggleExpand,
  onCheck,
  onDelete,
  onStartEditQty,
  onCommitQty,
}: {
  line: ListLine
  live: boolean
  expanded: boolean
  editingQty: boolean
  onToggleExpand: () => void
  onCheck: () => void
  onDelete: () => void
  onStartEditQty: () => void
  onCommitQty: (q: number | null) => void
}) {
  const [qtyText, setQtyText] = useState(line.quantity != null ? String(line.quantity) : '')
  const recipeCount = line.contributing.length

  return (
    <div className="border-b border-divider p-3.5 last:border-0">
      <div className="flex items-start gap-3">
        <button
          onClick={() => live && onCheck()}
          className="mt-0.5 flex h-6 w-6 flex-none items-center justify-center rounded-[7px] bg-success text-sm font-bold text-white"
          aria-label="Exclude"
        >
          ✓
        </button>
        <div className="min-w-0 flex-1">
          {editingQty ? (
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={qtyText}
                onChange={(e) => setQtyText(e.target.value)}
                onBlur={() => onCommitQty(qtyText ? Number(qtyText) : null)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onCommitQty(qtyText ? Number(qtyText) : null)
                  if (e.key === 'Escape') onCommitQty(null)
                }}
                inputMode="decimal"
                className="tab-fig w-20 rounded-[7px] border border-line2 bg-surface px-2 py-1 text-[15px] outline-none focus:border-terracotta"
              />
              <span className="text-[15px] text-muted">
                {line.unit ? `${line.unit} ` : ''}
                {line.food}
              </span>
            </div>
          ) : (
            <button
              onClick={() => live && onStartEditQty()}
              className="text-left text-[15px] font-semibold text-ink"
            >
              {line.display}
            </button>
          )}
          {recipeCount > 0 && (
            <button
              onClick={onToggleExpand}
              className="flex flex-wrap items-center gap-1.5 pt-1 text-[12px] text-faint"
            >
              {line.conflict && <span className="font-semibold text-warn">mixed units</span>}
              <span>
                {recipeCount} {recipeCount === 1 ? 'recipe' : 'recipes'} · {expanded ? 'hide' : 'show detail'}
              </span>
            </button>
          )}
          {expanded && recipeCount > 0 && (
            <div className="mt-2 rounded-[9px] bg-cream px-3 py-2.5 text-[12px] text-muted">
              <div className="mb-1 font-semibold text-ink">
                {line.contributing.map((c) => c.recipe_title).join(' · ')}
              </div>
              <div className="font-mono text-[11px] leading-relaxed">
                {line.contributing.map((c) => c.raw).join('   ·   ')}
              </div>
            </div>
          )}
        </div>
        {live && (
          <button
            onClick={onDelete}
            className="flex-none px-1 text-lg text-hint hover:text-danger"
            aria-label="Delete"
          >
            ×
          </button>
        )}
      </div>
    </div>
  )
}
