// Cookbook (DESIGN_BRIEF §4.7, visual language v2 §8) — browse register.
// Serif title + round add button, search, then client-derived shelves
// ("Cook again", "Recently added", "On the table in 30 minutes") above the full
// photo grid. Filter chips (Favorites + the most-used tags, via ?fav=1 / ?tag=)
// narrow the grid; shelves hide while searching or filtering. "Add a recipe"
// opens a sheet that imports from a URL or photos/PDF with parse progress.
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { pluralize, shortDate } from '../lib/format'
import { useCreateRecipeFromUpload, useCreateRecipeFromUrl, useRecipeTags, useRecipes } from '../lib/queries'
import type { RecipeDetail, RecipeSummary } from '../lib/types'
import Icon from '../components/Icon'
import {
  AuthedImage,
  Button,
  Chip,
  DegradedBanner,
  EmptyState,
  IconButton,
  ScreenHeader,
  SectionHeading,
  SegmentedControl,
  Spinner,
} from '../components/ui'

const MAX_UPLOAD_FILES = 6
const MAX_UPLOAD_BYTES = 15_000_000
const SHELF_MIN_RECIPES = 6 // below this the grid alone reads better than shelves
const QUICK_MINUTES = 30
const COOK_AGAIN_DAYS = 21
const FILTER_TAGS = 8 // most-used tags shown as chips; the rest live in Collections

// "cooking.nytimes.com" → "nytimes", "hot-thai-kitchen.com" → "hot-thai-kitchen".
function sourceName(url: string | null): string {
  if (!url) return ''
  try {
    const parts = new URL(url).hostname.replace(/^www\./, '').split('.')
    return parts.length >= 2 ? parts[parts.length - 2] : parts[0]
  } catch {
    return ''
  }
}

