// Recipe detail (DESIGN_BRIEF §4.8) — the most editorial screen. Full-bleed
// photo, serif title, meta row, ingredients, numbered steps. Actions: "I cooked
// this" (stamps last_cooked_at), edit (sheet → PUT), delete (confirm), open
// original.
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { cookedLabel } from '../lib/format'
import {
  useDeleteRecipe,
  useMarkCooked,
  useRecipe,
  useUpdateRecipe,
} from '../lib/queries'
import type { RecipeDetail as Recipe } from '../lib/types'
import { toast } from '../stores/toast'
import { AuthedImage, Button, ConfirmDialog, EmptyState } from '../components/ui'

function domainOf(url: string | null): string {
  if (!url) return ''
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

export default function RecipeDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const recipe = useRecipe(id)
  const cooked = useMarkCooked(id ?? '')
  const del = useDeleteRecipe()
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (recipe.isLoading) {
    return (
      <div className="pb-8">
        <div className="sk h-[230px]" />
        <div className="px-[22px] pt-4">
          <div className="sk h-7 w-3/4 rounded" />
          <div className="sk mt-3 h-4 w-1/2 rounded" />
        </div>
      </div>
    )
  }

  if (recipe.isError || !recipe.data) {
    return (
      <div className="px-5 py-16">
        <EmptyState
          glyph="🧭"
          message="That recipe isn't here."
          action={
            <button
              onClick={() => navigate('/cookbook')}
              className="mt-1 text-[13.5px] font-semibold text-terracotta"
            >
              Back to Cookbook
            </button>
          }
        />
      </div>
    )
  }

  const r = recipe.data
  const domain = domainOf(r.source_url)
  const meta: { label: string; value: string }[] = []
  if (r.recipe_yield) meta.push({ label: 'Yield', value: r.recipe_yield })
  if (r.prep_time) meta.push({ label: 'Prep', value: r.prep_time })
  if (r.cook_time) meta.push({ label: 'Cook', value: r.cook_time })
  if (!r.prep_time && !r.cook_time && r.total_time)
    meta.push({ label: 'Total', value: r.total_time })

  return (
    <div className="pb-9">
      {/* Full-bleed image + back */}
      <div className="relative h-[230px]">
        <AuthedImage path={r.image_url} alt={r.title} label="recipe photo" />
        <button
          onClick={() => navigate('/cookbook')}
          aria-label="Back to Cookbook"
          className="absolute left-3.5 top-3.5 flex h-9 w-9 items-center justify-center rounded-full bg-surface/85 text-lg text-ink"
        >
          ←
        </button>
      </div>

      <div className="px-[22px] pt-4">
        <div className="font-serif text-[27px] font-semibold leading-[1.12] tracking-tight">
          {r.title}
        </div>

        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-muted">
          {r.source_url && (
            <a
              href={r.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-terracotta"
            >
              {domain || 'Original'}
            </a>
          )}
          {meta.map((m) => (
            <span key={m.label}>
              {m.label} · {m.value}
            </span>
          ))}
          {r.last_cooked_at && <span>{cookedLabel(r.last_cooked_at)}</span>}
        </div>

        <div className="mt-4 flex gap-2.5">
          <Button
            className="flex-1 py-3 text-sm"
            busy={cooked.isPending}
            disabled={cooked.isPending}
            onClick={async () => {
              await cooked.mutateAsync()
              toast('Marked as cooked')
            }}
          >
            {cooked.isPending ? 'Marking cooked…' : 'I cooked this'}
          </Button>
          <Button
            variant="secondary"
            className="px-5 py-3 text-sm"
            onClick={() => setEditing(true)}
          >
            Edit
          </Button>
        </div>

        {r.ingredients.length > 0 && (
          <>
            <div className="mb-2.5 mt-6 font-serif text-[19px] font-semibold">Ingredients</div>
            <div className="overflow-hidden rounded-[13px] border border-line bg-surface">
              {r.ingredients.map((ing) => (
                <div
                  key={ing.id}
                  className="border-b border-divider px-3.5 py-2.5 text-sm text-ink last:border-0"
                >
                  {ing.raw}
                </div>
              ))}
            </div>
          </>
        )}

        {r.instructions.length > 0 && (
          <>
            <div className="mb-2.5 mt-6 font-serif text-[19px] font-semibold">Instructions</div>
            <div className="flex flex-col gap-3.5">
              {r.instructions.map((step, i) => (
                <div key={i} className="flex gap-3">
                  <span className="tab-fig flex h-7 w-7 flex-none items-center justify-center rounded-full bg-terracotta-soft font-serif text-sm font-semibold text-terracotta-deep">
                    {i + 1}
                  </span>
                  <div className="pt-0.5 text-[14.5px] leading-relaxed text-[#3A342C]">{step}</div>
                </div>
              ))}
            </div>
          </>
        )}

        <button
          onClick={() => setConfirmDelete(true)}
          className="mt-8 w-full rounded-xl border border-danger-border py-3 text-sm font-semibold text-danger hover:bg-danger-bg"
        >
          Delete recipe
        </button>
      </div>

      {editing && <EditSheet recipe={r} onClose={() => setEditing(false)} />}

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this recipe?"
        body="This removes it from your cookbook. This can't be undone."
        confirmLabel="Delete"
        destructive
        onCancel={() => setConfirmDelete(false)}
        onConfirm={async () => {
          await del.mutateAsync(r.id)
          setConfirmDelete(false)
          toast('Recipe deleted')
          navigate('/cookbook')
        }}
      />
    </div>
  )
}

// --- Edit sheet ------------------------------------------------------------

function EditSheet({ recipe, onClose }: { recipe: Recipe; onClose: () => void }) {
  const update = useUpdateRecipe(recipe.id)
  const [title, setTitle] = useState(recipe.title)
  const [recipeYield, setRecipeYield] = useState(recipe.recipe_yield ?? '')
  const [prep, setPrep] = useState(recipe.prep_time ?? '')
  const [cook, setCook] = useState(recipe.cook_time ?? '')
  const [ingredients, setIngredients] = useState(recipe.ingredients.map((i) => i.raw).join('\n'))
  const [instructions, setInstructions] = useState(recipe.instructions.join('\n'))

  async function save() {
    const ingLines = ingredients
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
    const stepLines = instructions
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean)
    await update.mutateAsync({
      title: title.trim() || recipe.title,
      recipe_yield: recipeYield.trim() || null,
      prep_time: prep.trim() || null,
      cook_time: cook.trim() || null,
      ingredients: ingLines.map((raw) => ({ raw })),
      instructions: stepLines,
    })
    toast('Recipe updated')
    onClose()
  }

  const field =
    'w-full rounded-[10px] border border-line2 bg-cream px-3 py-2.5 text-sm outline-none focus:border-terracotta'
  const labelCls = 'text-xs font-bold uppercase tracking-[.06em] text-hint'

  return (
    <div
      className="absolute inset-0 z-30 flex animate-pop items-end justify-center"
      style={{ background: 'rgba(40,30,20,.4)' }}
      onClick={onClose}
    >
      <div
        className="flex max-h-[92%] w-full max-w-[480px] flex-col rounded-t-[22px] bg-surface shadow-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-divider px-5 py-3.5">
          <div className="font-serif text-lg font-semibold">Edit recipe</div>
          <button onClick={onClose} className="text-sm font-semibold text-muted">
            Cancel
          </button>
        </div>
        <div className="flex flex-col gap-3.5 overflow-y-auto px-5 py-4">
          <label className="flex flex-col gap-1.5">
            <span className={labelCls}>Title</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} className={field} />
          </label>
          <div className="grid grid-cols-3 gap-2.5">
            <label className="flex flex-col gap-1.5">
              <span className={labelCls}>Yield</span>
              <input
                value={recipeYield}
                onChange={(e) => setRecipeYield(e.target.value)}
                className={field}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className={labelCls}>Prep</span>
              <input value={prep} onChange={(e) => setPrep(e.target.value)} className={field} />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className={labelCls}>Cook</span>
              <input value={cook} onChange={(e) => setCook(e.target.value)} className={field} />
            </label>
          </div>
          <label className="flex flex-col gap-1.5">
            <span className={labelCls}>Ingredients — one per line</span>
            <textarea
              value={ingredients}
              onChange={(e) => setIngredients(e.target.value)}
              rows={7}
              className={`${field} resize-none font-mono text-[12.5px] leading-relaxed`}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className={labelCls}>Instructions — one step per line</span>
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={7}
              className={`${field} resize-none leading-relaxed`}
            />
          </label>
        </div>
        <div className="flex-none border-t border-divider px-5 py-3.5">
          <Button
            className="w-full py-3.5 text-[15px]"
            onClick={save}
            busy={update.isPending}
            disabled={update.isPending}
          >
            {update.isPending ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      </div>
    </div>
  )
}
