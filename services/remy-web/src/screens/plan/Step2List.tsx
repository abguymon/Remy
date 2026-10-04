// Plan step 2 — review shopping list (DESIGN_BRIEF §4.4). Edit register: three
// groups (To buy / Excluded by you / Pantry — skipping), consolidated qty +
// contributing-recipe expansion, conflict display, qty edit, delete, add-item
// row, and a sticky "Find products at {store} →" bar.
import { useState } from 'react'
import { ApiError } from '../../lib/api'
import { useApproveList, useListEdits, useSettings } from '../../lib/queries'
import type { ListEdit, ListLine, PlanSnapshot } from '../../lib/types'
import { toast } from '../../stores/toast'
import { Button, IconButton, ScreenHeader, SectionLabel, Spinner, StickyBar } from '../../components/ui'
import Icon from '../../components/Icon'

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
      <div className="px-5 pt-4">
        <div className="flex items-center gap-2 py-3 text-[13.5px] text-muted">
          <Spinner /> Building your shopping list…
        </div>
        <div className="overflow-hidden rounded-card border border-line bg-surface" aria-hidden>
          {[78, 55, 66, 48, 72].map((w, i) => (
            <div key={i} className="flex items-center gap-3 border-b border-divider px-3.5 py-3.5 last:border-0">
              <div className="sk h-6 w-6 flex-none rounded-[7px]" />
              <div className="flex-1">
                <div className="sk h-3.5 rounded" style={{ width: `${w}%` }} />
                <div className="sk mt-2 h-2.5 w-20 rounded" />
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="no-scrollbar flex-1 overflow-y-auto pb-8">
        <ScreenHeader
          className="!pt-4"
          title="Review your list"
          subtitle="Merged across your recipes. Uncheck anything you already have."
        />

        <div className="px-5">
          {/* To buy */}
          <div className="mb-2.5 mt-6 flex items-center gap-2">
            <SectionLabel tone="success" className="flex items-center gap-1.5">
              <Icon name="cart" size={14} strokeWidth={2.2} />
              To buy
            </SectionLabel>
            <span className="tab-fig rounded-full bg-success-bg px-2 py-0.5 text-[11px] font-bold text-success">
              {toBuy.length}
            </span>
          </div>
          <div className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
            {toBuy.map((line) => (
              <LineRow
                key={line.id}
                line={line}
                live={live}
                expanded={!!expanded[line.id]}
                editingQty={editingQty === line.id}
                onToggleExpand={() => setExpanded((e) => ({ ...e, [line.id]: !e[line.id] }))}
                onCheck={() => edit({ op: 'exclude', line_id: line.id })}
                onDelete={() => edit({ op: 'delete', line_id: line.id })}
                onStartEditQty={() => setEditingQty(line.id)}
                onCommitQty={(q) => {
                  setEditingQty(null)
                  if (q != null)
                    edit({ op: 'set_quantity', line_id: line.id, quantity: q, unit: line.unit })
                }}
              />
            ))}
            {live && (
              <>
                {addOpen ? (
                  <div className="flex gap-2 border-t border-divider p-3 first:border-0">
                    <input
                      autoFocus
                      value={addText}
                      onChange={(e) => setAddText(e.target.value)}
                      placeholder="e.g. 1 bunch parsley"
                      aria-label="New item"
                      className="h-11 min-w-0 flex-1 rounded-[12px] border border-line2 bg-cream px-3.5 text-[14.5px] text-ink outline-none placeholder:text-faint focus:border-terracotta"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && addText.trim()) {
                          edit({ op: 'add', text: addText.trim() })
                          setAddText('')
                          setAddOpen(false)
                        }
                      }}
                    />
                    <Button
                      className="h-11 px-4 text-[13.5px]"
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
                    type="button"
                    onClick={() => setAddOpen(true)}
                    className="flex min-h-[48px] w-full items-center gap-3 border-t border-divider px-3.5 text-left text-[14px] font-semibold text-terracotta-deep first:border-0 hover:bg-cream"
                  >
                    <span className="flex h-6 w-6 flex-none items-center justify-center rounded-[7px] border-[1.5px] border-dashed border-terracotta/60">
                      <Icon name="plus" size={14} strokeWidth={2.6} />
                    </span>
                    Add an item
                  </button>
                )}
              </>
            )}
          </div>

          {/* Excluded by you */}
          {excluded.length > 0 && (
            <>
              <SectionLabel className="mb-2.5 mt-7">Excluded by you</SectionLabel>
              <div className="overflow-hidden rounded-card border border-dashed border-line2 bg-chip/40">
                {excluded.map((line) => (
                  <div
                    key={line.id}
                    className="flex min-h-[48px] items-center gap-1 border-b border-line/70 pr-3.5 last:border-0"
                  >
                    <button
                      type="button"
                      onClick={() => live && edit({ op: 'include', line_id: line.id })}
                      className="flex h-12 w-12 flex-none items-center justify-center"
                      aria-label="Add back"
                    >
                      <span className="h-6 w-6 rounded-[7px] border-[1.5px] border-hint bg-surface" />
                    </button>
                    <div className="flex-1 text-[14.5px] text-faint line-through">{line.display}</div>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Pantry — skipping */}
          {pantry.length > 0 && (
            <>
              <SectionLabel className="mb-1 mt-7 flex items-center gap-1.5">
                <Icon name="pantry" size={14} strokeWidth={2.2} />
                Pantry — skipping
              </SectionLabel>
              <div className="mb-2.5 text-[12.5px] text-faint">
                You told us you keep these on hand. Tap to add back.
              </div>
              <div className="overflow-hidden rounded-card border border-line bg-surface">
                {pantry.map((line) => (
                  <div
                    key={line.id}
                    className="flex min-h-[48px] items-center gap-1 border-b border-divider pr-3.5 last:border-0"
                  >
                    <button
                      type="button"
                      onClick={() => live && edit({ op: 'include', line_id: line.id })}
                      className="flex h-12 w-12 flex-none items-center justify-center"
                      aria-label="Add back"
                    >
                      <span className="h-6 w-6 rounded-[7px] border-[1.5px] border-line2 bg-cream" />
                    </button>
                    <div className="flex-1 text-[14.5px] text-muted">{line.display}</div>
                    <span className="rounded-full bg-chip px-2 py-0.5 text-[11px] font-semibold text-faint">
                      pantry
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Pinned to the bottom of the app's scrolling <main> so the action
          (and the live total) stays in reach while the list scrolls. */}
      <div className="sticky bottom-0 z-10">
        <StickyBar>
          <Button
            className="h-[54px] w-full text-[16px] font-bold"
            busy={approve.isPending}
            disabled={!live || approve.isPending}
            onClick={onApprove}
          >
            {approve.isPending ? (
              'Finding products…'
            ) : (
              <>
                <span className="truncate">Find products at {storeName}</span>
                <Icon name="chevronRight" size={18} strokeWidth={2.4} className="flex-none" />
              </>
            )}
          </Button>
        </StickyBar>
      </div>
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
    <div className="border-b border-divider py-1 pr-1 last:border-0">
      <div className="flex items-start gap-1">
        <button
          type="button"
          onClick={() => live && onCheck()}
          className="flex h-11 w-12 flex-none items-center justify-center"
          aria-label="Exclude"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-[7px] bg-success text-onaccent">
            <Icon name="check" size={15} strokeWidth={3} />
          </span>
        </button>
        <div className="min-w-0 flex-1 py-2">
          {editingQty ? (
            <div className="-my-1.5 flex items-center gap-2">
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
                aria-label="Quantity"
                className="tab-fig h-9 w-20 rounded-[10px] border border-terracotta bg-cream px-2.5 text-[15px] text-ink outline-none"
              />
              <span className="text-[15px] text-muted">
                {line.unit ? `${line.unit} ` : ''}
                {line.food}
              </span>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => live && onStartEditQty()}
              className="tab-fig text-left text-[15px] font-semibold leading-snug text-ink"
            >
              {line.display}
            </button>
          )}
          {recipeCount > 0 && (
            <button
              type="button"
              onClick={onToggleExpand}
              aria-expanded={expanded}
              className="mt-1 flex flex-wrap items-center gap-1.5 text-[12.5px] text-faint hover:text-ink"
            >
              {line.conflict && (
                <span className="inline-flex items-center gap-1 rounded-full bg-warn-bg px-2 py-0.5 text-[11px] font-semibold text-warn">
                  <Icon name="alert" size={11} strokeWidth={2.4} />
                  mixed units
                </span>
              )}
              <span>
                {recipeCount} {recipeCount === 1 ? 'recipe' : 'recipes'} · {expanded ? 'hide' : 'show detail'}
              </span>
              <Icon
                name="chevronDown"
                size={13}
                strokeWidth={2.4}
                className={`transition-transform ${expanded ? 'rotate-180' : ''}`}
              />
            </button>
          )}
          {expanded && recipeCount > 0 && (
            <div className="mt-2.5 rounded-[12px] border border-line bg-cream px-3 py-2.5 text-[12px] text-muted">
              <div className="mb-1 flex items-start gap-1.5 font-semibold text-ink">
                <Icon name="book" size={13} className="mt-px flex-none text-faint" />
                {line.contributing.map((c) => c.recipe_title).join(' · ')}
              </div>
              <div className="font-mono text-[11px] leading-relaxed">
                {line.contributing.map((c) => c.raw).join('   ·   ')}
              </div>
            </div>
          )}
        </div>
        {live && (
          <IconButton
            icon="trash"
            label="Delete"
            variant="plain"
            iconSize={17}
            onClick={onDelete}
            className="!text-faint hover:!bg-danger-bg hover:!text-danger"
          />
        )}
      </div>
    </div>
  )
}