// Minutes from free-text ("1 hr 15 min", "45 min", "1 hour") or ISO-8601
// ("PT1H15M") durations. null when it can't be read.
function minutesOf(text: string | null): number | null {
  if (!text) return null
  const iso = /^P(?:T)?(?:(\d+)H)?(?:(\d+)M)?/i.exec(text.trim())
  if (iso && (iso[1] || iso[2])) return Number(iso[1] ?? 0) * 60 + Number(iso[2] ?? 0)
  const h = /(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b/i.exec(text)
  const m = /(\d+)\s*(?:m|min|mins|minute|minutes)\b/i.exec(text)
  if (!h && !m) return null
  return Math.round(Number(h?.[1] ?? 0) * 60 + Number(m?.[1] ?? 0))
}

function metaLine(r: RecipeSummary): string {
  return [r.total_time, sourceName(r.source_url)].filter(Boolean).join(' · ')
}

export default function Cookbook() {
  const [search, setSearch] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const all = useRecipes('') // unfiltered list → count + shelves (shared cache with the grid)
  const recipes = useRecipes(search)
  const tags = useRecipeTags()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tagFilter = params.get('tag')
  const favFilter = params.get('fav') === '1'
  const filtering = !!tagFilter || favFilter
  const setFilter = (next: { tag?: string; fav?: boolean } | null) =>
    setParams(next?.tag ? { tag: next.tag } : next?.fav ? { fav: '1' } : {}, { replace: true })

  const items = useMemo(() => {
    const list = recipes.data ?? []
    if (favFilter) return list.filter((r) => r.is_favorite)
    if (tagFilter) {
      const key = tagFilter.toLowerCase()
      return list.filter((r) => r.tags.some((t) => t.toLowerCase() === key))
    }
    return list
  }, [recipes.data, favFilter, tagFilter])
  const allItems = useMemo(() => all.data ?? [], [all.data])
  const favCount = allItems.filter((r) => r.is_favorite).length
  const isSearching = search.trim().length > 0
  const chipTags = (tags.data ?? []).slice(0, FILTER_TAGS).map((t) => t.name)
  if (tagFilter && !chipTags.some((t) => t.toLowerCase() === tagFilter.toLowerCase())) chipTags.unshift(tagFilter)
  const open = (id: string) => navigate(`/app/cookbook/${id}`)

  const shelves = useMemo(() => {
    const now = Date.now()
    const recent = [...allItems]
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, 8)
    const quick = allItems
      .map((r) => ({ r, min: minutesOf(r.total_time) }))
      .filter((x): x is { r: RecipeSummary; min: number } => x.min != null && x.min <= QUICK_MINUTES)
      .sort((a, b) => a.min - b.min)
      .slice(0, 3)
      .map((x) => x.r)
    // Favorites and past hits you haven't made lately: favorites first, then
    // the most-made, then whatever's gone longest.
    const stale = (r: RecipeSummary) =>
      !r.last_cooked_at || now - new Date(r.last_cooked_at).getTime() > COOK_AGAIN_DAYS * 86_400_000
    const again = allItems
      .filter((r) => (r.is_favorite || r.cooked_count > 0) && stale(r))
      .sort(
        (a, b) =>
          Number(b.is_favorite) - Number(a.is_favorite) ||
          b.cooked_count - a.cooked_count ||
          (a.last_cooked_at ?? '').localeCompare(b.last_cooked_at ?? ''),
      )
      .slice(0, 6)
    return { recent, quick, again }
  }, [allItems])

  const showShelves = !isSearching && !filtering && allItems.length >= SHELF_MIN_RECIPES
  const gridTitle = isSearching ? 'Search results' : favFilter ? 'Favorites' : tagFilter ?? 'All recipes'

  return (
    <div className="pb-10">
      <ScreenHeader
        title="Cookbook"
        subtitle={
          all.data
            ? [pluralize(all.data.length, 'recipe'), favCount ? pluralize(favCount, 'favorite') : '']
                .filter(Boolean)
                .join(' · ')
            : undefined
        }
        action={
          <IconButton icon="plus" label="Add a recipe" variant="accent" onClick={() => setAddOpen(true)} />
        }
      />

      <div className="px-5 pt-[18px]">
        <label className="flex h-[46px] items-center gap-2.5 rounded-[14px] border border-line bg-surface px-3.5 focus-within:border-terracotta">
          <Icon name="search" size={18} strokeWidth={2} className="flex-none text-faint" />
          <input
            type="search"
            aria-label="Search recipes"
            placeholder="Search recipes"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="min-w-0 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-faint [&::-webkit-search-cancel-button]:hidden"
          />
          {isSearching && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setSearch('')}
              className="-mr-2 flex h-9 w-9 flex-none items-center justify-center rounded-full text-muted hover:bg-chip"
            >
              <Icon name="x" size={16} strokeWidth={2.2} />
            </button>
          )}
        </label>
      </div>

      {allItems.length > 0 && (
        <nav aria-label="Filter recipes" className="no-scrollbar flex gap-2 overflow-x-auto px-5 pb-0.5 pt-3.5">
          <Chip active={!filtering} onClick={() => setFilter(null)}>
            All
          </Chip>
          {favCount > 0 && (
            <Chip icon="heart" active={favFilter} onClick={() => setFilter(favFilter ? null : { fav: true })}>
              Favorites
            </Chip>
          )}
          {chipTags.map((t) => {
            const on = tagFilter?.toLowerCase() === t.toLowerCase()
            return (
              <Chip key={t} active={on} onClick={() => setFilter(on ? null : { tag: t })}>
                {t}
              </Chip>
            )
          })}
          <Link
            to="/app/cookbook/collections"
            className="inline-flex h-9 flex-none items-center gap-1.5 rounded-full px-3 text-[13.5px] font-semibold text-terracotta-deep hover:bg-chip"
          >
            Collections
            <Icon name="chevronRight" size={14} strokeWidth={2.4} />
          </Link>
        </nav>
      )}

      {recipes.isError ? (
        <div className="px-5 pt-6">
          <DegradedBanner tone="danger" onRetry={() => recipes.refetch()} retrying={recipes.isFetching}>
            Couldn't load your recipes.
          </DegradedBanner>
        </div>
      ) : recipes.isLoading ? (
        <section className="px-5 pt-[30px]">
          <div className="sk h-6 w-36 rounded" />
          <CardGrid>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i}>
                <div className="sk aspect-[4/3] rounded-[14px]" />
                <div className="sk mt-2.5 h-3.5 w-[85%] rounded" />
                <div className="sk mt-1.5 h-3 w-[55%] rounded" />
              </div>
            ))}
          </CardGrid>
        </section>
      ) : items.length === 0 ? (
        <div className="px-5 pt-6">
          {isSearching ? (
            <EmptyState icon="search" message={`No recipes match "${search.trim()}"${filtering ? ' in this filter' : ''}.`} />
          ) : filtering ? (
            <EmptyState
              icon={favFilter ? 'heart' : 'list'}
              message={favFilter ? 'No favorites yet — tap the heart on a recipe.' : `Nothing tagged "${tagFilter}" yet.`}
              action={
                <Button variant="secondary" className="mt-1 h-11 px-5 text-sm" onClick={() => setFilter(null)}>
                  Show all recipes
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon="book"
              message="Recipes you pick get saved here automatically — or add one from a URL, photos, or a PDF."
              action={
                <Button className="mt-1 h-11 px-5 text-sm" onClick={() => setAddOpen(true)}>
                  <Icon name="plus" size={16} strokeWidth={2.4} />
                  Add a recipe
                </Button>
              }
            />
          )}
        </div>
      ) : (
        <>
          {showShelves && shelves.again.length > 0 && (
            <Shelf title="Cook again" sub="Favorites and past hits you haven't made lately">
              {shelves.again.map((r) => (
                <button
                  key={r.id}
                  onClick={() => open(r.id)}
                  className="w-[270px] flex-none self-start text-left lg:w-[300px]"
                >
                  <div className="relative h-[176px] overflow-hidden rounded-card bg-tile lg:h-[196px]">
                    <AuthedImage path={r.image_url} alt="" label="recipe photo" />
                    <span className="absolute bottom-2.5 left-2.5 inline-flex items-center gap-1 rounded-[12px] bg-surface/85 px-2.5 py-[5px] text-[12px] font-semibold text-ink backdrop-blur">
                      {r.is_favorite && <Icon name="heart" size={12} filled strokeWidth={0} className="text-terracotta" />}
                      {r.cooked_count > 0 ? `Made ${r.cooked_count}×` : 'Favorite'}
                    </span>
                  </div>
                  <div className="mt-2.5 line-clamp-2 font-serif text-[18px] font-medium leading-[1.2] text-ink">
                    {r.title}
                  </div>
                  <div className="mt-[3px] text-[13px] text-muted">
                    {[r.last_cooked_at ? `Last made ${shortDate(r.last_cooked_at)}` : 'Not made yet', r.total_time]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                </button>
              ))}
            </Shelf>
          )}

          {showShelves && (
            <Shelf title="Recently added">
              {shelves.recent.map((r) => (
                <button
                  key={r.id}
                  onClick={() => open(r.id)}
                  className="w-[148px] flex-none self-start text-left lg:w-[168px]"
                >
                  <div className="h-[148px] overflow-hidden rounded-[14px] bg-tile lg:h-[168px]">
                    <AuthedImage path={r.image_url} alt="" label="recipe photo" />
                  </div>
                  <div className="mt-2 line-clamp-2 font-serif text-[15.5px] font-medium leading-[1.22] text-ink">
                    {r.title}
                  </div>
                  {r.total_time && (
                    <div className="mt-[3px] text-[12.5px] text-muted">{r.total_time}</div>
                  )}
                </button>
              ))}
            </Shelf>
          )}

          {showShelves && shelves.quick.length > 0 && (
            <section aria-labelledby="sh-quick" className="px-5 pt-[26px]">
              <SectionHeading id="sh-quick">On the table in 30 minutes</SectionHeading>
              <div className="mt-3 flex flex-col gap-2.5">
                {shelves.quick.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => open(r.id)}
                    className="flex items-center gap-3.5 rounded-card border border-line bg-surface p-2.5 text-left hover:border-line2"
                  >
                    <div className="h-[72px] w-[72px] flex-none overflow-hidden rounded-[12px] bg-tile">
                      <AuthedImage path={r.image_url} alt="" label="recipe photo" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="line-clamp-2 font-serif text-[16.5px] font-medium leading-[1.2] text-ink">
                        {r.title}
                      </div>
                      <div className="mt-1 flex items-center gap-1.5 text-[13px] text-muted">
                        <Icon name="clock" size={14} strokeWidth={2} className="flex-none" />
                        <span className="truncate">{metaLine(r)}</span>
                      </div>
                    </div>
                    <Icon name="chevronRight" size={18} strokeWidth={2} className="mr-1 flex-none text-faint" />
                  </button>
                ))}
              </div>
            </section>
          )}

          <section aria-labelledby="sh-all" className={`px-5 ${showShelves ? 'pt-[30px]' : 'pt-6'}`}>
            <SectionHeading
              id="sh-all"
              sub={pluralize(items.length, isSearching ? 'match' : 'recipe', isSearching ? 'matches' : undefined)}
              action={
                filtering ? (
                  <button type="button" onClick={() => setFilter(null)} className="min-h-[36px] px-1">
                    Clear filter
                  </button>
                ) : undefined
              }
            >
              {gridTitle}
            </SectionHeading>
            <CardGrid>
              {items.map((r) => (
                <RecipeCard key={r.id} recipe={r} onOpen={() => open(r.id)} />
              ))}
            </CardGrid>
          </section>
        </>
      )}

      {addOpen && (
        <AddRecipeSheet
          onClose={() => setAddOpen(false)}
          onView={(id) => {
            setAddOpen(false)
            open(id)
          }}
        />
      )}
    </div>
  )
}

