// Collections (COOKBOOK_PLAN item 3): every tag in the cookbook as a card with
// a 2×2 photo mosaic, Favorites first. Tapping one opens the Cookbook filtered
// to it (?tag= / ?fav=1).
import { useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Icon from '../components/Icon'
import { AuthedImage, DegradedBanner, EmptyState, IconButton, ScreenHeader } from '../components/ui'
import { pluralize } from '../lib/format'
import { useRecipeTags, useRecipes } from '../lib/queries'
import type { RecipeSummary } from '../lib/types'

interface Collection {
  key: string
  name: string
  to: string
  favorite?: boolean
  recipes: RecipeSummary[]
}

export default function Collections() {
  const navigate = useNavigate()
  const recipes = useRecipes('')
  const tags = useRecipeTags()

  const collections = useMemo<Collection[]>(() => {
    const all = recipes.data ?? []
    const withPhotosFirst = (rs: RecipeSummary[]) =>
      [...rs].sort((a, b) => Number(!!b.image_url) - Number(!!a.image_url))
    const out: Collection[] = []
    const favs = all.filter((r) => r.is_favorite)
    if (favs.length) out.push({ key: '__fav', name: 'Favorites', to: '/app/cookbook?fav=1', favorite: true, recipes: withPhotosFirst(favs) })
    for (const t of tags.data ?? []) {
      const key = t.name.toLowerCase()
      out.push({
        key,
        name: t.name,
        to: `/app/cookbook?tag=${encodeURIComponent(t.name)}`,
        recipes: withPhotosFirst(all.filter((r) => r.tags.some((x) => x.toLowerCase() === key))),
      })
    }
    return out
  }, [recipes.data, tags.data])

  const loading = recipes.isLoading || tags.isLoading
  const failed = recipes.isError || tags.isError

  return (
    <div className="pb-10">
      <div className="px-3 pt-3">
        <IconButton icon="back" label="Back to Cookbook" variant="plain" onClick={() => navigate('/app/cookbook')} />
      </div>
      <ScreenHeader
        className="!pt-1"
        title="Collections"
        subtitle="Tags group your recipes. Add tags from any recipe page."
      />

      <div className="px-5 pt-5">
        {failed ? (
          <DegradedBanner
            tone="danger"
            onRetry={() => {
              recipes.refetch()
              tags.refetch()
            }}
          >
            Couldn't load your collections.
          </DegradedBanner>
        ) : loading ? (
          <div className="grid grid-cols-2 gap-x-3.5 gap-y-[18px] lg:grid-cols-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i}>
                <div className="sk aspect-square rounded-card" />
                <div className="sk mt-2.5 h-4 w-2/3 rounded" />
              </div>
            ))}
          </div>
        ) : collections.length === 0 ? (
          <EmptyState
            icon="list"
            message="No collections yet. Tag a recipe (weeknight, Thai, make-ahead…) or tap its heart, and it shows up here."
            action={
              <Link
                to="/app/cookbook"
                className="mt-1 inline-flex h-11 items-center rounded-[14px] border border-line2 bg-surface px-5 text-sm font-semibold text-ink"
              >
                Browse recipes
              </Link>
            }
          />
        ) : (
          <div className="grid grid-cols-2 gap-x-3.5 gap-y-[18px] lg:grid-cols-3 lg:gap-x-5 lg:gap-y-6">
            {collections.map((c) => (
              <Link key={c.key} to={c.to} className="group block min-w-0 text-ink">
                <Mosaic recipes={c.recipes.filter((r) => r.image_url).slice(0, 4)} />
                <div className="mt-2.5 flex items-center gap-1.5 font-serif text-[18px] font-medium leading-tight">
                  {c.favorite && <Icon name="heart" size={15} filled strokeWidth={0} className="text-terracotta" />}
                  <span className="truncate">{c.name}</span>
                </div>
                <div className="mt-0.5 text-[13px] text-muted">{pluralize(c.recipes.length, 'recipe')}</div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// 1 photo fills the square; 2 split it; 3 = one large + two stacked; 4 = 2×2.
const MOSAIC_CELLS: Record<number, string[]> = {
  0: [],
  1: ['col-span-2 row-span-2'],
  2: ['row-span-2', 'row-span-2'],
  3: ['row-span-2', '', ''],
  4: ['', '', '', ''],
}

function Mosaic({ recipes }: { recipes: RecipeSummary[] }) {
  const cells = MOSAIC_CELLS[recipes.length]
  return (
    <div className="grid aspect-square grid-cols-2 grid-rows-2 gap-0.5 overflow-hidden rounded-card bg-tile">
      {recipes.length === 0 ? (
        <div className="col-span-2 row-span-2 flex items-center justify-center text-faint">
          <Icon name="utensils" size={28} strokeWidth={1.6} />
        </div>
      ) : (
        recipes.map((r, i) => (
          <div key={r.id} className={`overflow-hidden bg-tile ${cells[i]}`}>
            <AuthedImage
              path={r.image_url}
              alt=""
              label="recipe photo"
              className="transition-transform duration-300 group-hover:scale-[1.04]"
            />
          </div>
        ))
      )}
    </div>
  )
}
