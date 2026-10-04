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
  DegradedBanner,
  EmptyState,
  OriginBadge,
  PhotoFallback,
  ScreenHeader,
  Spinner,
  StickyBar,
} from '../../components/ui'
import Icon from '../../components/Icon'

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
        <ScreenHeader
          className="!pt-4"
          title="Pick your recipes"
          subtitle="One per meal — or skip. We save the ones you pick to your cookbook."
        />
        {discovering && (
          <div className="mt-2.5 flex items-center gap-2 px-5 text-[12.5px] text-muted">
            <Spinner /> Finding recipes for each meal…
          </div>
        )}

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

      {/* Pinned to the bottom of the app's scrolling <main> so the action
          (and the live total) stays in reach while the list scrolls. */}
      <div className="sticky bottom-0 z-10">
        <StickyBar>
          <Button
            className="h-[54px] w-full text-[16px] font-bold"
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
    <section className="mt-8">
      <div className="flex items-end justify-between gap-3 px-5 pb-3">
        <h2
          className={`min-w-0 font-serif text-[22px] font-medium leading-tight tracking-[-0.01em] ${
            skipped ? 'text-faint line-through decoration-1' : ''
          }`}
        >
          {title}
        </h2>
        {live && (
          <button
            type="button"
            onClick={onSkip}
            aria-pressed={skipped}
            className="-my-1 flex min-h-[44px] flex-none items-center"
          >
            <span
              className={`inline-flex h-8 items-center gap-1 rounded-full border px-3 text-[12.5px] font-semibold ${
                skipped
                  ? 'border-ink bg-ink text-cream'
                  : 'border-line bg-surface text-muted hover:text-ink'
              }`}
            >
              {skipped ? (
                <>
                  <Icon name="refresh" size={13} strokeWidth={2.4} />
                  Skipped · undo
                </>
              ) : (
                'Skip'
              )}
            </span>
          </button>
        )}
      </div>

      <div className={skipped ? 'opacity-50' : ''}>
        {selection?.status === 'error' && (
          <div className="mx-5 mb-3">
            <DegradedBanner tone="danger" onRetry={live ? onRetry : undefined} retrying={retrying}>
              Couldn't read that recipe{selection.error ? ` — ${selection.error}` : ''}. Try another.
            </DegradedBanner>
          </div>
        )}

        {status === 'degraded' && (
          <div className="mx-5 mb-3">
            <DegradedBanner onRetry={live ? onRetry : undefined} retrying={retrying}>
              {candidates?.source_errors?.[0] ?? 'Some sources failed — showing what we found.'}
            </DegradedBanner>
          </div>
        )}
        {status === 'error' && (
          <div className="mx-5 mb-3">
            <DegradedBanner tone="danger" onRetry={live ? onRetry : undefined} retrying={retrying}>
              {candidates?.source_errors?.[0] ?? 'Search failed for this meal.'}
            </DegradedBanner>
          </div>
        )}

        {loading ? (
          <>
            <div className="no-scrollbar flex gap-3.5 overflow-x-auto px-5 pb-3 pt-1 lg:grid lg:grid-cols-3 lg:overflow-visible">
              <CardSkeleton />
              <CardSkeleton />
              <CardSkeleton />
            </div>
            <div className="flex items-center gap-2 px-5 text-[12.5px] text-muted">
              <Spinner /> Searching for "{title}"…
            </div>
          </>
        ) : cands.length === 0 ? (
          <div className="px-5">
            <EmptyState
              icon="search"
              message="Nothing good found — try rewording, or paste a recipe URL below."
            />
          </div>
        ) : (
          <div className="no-scrollbar flex snap-x snap-mandatory scroll-px-5 gap-3.5 overflow-x-auto px-5 pb-1 pt-1 lg:grid lg:grid-cols-3 lg:gap-x-4 lg:gap-y-5 lg:overflow-visible">
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

        <div className="px-5">
          {urlOpen ? (
            <div className="flex gap-2">
              <input
                autoFocus
                value={urlText}
                onChange={(e) => setUrlText(e.target.value)}
                placeholder="https://…"
                aria-label="Recipe URL"
                className="h-11 min-w-0 flex-1 rounded-[12px] border border-line2 bg-surface px-3.5 text-[14px] text-ink outline-none placeholder:text-faint focus:border-terracotta"
              />
              <Button
                className="h-11 px-4 text-[13.5px]"
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
                type="button"
                onClick={() => setUrlOpen(true)}
                className="inline-flex h-11 items-center gap-1.5 rounded-full border border-dashed border-line2 px-4 text-[13px] font-semibold text-muted hover:border-terracotta hover:text-terracotta-deep"
              >
                <Icon name="link" size={15} />
                Use a recipe URL instead
              </button>
            )
          )}
          {choice?.choice === 'url' && !urlOpen && (
            <div className="mt-2.5 flex min-w-0 items-center gap-2 rounded-[12px] border border-terracotta/40 bg-terracotta-soft px-3 py-2 text-[12.5px] text-terracotta-deep">
              <Icon name="link" size={14} className="flex-none" />
              <span className="flex-none">Using:</span>
              <span className="truncate font-semibold">{choice.url}</span>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

// Skeleton sized to the v2 candidate card (photo 4:3 + badge + title lines).
function CardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`w-[236px] flex-none lg:w-auto ${className}`} aria-hidden>
      <div className="sk aspect-[4/3] rounded-card" />
      <div className="sk mt-3 h-4 w-14 rounded-full" />
      <div className="sk mt-2 h-3.5 w-[90%] rounded" />
      <div className="sk mt-1.5 h-3.5 w-[60%] rounded" />
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
    <div className="w-[236px] flex-none snap-start lg:w-auto">
      <button
        type="button"
        onClick={onPick}
        disabled={disabled}
        aria-pressed={selected}
        className="group block w-full text-left disabled:cursor-default"
      >
        <div
          className={`relative aspect-[4/3] overflow-hidden rounded-card transition-shadow ${
            selected
              ? 'ring-[2.5px] ring-terracotta ring-offset-2 ring-offset-cream'
              : 'ring-1 ring-line'
          }`}
        >
          {/* Recipe and cached search thumbnails are served by
              Bearer-protected API endpoints. AuthedImage fetches them with the
              token and renders a CSP-safe blob URL. */}
          {candidate.thumbnail?.startsWith('/') ? (
            <AuthedImage path={candidate.thumbnail} alt={candidate.title} />
          ) : (
            <PhotoFallback src={candidate.thumbnail} alt={candidate.title} />
          )}
          {selected ? (
            <span className="absolute right-2.5 top-2.5 flex h-8 w-8 items-center justify-center rounded-full bg-terracotta text-onaccent shadow-terracotta">
              <Icon name="check" size={17} strokeWidth={3} />
            </span>
          ) : (
            !disabled && (
              <span className="absolute right-2.5 top-2.5 h-8 w-8 rounded-full border-2 border-surface/90 bg-dark/20 backdrop-blur-sm" />
            )
          )}
        </div>
        <div className="mt-3 flex items-center gap-2">
          <OriginBadge origin={candidate.origin} />
          {candidate.total_time && (
            <span className="inline-flex items-center gap-1 text-[12px] text-faint">
              <Icon name="clock" size={13} />
              {candidate.total_time}
            </span>
          )}
        </div>
        <div
          className={`mt-1.5 line-clamp-2 font-serif text-[17px] font-medium leading-[1.2] tracking-[-0.005em] ${
            selected ? 'text-terracotta-deep' : 'text-ink'
          }`}
        >
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
          className="inline-flex min-h-[44px] max-w-full items-center gap-1 text-[12px] text-faint hover:text-terracotta-deep focus-visible:text-terracotta-deep"
        >
          <span className="truncate">{candidate.source_domain ?? 'View recipe'}</span>
          <Icon name="external" size={12} className="flex-none" aria-hidden />
          <span className="sr-only">(opens source in a new tab)</span>
        </a>
      ) : (
        candidate.source_domain && (
          <div className="flex min-h-[44px] items-center text-[12px] text-faint">
            {candidate.source_domain}
          </div>
        )
      )}
    </div>
  )
}