function Shelf({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  const id = `sh-${title.toLowerCase().replace(/[^a-z]+/g, '-')}`
  return (
    <section aria-labelledby={id} className="pt-[26px]">
      <SectionHeading id={id} sub={sub} className="px-5">
        {title}
      </SectionHeading>
      <div className="no-scrollbar flex gap-3 overflow-x-auto px-5 pb-1 pt-3">{children}</div>
    </section>
  )
}

function CardGrid({ children }: { children: ReactNode }) {
  return (
    <div className="mt-3.5 grid grid-cols-2 gap-x-3.5 gap-y-[18px] lg:grid-cols-3 lg:gap-x-5 lg:gap-y-6">
      {children}
    </div>
  )
}

function RecipeCard({ recipe, onOpen }: { recipe: RecipeSummary; onOpen: () => void }) {
  const meta = metaLine(recipe)
  return (
    <button onClick={onOpen} className="group min-w-0 cursor-pointer self-start text-left">
      <div className="relative aspect-[4/3] overflow-hidden rounded-[14px] bg-tile">
        <AuthedImage
          path={recipe.image_url}
          alt=""
          label="recipe photo"
          className="transition-transform duration-300 group-hover:scale-[1.03]"
        />
        {recipe.is_favorite && (
          <span className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full bg-surface/85 text-terracotta backdrop-blur">
            <Icon name="heart" size={14} filled strokeWidth={0} />
            <span className="sr-only">Favorite</span>
          </span>
        )}
      </div>
      <div className="mt-2 line-clamp-2 font-serif text-[15.5px] font-medium leading-[1.22] text-ink">
        {recipe.title}
      </div>
      {meta && <div className="mt-[3px] truncate text-[12.5px] text-muted">{meta}</div>}
    </button>
  )
}

// --- Add recipe sheet (URL or photos/PDF) ----------------------------------

type AddMode = 'url' | 'upload'

const fieldCls =
  'w-full rounded-[14px] border border-line2 bg-cream px-3.5 text-[15px] text-ink outline-none placeholder:text-faint focus:border-terracotta disabled:opacity-60'

function AddRecipeSheet({
  onClose,
  onView,
}: {
  onClose: () => void
  onView: (id: string) => void
}) {
  const [mode, setMode] = useState<AddMode>('url')
  const [added, setAdded] = useState<RecipeDetail | null>(null)
  const busy = useRef(false)

  return (
    <div
      className="fixed inset-0 z-30 flex animate-pop items-end justify-center bg-dark/50 sm:items-center sm:p-6"
      onClick={() => {
        if (!busy.current) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Add a recipe"
        className="max-h-[92%] w-full max-w-[440px] overflow-y-auto rounded-t-panel bg-surface px-5 pb-6 pt-2.5 shadow-modal sm:rounded-panel sm:pt-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line2 sm:hidden" aria-hidden />
        {added ? (
          <AddedView added={added} onClose={onClose} onView={onView} />
        ) : (
          <>
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-serif text-[24px] font-medium leading-tight tracking-[-0.01em]">
                Add a recipe
              </h2>
              <IconButton
                icon="x"
                label="Close"
                variant="plain"
                size={36}
                iconSize={18}
                className="-mr-1.5 -mt-1"
                onClick={() => {
                  if (!busy.current) onClose()
                }}
              />
            </div>
            <SegmentedControl
              label="Import from"
              className="mt-3.5"
              value={mode}
              onChange={setMode}
              options={[
                {
                  value: 'url',
                  label: (
                    <>
                      <Icon name="link" size={15} strokeWidth={2} /> Paste URL
                    </>
                  ),
                },
                {
                  value: 'upload',
                  label: (
                    <>
                      <Icon name="camera" size={15} strokeWidth={2} /> Photos or PDF
                    </>
                  ),
                },
              ]}
            />
            {mode === 'url' ? (
              <UrlForm onAdded={setAdded} onCancel={onClose} onBusy={(b) => (busy.current = b)} />
            ) : (
              <UploadForm onAdded={setAdded} onCancel={onClose} onBusy={(b) => (busy.current = b)} />
            )}
          </>
        )}
      </div>
    </div>
  )
}

function AddedView({
  added,
  onClose,
  onView,
}: {
  added: RecipeDetail
  onClose: () => void
  onView: (id: string) => void
}) {
  return (
    <>
      <div className="flex items-center gap-2 text-[11.5px] font-bold uppercase tracking-[.07em] text-success">
        <Icon name="check" size={14} strokeWidth={3} />
        Added to your cookbook
      </div>
      <div className="mt-3.5 overflow-hidden rounded-card border border-line bg-cream">
        <div className="aspect-[16/9] w-full overflow-hidden bg-tile">
          <AuthedImage path={added.image_url} alt="" label="recipe photo" />
        </div>
        <div className="px-4 py-3">
          <div className="line-clamp-2 font-serif text-[19px] font-medium leading-[1.2] text-ink">
            {added.title}
          </div>
          <div className="mt-1 text-[13px] text-muted">
            {pluralize(added.ingredients.length, 'ingredient')} ·{' '}
            {pluralize(added.instructions.length, 'step')}
            {added.total_time ? ` · ${added.total_time}` : ''}
          </div>
        </div>
      </div>
      <div className="mt-4 flex gap-2.5">
        <Button variant="secondary" className="h-[50px] flex-1 text-[15px]" onClick={onClose}>
          Done
        </Button>
        <Button className="h-[50px] flex-1 text-[15px]" onClick={() => onView(added.id)}>
          View recipe
        </Button>
      </div>
    </>
  )
}

function ErrorBox({ message, reasons }: { message: string; reasons?: string[] }) {
  return (
    <div className="mt-3.5 flex gap-2.5 rounded-[14px] border border-danger-border bg-danger-bg px-3.5 py-3 text-[13px] text-danger">
      <Icon name="alert" size={17} className="mt-px flex-none" />
      <div className="min-w-0">
        {message}
        {reasons && reasons.length > 0 && (
          <ul className="mt-1.5 list-disc pl-4 text-[12.5px]">
            {reasons.map((r) => (
              <li key={r}>{reasonLabel(r)}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function reasonLabel(reason: string): string {
  const map: Record<string, string> = {
    llm_no_recipe: "We couldn't find a readable recipe in what you sent.",
    missing_ingredients: 'No ingredients could be read.',
    missing_instructions: 'No steps could be read.',
    missing_title: 'No recipe title could be read.',
    unsupported_type: 'One of the files is an unsupported type (use JPEG, PNG, WEBP, or PDF).',
    file_too_large: 'A file is larger than 15 MB.',
    too_many_files: `You can upload at most ${MAX_UPLOAD_FILES} files.`,
    undecodable_image: "One of the images couldn't be read.",
    empty_file: 'One of the files was empty.',
    empty_pdf: 'The PDF had no readable pages.',
  }
  return map[reason] ?? reason.replace(/_/g, ' ')
}

function Progress({ children }: { children: ReactNode }) {
  return (
    <div
      className="mt-3.5 flex items-center gap-2.5 rounded-[14px] bg-chip px-3.5 py-3 text-[13px] text-muted"
      role="status"
    >
      <Spinner />
      <span>{children}</span>
    </div>
  )
}

function SheetActions({
  busy,
  canSubmit,
  onCancel,
  onSubmit,
}: {
  busy: boolean
  canSubmit: boolean
  onCancel: () => void
  onSubmit: () => void
}) {
  return (
    <div className="mt-5 flex gap-2.5">
      <Button variant="secondary" className="h-[50px] flex-1 text-[15px]" onClick={onCancel} disabled={busy}>
        Cancel
      </Button>
      <Button
        className="h-[50px] flex-1 text-[15px]"
        onClick={onSubmit}
        busy={busy}
        disabled={busy || !canSubmit}
      >
        {busy ? 'Reading…' : 'Add recipe'}
      </Button>
    </div>
  )
}

function UrlForm({
  onAdded,
  onCancel,
  onBusy,
}: {
  onAdded: (r: RecipeDetail) => void
  onCancel: () => void
  onBusy: (b: boolean) => void
}) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [reasons, setReasons] = useState<string[]>([])
  const create = useCreateRecipeFromUrl()

  async function submit() {
    if (!url.trim() || create.isPending) return
    setError(null)
    setReasons([])
    onBusy(true)
    try {
      onAdded(await create.mutateAsync(url.trim()))
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.code === 'recipe_parse_failed' ? `Couldn't read that page — ${err.message}` : err.message,
        )
        setReasons(err.reasons)
      } else {
        setError('Something went wrong. Try another URL.')
      }
    } finally {
      onBusy(false)
    }
  }

  return (
    <>
      <p className="mt-4 text-[13.5px] leading-relaxed text-muted">
        Paste a recipe URL — we'll read the ingredients and steps.
      </p>
      {error && <ErrorBox message={error} reasons={reasons} />}
      <input
        autoFocus
        type="url"
        inputMode="url"
        aria-label="Recipe URL"
        placeholder="https://…"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && submit()}
        disabled={create.isPending}
        className={`mt-3 h-[50px] ${fieldCls}`}
      />
      {create.isPending && <Progress>Reading the page… this can take a few seconds.</Progress>}
      <SheetActions
        busy={create.isPending}
        canSubmit={!!url.trim()}
        onCancel={onCancel}
        onSubmit={submit}
      />
    </>
  )
}

interface PickedFile {
  file: File
  previewUrl: string | null // object URL for images; null for PDFs
}

function UploadForm({
  onAdded,
  onCancel,
  onBusy,
}: {
  onAdded: (r: RecipeDetail) => void
  onCancel: () => void
  onBusy: (b: boolean) => void
}) {
  const [picked, setPicked] = useState<PickedFile[]>([])
  const [hint, setHint] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [reasons, setReasons] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const create = useCreateRecipeFromUpload()

  // Revoke object URLs on unmount so we don't leak blobs.
  useEffect(() => {
    return () => {
      for (const p of picked) if (p.previewUrl) URL.revokeObjectURL(p.previewUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function addFiles(list: FileList | null) {
    if (!list) return
    setError(null)
    setReasons([])
    const incoming: PickedFile[] = []
    for (const file of Array.from(list)) {
      if (file.size > MAX_UPLOAD_BYTES) {
        setError(`"${file.name}" is larger than 15 MB.`)
        continue
      }
      incoming.push({
        file,
        previewUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
      })
    }
    setPicked((prev) => {
      const combined = [...prev, ...incoming]
      if (combined.length > MAX_UPLOAD_FILES) {
        setError(`You can upload at most ${MAX_UPLOAD_FILES} files.`)
        // Revoke the ones we're dropping.
        for (const p of combined.slice(MAX_UPLOAD_FILES)) if (p.previewUrl) URL.revokeObjectURL(p.previewUrl)
        return combined.slice(0, MAX_UPLOAD_FILES)
      }
      return combined
    })
    if (inputRef.current) inputRef.current.value = '' // allow re-picking the same file
  }

  function removeAt(index: number) {
    setPicked((prev) => {
      const target = prev[index]
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl)
      return prev.filter((_, i) => i !== index)
    })
  }

  function move(index: number, delta: number) {
    setPicked((prev) => {
      const next = [...prev]
      const to = index + delta
      if (to < 0 || to >= next.length) return prev
      ;[next[index], next[to]] = [next[to], next[index]]
      return next
    })
  }

  async function submit() {
    if (picked.length === 0 || create.isPending) return
    setError(null)
    setReasons([])
    onBusy(true)
    try {
      onAdded(await create.mutateAsync({ files: picked.map((p) => p.file), hint }))
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.code === 'recipe_parse_failed'
            ? "We couldn't read a recipe from those files."
            : err.message,
        )
        setReasons(err.reasons)
      } else {
        setError('Something went wrong. Try again.')
      }
    } finally {
      onBusy(false)
    }
  }

  const rowBtn =
    'flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-chip disabled:opacity-30 disabled:hover:bg-transparent'

  return (
    <>
      <p className="mt-4 text-[13.5px] leading-relaxed text-muted">
        Upload photos of a recipe (front and back, or a two-page spread) or a PDF. Order matters —
        arrange pages top to bottom. We'll transcribe exactly what's visible; check it against your
        photo before saving.
      </p>
      {error && <ErrorBox message={error} reasons={reasons} />}

      <input
        ref={inputRef}
        type="file"
        accept="image/*,application/pdf"
        multiple
        capture="environment"
        className="hidden"
        onChange={(e) => addFiles(e.target.files)}
      />

      {picked.length > 0 && (
        <ul className="mt-3.5 flex flex-col gap-2">
          {picked.map((p, i) => (
            <li
              key={`${p.file.name}-${i}`}
              className="flex items-center gap-3 rounded-[14px] border border-line bg-cream p-2"
            >
              <div className="flex h-12 w-12 flex-none items-center justify-center overflow-hidden rounded-[10px] bg-chip text-muted">
                {p.previewUrl ? (
                  <img src={p.previewUrl} alt={p.file.name} className="h-full w-full object-cover" />
                ) : (
                  <Icon name="file" size={22} strokeWidth={1.8} />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13.5px] font-medium text-ink">{p.file.name}</div>
                <div className="text-[12px] text-faint">Page {i + 1}</div>
              </div>
              <div className="flex flex-none items-center">
                <button
                  type="button"
                  aria-label="Move up"
                  onClick={() => move(i, -1)}
                  disabled={i === 0}
                  className={rowBtn}
                >
                  <Icon name="chevronUp" size={17} strokeWidth={2.2} />
                </button>
                <button
                  type="button"
                  aria-label="Move down"
                  onClick={() => move(i, 1)}
                  disabled={i === picked.length - 1}
                  className={rowBtn}
                >
                  <Icon name="chevronDown" size={17} strokeWidth={2.2} />
                </button>
                <button
                  type="button"
                  aria-label="Remove"
                  onClick={() => removeAt(i)}
                  className="flex h-9 w-9 items-center justify-center rounded-full text-danger hover:bg-danger-bg"
                >
                  <Icon name="x" size={16} strokeWidth={2.2} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={create.isPending || picked.length >= MAX_UPLOAD_FILES}
        className="mt-3.5 flex h-[50px] w-full items-center justify-center gap-2 rounded-[14px] border border-dashed border-line2 bg-transparent text-[14px] font-semibold text-terracotta-deep hover:bg-cream disabled:opacity-40"
      >
        <Icon name={picked.length === 0 ? 'upload' : 'plus'} size={17} strokeWidth={2.2} />
        {picked.length === 0 ? 'Choose photos or a PDF' : 'Add another page'}
      </button>

      <input
        aria-label="Hint (optional)"
        placeholder="Optional hint, e.g. “the recipe on the left”"
        value={hint}
        onChange={(e) => setHint(e.target.value)}
        disabled={create.isPending}
        className={`mt-3 h-[50px] ${fieldCls}`}
      />

      {create.isPending && (
        <Progress>
          Reading your {picked.length > 1 ? 'pages' : 'photo'}… this can take a few seconds.
        </Progress>
      )}

      <SheetActions
        busy={create.isPending}
        canSubmit={picked.length > 0}
        onCancel={onCancel}
        onSubmit={submit}
      />
    </>
  )
}
