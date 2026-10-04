// Recipe detail (DESIGN_BRIEF §4.8, visual language v2 §8) — the most
// editorial screen. Tall photo with glass back button, a cream sheet that
// overlaps it, serif title, source link, a stat strip, then ingredients (tap to
// tick off while cooking — local only) and big-numeral method steps.
// Actions: "I cooked this" (stamps last_cooked_at), edit (sheet → PUT),
// delete (confirm), open original.
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { pluralize, shortDate } from '../lib/format'
import { useDeleteRecipe, useMarkCooked, useRecipe, useUpdateRecipe } from '../lib/queries'
import type { RecipeDetail as Recipe } from '../lib/types'
import { toast } from '../stores/toast'
import Icon from '../components/Icon'
import {
  AuthedImage,
  Button,
  ConfirmDialog,
  EmptyState,
  IconButton,
  SectionHeading,
} from '../components/ui'

function domainOf(url: string | null): string {
  if (!url) return ''
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

// Split a raw ingredient line into a leading amount ("1 ½ pounds", "3 or 4",
// "½ cup") and the rest, so the amount can be set in bold. Display only — the
// raw text is shown unchanged; lines without a leading amount stay whole.
const NUM = String.raw`(?:\d+(?:[./]\d+)?(?:\s*[½⅓⅔¼¾⅛⅜⅝⅞])?|[½⅓⅔¼¾⅛⅜⅝⅞])`
const UNIT = String.raw`(?:cups?|tablespoons?|tbsps?|tbsp|teaspoons?|tsps?|tsp|pounds?|lbs?|ounces?|oz|grams?|g|kilograms?|kg|ml|milliliters?|liters?|l|cloves?|cans?|pinch(?:es)?|quarts?|pints?|sticks?|bunch(?:es)?)`
const AMOUNT = new RegExp(String.raw`^(${NUM}(?:\s*(?:-|–|to|or)\s*${NUM})?(?:\s+${UNIT}\.?(?=\s))?)\s+(.+)$`, 'i')

function splitAmount(raw: string): { amount: string; rest: string } {
  const m = AMOUNT.exec(raw.trim())
  return m ? { amount: m[1], rest: m[2] } : { amount: '', rest: raw }
}

// "6 servings" → Serves 6; anything else stays a free-text yield.
function yieldStat(y: string): { label: string; value: string } {
  const m = /^(\d+(?:\s*(?:-|–|to)\s*\d+)?)\s*(?:servings?|people|portions?)?$/i.exec(y.trim())
  return m ? { label: 'Serves', value: m[1] } : { label: 'Yield', value: y }
}

export default function RecipeDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const recipe = useRecipe(id)
  const cooked = useMarkCooked(id ?? '')
  const del = useDeleteRecipe()
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [ticked, setTicked] = useState<Set<string>>(() => new Set())

  const back = () => navigate('/app/cookbook')

  if (recipe.isLoading) {
    return (
      <div className="pb-8" aria-busy>
        <div className="sk h-[330px] lg:h-[400px]" />
        <div className="relative -mt-6 rounded-t-[24px] bg-cream px-5 pt-6">
          <div className="sk h-9 w-3/4 rounded" />
          <div className="sk mt-3 h-4 w-1/3 rounded" />
          <div className="sk mt-5 h-[68px] rounded-card" />
          <div className="sk mt-4 h-[54px] rounded-card" />
        </div>
      </div>
    )
  }

  if (recipe.isError || !recipe.data) {
    return (
      <div className="px-5 py-16">
        <EmptyState
          icon="info"
          message="That recipe isn't here."
          action={
            <Button variant="secondary" className="mt-1 h-11 px-5 text-sm" onClick={back}>
              <Icon name="back" size={16} strokeWidth={2.2} />
              Back to Cookbook
            </Button>
          }
        />
      </div>
    )
  }

  const r = recipe.data
  const domain = domainOf(r.source_url)

  const stats: { label: string; value: string }[] = []
  if (r.total_time) stats.push({ label: 'Total', value: r.total_time })
  if (r.prep_time) stats.push({ label: 'Prep', value: r.prep_time })
  if (r.cook_time) stats.push({ label: 'Cook', value: r.cook_time })
  if (r.recipe_yield) stats.push(yieldStat(r.recipe_yield))
  const statCols = ['', 'grid-cols-1', 'grid-cols-2', 'grid-cols-3', 'grid-cols-4'][stats.length]

  function toggle(ingId: string) {
    setTicked((prev) => {
      const next = new Set(prev)
      if (next.has(ingId)) next.delete(ingId)
      else next.add(ingId)
      return next
    })
  }

  return (
    <div className="pb-10">
      {/* Photo + glass back button */}
      <div className="relative h-[330px] bg-tile lg:h-[400px]">
        <AuthedImage path={r.image_url} alt={r.title} label="recipe photo" />
        <IconButton
          icon="back"
          label="Back to Cookbook"
          variant="glass"
          onClick={back}
          className="absolute left-4 top-4"
        />
        <IconButton
          icon="edit"
          label="Edit recipe"
          variant="glass"
          iconSize={19}
          onClick={() => setEditing(true)}
          className="absolute right-4 top-4"
        />
      </div>

      <div className="relative -mt-6 rounded-t-[24px] bg-cream px-5 pt-6 lg:px-8">
        <h1 className="font-serif text-[34px] font-medium leading-[1.05] tracking-[-0.02em] text-ink lg:text-[40px]">
          {r.title}
        </h1>

        {r.source_url && (
          <a
            href={r.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2.5 inline-flex min-h-[32px] items-center gap-[5px] text-[13.5px] font-semibold text-terracotta-deep hover:text-terracotta"
          >
            {domain || 'Original recipe'}
            <Icon name="external" size={13} strokeWidth={2.2} />
          </a>
        )}

        {stats.length > 0 && (
          <dl
            className={`mt-4 grid ${statCols} divide-x divide-line overflow-hidden rounded-card border border-line bg-surface`}
          >
            {stats.map((s) => (
              <div key={s.label} className="min-w-0 px-3.5 py-3">
                <dt className="text-[11.5px] font-semibold uppercase tracking-[.06em] text-muted">
                  {s.label}
                </dt>
                <dd className="mt-[3px] text-[16px] font-semibold leading-tight text-ink">{s.value}</dd>
              </div>
            ))}
          </dl>
        )}

        <div className="lg:flex lg:gap-2.5">
          <Button
            className="mt-4 h-[54px] w-full !rounded-card text-[16.5px] font-bold lg:flex-[2]"
            busy={cooked.isPending}
            disabled={cooked.isPending}
            onClick={async () => {
              await cooked.mutateAsync()
              toast('Marked as cooked')
            }}
          >
            {!cooked.isPending && <Icon name="check" size={20} strokeWidth={2.4} />}
            {cooked.isPending ? 'Marking cooked…' : 'I cooked this'}
          </Button>
          <div className={`mt-2.5 grid gap-2.5 lg:mt-4 lg:flex-[2] ${r.source_url ? 'grid-cols-2' : 'grid-cols-1'}`}>
            <Button
              variant="secondary"
              className="h-[46px] !border-line text-[14px] lg:h-[54px]"
              onClick={() => setEditing(true)}
            >
              <Icon name="edit" size={17} strokeWidth={2} />
              Edit recipe
            </Button>
            {r.source_url && (
              <a
                href={r.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-[46px] items-center justify-center gap-2 rounded-[14px] border border-line bg-surface text-[14px] font-semibold text-ink hover:bg-cream lg:h-[54px]"
              >
                <Icon name="external" size={17} strokeWidth={2} />
                Original
              </a>
            )}
          </div>
        </div>
        <div className="mt-2.5 text-center text-[13px] text-muted">
          {r.last_cooked_at ? `Last cooked ${shortDate(r.last_cooked_at)}` : 'Not cooked yet'}
        </div>

        <div className="lg:mt-4 lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-10">
          {r.ingredients.length > 0 && (
            <section aria-labelledby="ing-h" className="mt-[30px] lg:mt-6">
              <SectionHeading id="ing-h" className="[&_h2]:text-[24px]" action={
                <span className="text-[13px] font-medium text-muted">
                  {ticked.size > 0
                    ? `${ticked.size} of ${r.ingredients.length}`
                    : pluralize(r.ingredients.length, 'item')}
                </span>
              }>
                Ingredients
              </SectionHeading>
              <ul className="mt-2">
                {r.ingredients.map((ing) => {
                  const done = ticked.has(ing.id)
                  const { amount, rest } = splitAmount(ing.raw)
                  return (
                    <li key={ing.id} className="border-b border-line">
                      <button
                        type="button"
                        aria-pressed={done}
                        onClick={() => toggle(ing.id)}
                        className={`flex min-h-[52px] w-full items-start gap-3.5 py-3 text-left transition-opacity ${
                          done ? 'opacity-55' : ''
                        }`}
                      >
                        <span
                          className={`mt-px flex h-[22px] w-[22px] flex-none items-center justify-center rounded-full border-[1.6px] ${
                            done
                              ? 'border-terracotta bg-terracotta text-onaccent'
                              : 'border-line2 text-transparent'
                          }`}
                        >
                          <Icon name="check" size={13} strokeWidth={3} />
                        </span>
                        <span
                          className={`min-w-0 flex-1 text-[15.5px] leading-[1.4] text-ink ${
                            done ? 'line-through' : ''
                          }`}
                        >
                          {amount && <strong className="font-bold">{amount} </strong>}
                          {rest}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>
          )}

          {r.instructions.length > 0 && (
            <section aria-labelledby="steps-h" className="mt-8 lg:mt-6">
              <SectionHeading id="steps-h" className="[&_h2]:text-[24px]">
                Method
              </SectionHeading>
              <ol className="mt-3.5 flex flex-col gap-[22px]">
                {r.instructions.map((step, i) => (
                  <Step key={i} n={i + 1}>
                    {step}
                  </Step>
                ))}
              </ol>
            </section>
          )}
        </div>

        <div className="mt-9 flex justify-center border-t border-line pt-4">
          <button
            onClick={() => setConfirmDelete(true)}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-full px-4 text-[13.5px] font-semibold text-muted hover:bg-danger-bg hover:text-danger"
          >
            <Icon name="trash" size={16} strokeWidth={2} />
            Delete recipe
          </button>
        </div>
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
          navigate('/app/cookbook')
        }}
      />
    </div>
  )
}

function Step({ n, children }: { n: number; children: ReactNode }) {
  return (
    <li className="flex gap-3.5">
      <span className="tab-fig w-6 flex-none font-serif text-[30px] leading-none text-terracotta-deep" aria-hidden>
        {n}
      </span>
      <p className="min-w-0 text-[15.5px] leading-[1.6] text-ink">
        <span className="sr-only">Step {n}. </span>
        {children}
      </p>
    </li>
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
    'w-full rounded-[12px] border border-line2 bg-cream px-3.5 py-2.5 text-[15px] text-ink outline-none placeholder:text-faint focus:border-terracotta'
  const labelCls = 'text-[11.5px] font-bold uppercase tracking-[.07em] text-faint'

  return (
    <div
      className="fixed inset-0 z-30 flex animate-pop items-end justify-center bg-dark/50 sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-h"
        className="flex max-h-[92%] w-full max-w-[520px] flex-col rounded-t-panel bg-surface shadow-modal sm:rounded-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-line py-3 pl-5 pr-3">
          <h2 id="edit-h" className="font-serif text-[22px] font-medium tracking-[-0.01em]">
            Edit recipe
          </h2>
          <IconButton icon="x" label="Cancel editing" variant="plain" size={40} iconSize={18} onClick={onClose} />
        </div>
        <div className="flex flex-col gap-4 overflow-y-auto px-5 py-4">
          <label className="flex flex-col gap-1.5">
            <span className={labelCls}>Title</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} className={`${field} font-serif !text-[17px]`} />
          </label>
          <div className="grid grid-cols-3 gap-2.5">
            <label className="flex min-w-0 flex-col gap-1.5">
              <span className={labelCls}>Yield</span>
              <input
                value={recipeYield}
                onChange={(e) => setRecipeYield(e.target.value)}
                className={field}
              />
            </label>
            <label className="flex min-w-0 flex-col gap-1.5">
              <span className={labelCls}>Prep</span>
              <input value={prep} onChange={(e) => setPrep(e.target.value)} className={field} />
            </label>
            <label className="flex min-w-0 flex-col gap-1.5">
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
              className={`${field} resize-none font-mono !text-[13px] leading-relaxed`}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className={labelCls}>Instructions — one step per line</span>
            <textarea
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              rows={7}
              className={`${field} resize-none !text-[14px] leading-relaxed`}
            />
          </label>
        </div>
        <div className="flex flex-none gap-2.5 border-t border-line px-5 py-3.5">
          <Button variant="secondary" className="h-[52px] flex-1 text-[15px]" onClick={onClose}>
            Cancel
          </Button>
          <Button
            className="h-[52px] flex-[2] text-[15px]"
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
