// Cookbook (DESIGN_BRIEF §4.7) — browse register. Search + 2-col photo card
// grid; "Add recipe" opens a paste-URL sheet with parse progress and a parsed
// preview. Empty first-run and no-results states included.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { cookedLabel } from '../lib/format'
import { useCreateRecipeFromUrl, useRecipes } from '../lib/queries'
import type { RecipeDetail, RecipeSummary } from '../lib/types'
import { AuthedImage, Button, EmptyState, Spinner } from '../components/ui'

function domainOf(url: string | null): string {
  if (!url) return ''
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

export default function Cookbook() {
  const [search, setSearch] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const recipes = useRecipes(search)
  const navigate = useNavigate()

  const items = recipes.data ?? []
  const isSearching = search.trim().length > 0

  return (
    <div className="px-5 pb-8 pt-3.5">
      <div className="font-serif text-[28px] font-semibold tracking-tight">Cookbook</div>

      <div className="relative my-3.5">
        <input
          placeholder="Search recipes"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-[11px] border border-line2 bg-surface px-3.5 py-3 text-sm outline-none focus:border-terracotta"
        />
      </div>

      {recipes.isLoading ? (
        <CardGrid>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i}>
              <div className="sk h-[130px] rounded-card" />
              <div className="sk mt-2 h-3.5 w-[85%] rounded" />
              <div className="sk mt-1.5 h-3 w-[55%] rounded" />
            </div>
          ))}
        </CardGrid>
      ) : items.length === 0 ? (
        isSearching ? (
          <EmptyState glyph="🔍" message={`No recipes match "${search.trim()}".`} />
        ) : (
          <EmptyState
            glyph="📖"
            message="Recipes you pick get saved here automatically — or paste a URL to add one."
            action={
              <Button className="mt-1 px-4 py-2.5 text-sm" onClick={() => setAddOpen(true)}>
                Add a recipe by URL
              </Button>
            }
          />
        )
      ) : (
        <CardGrid>
          {items.map((r) => (
            <RecipeCard key={r.id} recipe={r} onOpen={() => navigate(`/cookbook/${r.id}`)} />
          ))}
        </CardGrid>
      )}

      {items.length > 0 && (
        <button
          onClick={() => setAddOpen(true)}
          className="mt-4 w-full rounded-card border border-dashed border-[#D8CDB9] bg-transparent py-3.5 text-sm font-semibold text-terracotta"
        >
          ＋ Add a recipe by URL
        </button>
      )}

      {addOpen && (
        <AddRecipeSheet
          onClose={() => setAddOpen(false)}
          onView={(id) => {
            setAddOpen(false)
            navigate(`/cookbook/${id}`)
          }}
        />
      )}
    </div>
  )
}

function CardGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3.5 lg:grid-cols-3">{children}</div>
}

function RecipeCard({ recipe, onOpen }: { recipe: RecipeSummary; onOpen: () => void }) {
  const domain = domainOf(recipe.source_url)
  const meta = [domain, cookedLabel(recipe.last_cooked_at)].filter(Boolean).join(' · ')
  return (
    <button onClick={onOpen} className="cursor-pointer text-left">
      <div className="h-[130px] overflow-hidden rounded-card border border-line2">
        <AuthedImage path={recipe.image_url} alt={recipe.title} label="photo" />
      </div>
      <div className="mt-2 line-clamp-2 font-serif text-[14.5px] font-semibold leading-tight text-ink">
        {recipe.title}
      </div>
      <div className="mt-0.5 text-[11.5px] text-faint">{meta}</div>
    </button>
  )
}

// --- Add recipe by URL sheet -----------------------------------------------

function AddRecipeSheet({
  onClose,
  onView,
}: {
  onClose: () => void
  onView: (id: string) => void
}) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [added, setAdded] = useState<RecipeDetail | null>(null)
  const create = useCreateRecipeFromUrl()

  async function submit() {
    if (!url.trim()) return
    setError(null)
    try {
      const recipe = await create.mutateAsync(url.trim())
      setAdded(recipe)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.code === 'recipe_parse_failed'
            ? `Couldn't read that page — ${err.message}`
            : err.message,
        )
      } else {
        setError('Something went wrong. Try another URL.')
      }
    }
  }

  return (
    <div
      className="absolute inset-0 z-30 flex animate-pop items-end justify-center sm:items-center"
      style={{ background: 'rgba(40,30,20,.4)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-[420px] rounded-t-[22px] bg-surface p-[22px] shadow-modal sm:rounded-[18px]"
        onClick={(e) => e.stopPropagation()}
      >
        {added ? (
          <>
            <div className="font-serif text-xl font-semibold">Added to your cookbook</div>
            <div className="mt-3 flex gap-3">
              <div className="h-[64px] w-[64px] flex-none overflow-hidden rounded-[11px] border border-line2">
                <AuthedImage path={added.image_url} alt={added.title} label="photo" />
              </div>
              <div className="min-w-0">
                <div className="line-clamp-2 font-serif text-[15px] font-semibold leading-tight">
                  {added.title}
                </div>
                <div className="mt-1 text-[12px] text-muted">
                  {added.ingredients.length} ingredients · {added.instructions.length} steps
                </div>
              </div>
            </div>
            <div className="mt-4 flex gap-2.5">
              <Button variant="secondary" className="flex-1 py-3 text-sm" onClick={onClose}>
                Done
              </Button>
              <Button className="flex-1 py-3 text-sm" onClick={() => onView(added.id)}>
                View recipe
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="font-serif text-xl font-semibold">Add a recipe</div>
            <div className="mt-1.5 text-[13px] text-muted">
              Paste a recipe URL — we'll read the ingredients and steps.
            </div>
            {error && (
              <div className="mt-3 rounded-[10px] border border-danger-border bg-danger-bg px-3 py-2.5 text-[13px] text-danger">
                {error}
              </div>
            )}
            <input
              autoFocus
              placeholder="https://…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !create.isPending && submit()}
              disabled={create.isPending}
              className="mt-3 w-full rounded-[11px] border border-line2 bg-cream px-3.5 py-3 text-sm outline-none focus:border-terracotta disabled:opacity-60"
            />
            {create.isPending && (
              <div className="mt-3 flex items-center gap-2 text-[12.5px] text-muted">
                <Spinner /> Reading the page… this can take a few seconds.
              </div>
            )}
            <div className="mt-4 flex gap-2.5">
              <Button
                variant="secondary"
                className="flex-1 py-3 text-sm"
                onClick={onClose}
                disabled={create.isPending}
              >
                Cancel
              </Button>
              <Button
                className="flex-1 py-3 text-sm"
                onClick={submit}
                disabled={create.isPending || !url.trim()}
              >
                {create.isPending ? 'Reading…' : 'Add recipe'}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
