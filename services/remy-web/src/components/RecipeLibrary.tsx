// Recipe-page library widgets (COOKBOOK_PLAN items 3–4): favorite heart, star
// rating, tags (+ tag sheet), personal notes. All save through useUpdateRecipe,
// which applies them optimistically.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useRecipeTags, useUpdateRecipe } from '../lib/queries'
import type { RecipeDetail } from '../lib/types'
import { toast } from '../stores/toast'
import Icon from './Icon'
import { Button, IconButton } from './ui'

function useSave(recipe: RecipeDetail) {
  const update = useUpdateRecipe(recipe.id)
  return {
    update,
    save: (body: Parameters<typeof update.mutateAsync>[0]) =>
      update.mutateAsync(body).catch(() => {
        toast("Couldn't save — check your connection and try again")
        throw new Error('save failed')
      }),
  }
}

export function FavoriteButton({ recipe, className = '' }: { recipe: RecipeDetail; className?: string }) {
  const { save } = useSave(recipe)
  const on = recipe.is_favorite
  return (
    <button
      type="button"
      aria-label={on ? 'Remove from favorites' : 'Add to favorites'}
      aria-pressed={on}
      onClick={() => save({ is_favorite: !on }).catch(() => {})}
      className={`inline-flex h-11 w-11 items-center justify-center rounded-full bg-surface/85 backdrop-blur ${
        on ? 'text-terracotta' : 'text-ink'
      } ${className}`}
    >
      <Icon name="heart" size={20} filled={on} strokeWidth={2} />
    </button>
  )
}

export function StarRating({ recipe }: { recipe: RecipeDetail }) {
  const { save } = useSave(recipe)
  const value = recipe.rating ?? 0
  return (
    <div role="group" aria-label={value ? `Your rating: ${value} of 5` : 'Rate this recipe'} className="flex">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          aria-label={n === value ? `Clear rating (${n} of 5)` : `Rate ${n} of 5`}
          aria-pressed={n <= value}
          // Tapping the current rating clears it.
          onClick={() => save({ rating: n === value ? null : n }).catch(() => {})}
          className={`flex h-10 w-8 items-center justify-center ${n <= value ? 'text-terracotta' : 'text-line2'}`}
        >
          <Icon name="star" size={19} filled strokeWidth={0} />
        </button>
      ))}
    </div>
  )
}

export function TagRow({ recipe }: { recipe: RecipeDetail }) {
  const [editing, setEditing] = useState(false)
  return (
    <>
      <div className="flex flex-wrap gap-1.5">
        {recipe.tags.map((t) => (
          <Link
            key={t}
            to={`/app/cookbook?tag=${encodeURIComponent(t)}`}
            className="inline-flex h-8 items-center rounded-full bg-chip px-3 text-[12.5px] font-semibold text-ink hover:bg-line"
          >
            {t}
          </Link>
        ))}
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="inline-flex h-8 items-center gap-1 rounded-full border border-dashed border-faint px-3 text-[12.5px] font-semibold text-muted hover:text-ink"
        >
          <Icon name={recipe.tags.length ? 'edit' : 'plus'} size={12} strokeWidth={2.4} />
          {recipe.tags.length ? 'Tags' : 'Add tag'}
        </button>
      </div>
      {editing && <TagSheet recipe={recipe} onClose={() => setEditing(false)} />}
    </>
  )
}

