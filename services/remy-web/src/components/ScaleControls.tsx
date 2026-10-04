// Servings scaler + US/metric toggle for a recipe's ingredient list. Uses a
// servings stepper when the yield has a number ("6 servings"), otherwise
// multiplier chips (½× 1× 2× 3×).
import { detectSystem, parseServings } from '../lib/ingredients'
import type { UnitSystem } from '../lib/ingredients'
import type { RecipeDetail } from '../lib/types'
import { useCookPref, useCookPrefs } from '../stores/cookPrefs'
import Icon from './Icon'
import { Chip, SegmentedControl } from './ui'

const MULTIPLIERS = [0.5, 1, 2, 3]

export function useScale(recipe: RecipeDetail | undefined) {
  const pref = useCookPref(recipe?.id)
  const base = parseServings(recipe?.recipe_yield)
  const native = detectSystem(recipe?.ingredients.map((i) => i.raw) ?? [])
  return {
    factor: pref.factor,
    system: (pref.system ?? native) as UnitSystem,
    baseServings: base,
    servings: base ? Math.max(1, Math.round(base * pref.factor)) : null,
  }
}

function multLabel(m: number) {
  return m === 0.5 ? '½×' : `${m}×`
}

export default function ScaleControls({ recipe, className = '' }: { recipe: RecipeDetail; className?: string }) {
  const setPref = useCookPrefs((s) => s.set)
  const { factor, system, baseServings, servings } = useScale(recipe)
  const setServings = (n: number) => baseServings && setPref(recipe.id, { factor: n / baseServings })

  return (
    <div className={`flex flex-col gap-2.5 ${className}`}>
      {baseServings && servings ? (
        <div className="flex items-center justify-between rounded-card border border-line bg-surface py-2 pl-4 pr-2">
          <div>
            <div className="text-[15px] font-semibold text-ink" aria-live="polite">
              {servings} {servings === 1 ? 'serving' : 'servings'}
            </div>
            <div className="text-[12.5px] text-muted">
              {factor === 1 ? 'As written' : `Scaled from ${baseServings}`}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="Fewer servings"
              disabled={servings <= 1}
              onClick={() => setServings(servings - 1)}
              className="flex h-11 w-11 items-center justify-center rounded-[12px] border border-line bg-cream text-ink disabled:opacity-40"
            >
              <Icon name="minus" size={18} strokeWidth={2.4} />
            </button>
            <button
              type="button"
              aria-label="More servings"
              disabled={servings >= baseServings * 8}
              onClick={() => setServings(servings + 1)}
              className="flex h-11 w-11 items-center justify-center rounded-[12px] border border-line bg-cream text-ink disabled:opacity-40"
            >
              <Icon name="plus" size={18} strokeWidth={2.4} />
            </button>
          </div>
        </div>
      ) : (
        <div role="group" aria-label="Scale recipe" className="flex flex-wrap gap-2">
          {MULTIPLIERS.map((m) => (
            <Chip key={m} active={factor === m} onClick={() => setPref(recipe.id, { factor: m })}>
              {multLabel(m)}
            </Chip>
          ))}
        </div>
      )}
      <SegmentedControl
        label="Units"
        value={system}
        onChange={(v) => setPref(recipe.id, { system: v })}
        options={[
          { value: 'us', label: 'US' },
          { value: 'metric', label: 'Metric' },
        ]}
      />
    </div>
  )
}
