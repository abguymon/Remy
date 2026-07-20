// Plan step 1 — pick recipes (DESIGN_BRIEF §4.3). Meals stream in independently:
// per-meal skeletons while searching, scoped degraded/error banners with retry,
// per-meal empty state, skip + use-a-URL affordances, and a sticky "Continue
// with N recipes" bar. Selection is held locally and submitted via /plan/select.
import { useEffect, useState } from 'react'
import { ApiError } from '../../lib/api'
import { useRetry, useSubmitSelection } from '../../lib/queries'
import type { Candidate, MealChoice, PlanSnapshot } from '../../lib/types'
import { toast } from '../../stores/toast'
import {
  AuthedImage,
  Button,
  CandidateSkeleton,
  DegradedBanner,
  EmptyState,
  OriginBadge,
  PhotoFallback,
  Spinner,
  StickyBar,
} from '../../components/ui'

type Choice = { choice: 'candidate' | 'url' | 'skip'; candidate_id?: string; url?: string }

function seedChoices(snapshot: PlanSnapshot): Record<string, Choice> {
  const out: Record<string, Choice> = {}
  for (const [mealId, sel] of Object.entries(snapshot.selections)) {
    if (sel.choice === 'candidate' && sel.candidate_id)
      out[mealId] = { choice: 'candidate', candidate_id: sel.candidate_id }
    else if (sel.choice === 'url' && sel.url) out[mealId] = { choice: 'url', url: sel.url }
    else if (sel.choice === 'skip') out[mealId] = { choice: 'skip' }
  }
  return out
}