function TagSheet({ recipe, onClose }: { recipe: RecipeDetail; onClose: () => void }) {
  const { save, update } = useSave(recipe)
  const all = useRecipeTags()
  const [tags, setTags] = useState<string[]>(recipe.tags)
  const [draft, setDraft] = useState('')

  const has = (t: string) => tags.some((x) => x.toLowerCase() === t.toLowerCase())
  const add = (raw: string) => {
    const t = raw.replace(/\s+/g, ' ').trim().slice(0, 40)
    if (t && !has(t)) setTags((ts) => [...ts, t])
    setDraft('')
  }
  const q = draft.trim().toLowerCase()
  const suggestions = (all.data ?? [])
    .map((t) => t.name)
    .filter((n) => !has(n) && (!q || n.toLowerCase().includes(q)))
    .slice(0, 12)

  async function done() {
    const final = draft.trim() && !has(draft.trim()) ? [...tags, draft.trim()] : tags
    try {
      await save({ tags: final })
      onClose()
    } catch {
      // toast shown; keep the sheet open
    }
  }

  return (
    <div
      className="fixed inset-0 z-30 flex animate-pop items-end justify-center bg-dark/50 sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="tags-h"
        className="flex max-h-[85%] w-full max-w-[460px] flex-col rounded-t-panel bg-surface shadow-modal sm:rounded-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-line py-3 pl-5 pr-3">
          <h2 id="tags-h" className="font-serif text-[22px] font-medium tracking-[-0.01em]">
            Tags
          </h2>
          <IconButton icon="x" label="Close" variant="plain" size={40} iconSize={18} onClick={onClose} />
        </div>
        <div className="flex flex-col gap-4 overflow-y-auto px-5 py-4">
          <div className="flex flex-wrap gap-2">
            {tags.length === 0 && <span className="text-[13.5px] text-muted">No tags yet.</span>}
            {tags.map((t) => (
              <span
                key={t}
                className="inline-flex h-9 items-center gap-1 rounded-full bg-ink pl-3.5 pr-1 text-[13.5px] font-semibold text-cream"
              >
                {t}
                <button
                  type="button"
                  aria-label={`Remove ${t}`}
                  onClick={() => setTags((ts) => ts.filter((x) => x !== t))}
                  className="flex h-7 w-7 items-center justify-center rounded-full hover:bg-cream/20"
                >
                  <Icon name="x" size={13} strokeWidth={2.6} />
                </button>
              </span>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              add(draft)
            }}
            className="flex gap-2"
          >
            <label className="sr-only" htmlFor="tag-input">
              New tag
            </label>
            <input
              id="tag-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Add a tag, e.g. weeknight"
              maxLength={40}
              autoFocus
              className="h-11 min-w-0 flex-1 rounded-[12px] border border-line2 bg-cream px-3.5 text-[15px] text-ink outline-none placeholder:text-faint focus:border-terracotta"
            />
            <Button type="submit" variant="secondary" className="h-11 px-4 text-[14px]" disabled={!draft.trim()}>
              Add
            </Button>
          </form>
          {suggestions.length > 0 && (
            <div>
              <div className="text-[11.5px] font-bold uppercase tracking-[.07em] text-faint">
                {q ? 'Matching tags' : 'Your tags'}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {suggestions.map((n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => add(n)}
                    className="inline-flex h-9 items-center gap-1 rounded-full border border-line bg-surface px-3 text-[13.5px] font-semibold text-ink hover:bg-cream"
                  >
                    <Icon name="plus" size={12} strokeWidth={2.4} />
                    {n}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="flex flex-none gap-2.5 border-t border-line px-5 py-3.5">
          <Button variant="secondary" className="h-[50px] flex-1 text-[15px]" onClick={onClose}>
            Cancel
          </Button>
          <Button className="h-[50px] flex-[2] text-[15px]" onClick={done} busy={update.isPending}>
            Save tags
          </Button>
        </div>
      </div>
    </div>
  )
}

export function NotesCard({ recipe }: { recipe: RecipeDetail }) {
  const { save, update } = useSave(recipe)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(recipe.notes ?? '')

  if (!editing && !recipe.notes) {
    return (
      <button
        type="button"
        onClick={() => {
          setDraft('')
          setEditing(true)
        }}
        className="flex min-h-[52px] w-full items-center gap-3 rounded-card border border-dashed border-line2 px-4 text-left text-[14.5px] font-semibold text-muted hover:text-ink"
      >
        <Icon name="edit" size={17} strokeWidth={2} />
        Add a note — tweaks, swaps, what you'd do differently
      </button>
    )
  }

  return (
    <section aria-labelledby="notes-h" className="rounded-card bg-warn-bg px-[18px] py-4 text-warn-deep">
      <div className="flex items-center justify-between">
        <h2 id="notes-h" className="text-[12.5px] font-bold uppercase tracking-[.07em]">
          Your notes
        </h2>
        {!editing && (
          <button
            type="button"
            onClick={() => {
              setDraft(recipe.notes ?? '')
              setEditing(true)
            }}
            className="h-9 px-1 text-[13.5px] font-bold underline underline-offset-2"
          >
            Edit
          </button>
        )}
      </div>
      {editing ? (
        <div className="mt-2.5">
          <label htmlFor="notes-input" className="sr-only">
            Your notes
          </label>
          <textarea
            id="notes-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={4}
            maxLength={5000}
            autoFocus
            placeholder="Used half the salt; pecorino works fine."
            className="w-full resize-y rounded-[12px] border border-warn-border bg-surface px-3.5 py-2.5 font-serif text-[16.5px] leading-[1.45] text-ink outline-none placeholder:text-faint focus:border-terracotta"
          />
          <div className="mt-2.5 flex gap-2.5">
            <Button variant="secondary" className="h-11 flex-1 text-[14px]" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button
              className="h-11 flex-[2] text-[14px]"
              busy={update.isPending}
              onClick={() =>
                save({ notes: draft.trim() || null })
                  .then(() => setEditing(false))
                  .catch(() => {})
              }
            >
              Save note
            </Button>
          </div>
        </div>
      ) : (
        <p className="mt-2 whitespace-pre-line font-serif text-[17px] leading-[1.45]">{recipe.notes}</p>
      )}
    </section>
  )
}
