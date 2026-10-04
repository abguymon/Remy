// "Cook this week": queue saved recipes, then order groceries for all of them
// in one plan that starts at list review (POST /plan/from-recipes).
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useCreatePlanFromRecipes, useUpdateRecipe } from '../lib/queries'
import type { RecipeSummary } from '../lib/types'
import { toast } from '../stores/toast'
import Icon from './Icon'

export function useThisWeekToggle(recipe: Pick<RecipeSummary, 'id' | 'this_week'>) {
  const update = useUpdateRecipe(recipe.id)
  return () =>
    update
      .mutateAsync({ this_week: !recipe.this_week })
      .then(() => toast(recipe.this_week ? 'Removed from this week' : 'Added to this week'))
      .catch(() => toast("Couldn't update this week's list — try again"))
}

export function useOrderGroceries() {
  const create = useCreatePlanFromRecipes()
  const navigate = useNavigate()
  return {
    pending: create.isPending,
    order: async (recipeIds: string[]) => {
      try {
        await create.mutateAsync(recipeIds)
        navigate('/app')
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          toast('You already have a plan in progress — finish it or start over first')
          navigate('/app')
        } else {
          toast("Couldn't build the shopping list — try again")
        }
      }
    },
  }
}

/** Round add/remove button that sits on a recipe photo. */
export function ThisWeekBadge({
  recipe,
  className = '',
}: {
  recipe: Pick<RecipeSummary, 'id' | 'this_week' | 'title'>
  className?: string
}) {
  const toggle = useThisWeekToggle(recipe)
  const on = recipe.this_week
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        toggle()
      }}
      aria-pressed={on}
      aria-label={on ? `Remove ${recipe.title} from this week` : `Add ${recipe.title} to this week`}
      className={`flex h-9 w-9 items-center justify-center rounded-full shadow-card backdrop-blur ${
        on ? 'bg-terracotta text-onaccent' : 'bg-surface/85 text-ink hover:bg-surface'
      } ${className}`}
    >
      <Icon name={on ? 'check' : 'plus'} size={17} strokeWidth={2.6} />
    </button>
  )
}