export default function Step1Pick({
  snapshot,
  live,
}: {
  snapshot: PlanSnapshot
  live: boolean
}) {
  const [choices, setChoices] = useState<Record<string, Choice>>(() => seedChoices(snapshot))
  const submit = useSubmitSelection()
  const retry = useRetry()

  // Keep local choices in sync when candidates first stream in (don't clobber
  // in-progress edits — only add server-confirmed selections we don't have yet).
  useEffect(() => {
    setChoices((prev) => {
      const seeded = seedChoices(snapshot)
      let changed = false
      const next = { ...prev }
      for (const [k, v] of Object.entries(seeded)) {
        if (!(k in next)) {
          next[k] = v
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [snapshot])

  const discovering = snapshot.status === 'discovering'
  const selectedCount = Object.values(choices).filter(
    (c) => c.choice === 'candidate' || c.choice === 'url',
  ).length
  const allDecided = snapshot.meals.every((m) => m.id in choices)
  const canContinue = live && snapshot.status === 'selecting' && allDecided && !submit.isPending

  function pick(mealId: string, candidateId: string) {
    setChoices((prev) => {
      const cur = prev[mealId]
      if (cur?.choice === 'candidate' && cur.candidate_id === candidateId) {
        const { [mealId]: _drop, ...rest } = prev
        return rest
      }
      return { ...prev, [mealId]: { choice: 'candidate', candidate_id: candidateId } }
    })
  }

  function toggleSkip(mealId: string) {
    setChoices((prev) => {
      if (prev[mealId]?.choice === 'skip') {
        const { [mealId]: _drop, ...rest } = prev
        return rest
      }
      return { ...prev, [mealId]: { choice: 'skip' } }
    })
  }

  function setUrl(mealId: string, url: string) {
    setChoices((prev) => ({ ...prev, [mealId]: { choice: 'url', url } }))
  }

  async function onContinue() {
    const payload: MealChoice[] = snapshot.meals.map((m) => ({
      meal_id: m.id,
      ...(choices[m.id] ?? { choice: 'skip' }),
    }))
    try {
      await submit.mutateAsync(payload)
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not save your picks.')
    }
  }

  async function retryMeal(mealId: string) {
    try {
      await retry.mutateAsync({ scope: 'meal', id: mealId })
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Retry failed.')
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="no-scrollbar flex-1 overflow-y-auto pb-8">
        <div className="px-[22px] pb-1.5 pt-1.5">
          <div className="font-serif text-[26px] font-semibold tracking-tight">
            Pick your recipes
          </div>
          <div className="mt-0.5 text-sm text-muted">
            One per meal — or skip. We save the ones you pick to your cookbook.
          </div>
          {discovering && (
            <div className="mt-2 flex items-center gap-2 text-xs text-fainter">
              <Spinner /> Finding recipes for each meal…
            </div>
          )}
        </div>

        {snapshot.meals.map((meal) => (
          <MealSection
            key={meal.id}
            title={meal.verbatim}
            candidates={snapshot.candidates[meal.id]}
            selection={snapshot.selections[meal.id]}
            choice={choices[meal.id]}
            live={live}
            retrying={retry.isPending}
            onPick={(cid) => pick(meal.id, cid)}
            onSkip={() => toggleSkip(meal.id)}
            onUrl={(url) => setUrl(meal.id, url)}
            onRetry={() => retryMeal(meal.id)}
          />
        ))}
      </div>

      <StickyBar>
        <Button
          className="w-full py-3.5 text-[15.5px] font-bold"
          busy={submit.isPending}
          disabled={!canContinue}
          onClick={onContinue}
        >
          {submit.isPending
            ? 'Saving…'
            : discovering
              ? 'Finding recipes…'
              : `Continue with ${selectedCount} ${selectedCount === 1 ? 'recipe' : 'recipes'}`}
        </Button>
      </StickyBar>
    </div>
  )
}

function MealSection({
  title,
  candidates,
  selection,
  choice,
  live,
  retrying,
  onPick,
  onSkip,
  onUrl,
  onRetry,
}: {
  title: string
  candidates: PlanSnapshot['candidates'][string] | undefined
  selection: PlanSnapshot['selections'][string] | undefined
  choice: Choice | undefined
  live: boolean
  retrying: boolean
  onPick: (candidateId: string) => void
  onSkip: () => void
  onUrl: (url: string) => void
  onRetry: () => void
}) {
  const [urlOpen, setUrlOpen] = useState(false)
  const [urlText, setUrlText] = useState('')

  const status = candidates?.status ?? 'pending'
  const loading = status === 'pending' || status === 'searching'
  const skipped = choice?.choice === 'skip'
  const cands = candidates?.candidates ?? []

  return (
    <div className={`mt-4 ${skipped ? 'opacity-55' : ''}`}>
      <div className="flex items-baseline justify-between px-[22px] pb-2.5">
        <div className="font-serif text-[19px] font-semibold tracking-tight">{title}</div>
        {live && (
          <button
            onClick={onSkip}
            className="text-[12.5px] font-semibold text-muted hover:text-ink"
          >
            {skipped ? 'Skipped · undo' : 'Skip'}
          </button>
        )}
      </div>

      {selection?.status === 'error' && (
        <div className="mx-[22px] mb-2.5">
          <DegradedBanner tone="danger" onRetry={live ? onRetry : undefined} retrying={retrying}>
            Couldn't read that recipe{selection.error ? ` — ${selection.error}` : ''}. Try another.
          </DegradedBanner>
        </div>
      )}

      {status === 'degraded' && (
        <div className="mx-[22px] mb-2.5">
          <DegradedBanner onRetry={live ? onRetry : undefined} retrying={retrying}>
            {candidates?.source_errors?.[0] ?? 'Some sources failed — showing what we found.'}
          </DegradedBanner>
        </div>
      )}
      {status === 'error' && (
        <div className="mx-[22px] mb-2.5">
          <DegradedBanner tone="danger" onRetry={live ? onRetry : undefined} retrying={retrying}>
            {candidates?.source_errors?.[0] ?? 'Search failed for this meal.'}
          </DegradedBanner>
        </div>
      )}

      {loading ? (
        <>
          <div className="no-scrollbar flex gap-3 overflow-x-auto px-[22px] pb-3.5">
            <CandidateSkeleton />
            <CandidateSkeleton />
          </div>
          <div className="flex items-center gap-2 px-[22px] text-xs text-fainter">
            <Spinner /> Searching for "{title}"…
          </div>
        </>
      ) : cands.length === 0 ? (
        <div className="px-[22px]">
          <EmptyState
            glyph="🔍"
            message="Nothing good found — try rewording, or paste a recipe URL below."
          />
        </div>
      ) : (
        <div className="no-scrollbar flex snap-x snap-mandatory gap-3 overflow-x-auto px-[22px] pb-3.5 lg:grid lg:grid-cols-5 lg:overflow-visible lg:px-4">
          {cands.map((c) => (
            <CandidateCard
              key={c.id}
              candidate={c}
              selected={choice?.choice === 'candidate' && choice.candidate_id === c.id}
              disabled={!live}
              onPick={() => onPick(c.id)}
            />
          ))}
        </div>
      )}

      <div className="px-[22px]">
        {urlOpen ? (
          <div className="flex gap-2">
            <input
              autoFocus
              value={urlText}
              onChange={(e) => setUrlText(e.target.value)}
              placeholder="https://…"
              className="flex-1 rounded-[9px] border border-line2 bg-surface px-3 py-2 text-[13px] outline-none focus:border-terracotta"
            />
            <Button
              className="px-3 py-2 text-[12.5px]"
              disabled={!urlText.trim()}
              onClick={() => {
                onUrl(urlText.trim())
                setUrlOpen(false)
                toast('Recipe URL set for this meal')
              }}
            >
              Use
            </Button>
          </div>
        ) : (
          live && (
            <button
              onClick={() => setUrlOpen(true)}
              className="rounded-[9px] border border-dashed border-line2 px-3 py-2 text-[12.5px] font-semibold text-muted hover:text-ink"
            >
              ＋ Use a recipe URL instead
            </button>
          )
        )}
        {choice?.choice === 'url' && !urlOpen && (
          <div className="mt-2 truncate text-[12px] text-muted">
            Using: <span className="font-medium text-ink">{choice.url}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function CandidateCard({
  candidate,
  selected,
  disabled,
  onPick,
}: {
  candidate: Candidate
  selected: boolean
  disabled: boolean
  onPick: () => void
}) {
  return (
    <div className="w-[210px] flex-none snap-start lg:w-auto">
      <button
        onClick={onPick}
        disabled={disabled}
        className="block w-full text-left disabled:cursor-default"
      >
        <div
          className={`relative h-[150px] overflow-hidden rounded-card border ${
            selected ? 'border-terracotta ring-2 ring-terracotta' : 'border-line2'
          }`}
        >
          {/* Saved-recipe thumbnails point at the Bearer-protected
              /recipes/{id}/image endpoint — a plain <img> would 401. Load those
              via AuthedImage (token fetch → blob URL). Web candidates carry
              external og:image URLs and load fine with a plain <img>. */}
          {candidate.thumbnail?.startsWith('/recipes/') ? (
            <AuthedImage path={candidate.thumbnail} alt={candidate.title} />
          ) : (
            <PhotoFallback src={candidate.thumbnail} alt={candidate.title} />
          )}
          {selected && (
            <span className="absolute right-2 top-2 flex h-[26px] w-[26px] items-center justify-center rounded-full bg-terracotta text-[15px] font-bold text-white shadow">
              ✓
            </span>
          )}
        </div>
        <div className="mt-2.5 flex items-center gap-1.5">
          <OriginBadge origin={candidate.origin} />
          {candidate.total_time && (
            <span className="text-[11px] text-fainter">{candidate.total_time}</span>
          )}
        </div>
        <div className="mt-1.5 line-clamp-2 font-serif text-[15px] font-semibold leading-tight text-ink">
          {candidate.title}
        </div>
      </button>
      {/* Source affordance: a real link so keyboard/focus works. A sibling of the
          select button (not nested) and stopPropagation-guarded so opening the
          source never toggles selection (DESIGN_BRIEF §4.3). ≥44px tap target. */}
      {candidate.url ? (
        <a
          href={candidate.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="mt-0.5 inline-flex min-h-[44px] max-w-full items-center gap-1 text-[11.5px] text-faint hover:text-terracotta focus-visible:text-terracotta"
        >
          <span className="truncate">{candidate.source_domain ?? 'View recipe'}</span>
          <span aria-hidden className="flex-none">
            ↗
          </span>
          <span className="sr-only">(opens source in a new tab)</span>
        </a>
      ) : (
        candidate.source_domain && (
          <div className="mt-0.5 text-[11.5px] text-faint">{candidate.source_domain}</div>
        )
      )}
    </div>
  )
}
