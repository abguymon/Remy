// Cookbook (DESIGN_BRIEF §4.7) — browse register. Search + 2-col photo card
// grid; "Add recipe" opens a paste-URL sheet with parse progress and a parsed
// preview. Empty first-run and no-results states included.
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { cookedLabel } from '../lib/format'
import { useCreateRecipeFromUpload, useCreateRecipeFromUrl, useRecipes } from '../lib/queries'
import type { RecipeDetail, RecipeSummary } from '../lib/types'
import { AuthedImage, Button, EmptyState, Spinner } from '../components/ui'

const MAX_UPLOAD_FILES = 6
const MAX_UPLOAD_BYTES = 15_000_000

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
            message="Recipes you pick get saved here automatically — or add one from a URL, photos, or a PDF."
            action={
              <Button className="mt-1 px-4 py-2.5 text-sm" onClick={() => setAddOpen(true)}>
                Add a recipe
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
          ＋ Add a recipe
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

// --- Add recipe sheet (URL or photos/PDF) ----------------------------------

type AddMode = 'url' | 'upload'

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
      className="absolute inset-0 z-30 flex animate-pop items-end justify-center sm:items-center"
      style={{ background: 'rgba(40,30,20,.4)' }}
      onClick={() => {
        if (!busy.current) onClose()
      }}
    >
      <div
        className="max-h-[92%] w-full max-w-[420px] overflow-y-auto rounded-t-[22px] bg-surface p-[22px] shadow-modal sm:rounded-[18px]"
        onClick={(e) => e.stopPropagation()}
      >
        {added ? (
          <AddedView added={added} onClose={onClose} onView={onView} />
        ) : (
          <>
            <div className="font-serif text-xl font-semibold">Add a recipe</div>
            <ModeTabs mode={mode} onChange={setMode} />
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

function ModeTabs({ mode, onChange }: { mode: AddMode; onChange: (m: AddMode) => void }) {
  const tab = (m: AddMode, label: string) => (
    <button
      key={m}
      onClick={() => onChange(m)}
      className={`flex-1 rounded-[9px] py-2 text-[13px] font-semibold transition-colors ${
        mode === m ? 'bg-surface text-ink shadow-sm' : 'text-muted'
      }`}
    >
      {label}
    </button>
  )
  return (
    <div className="mt-3 flex gap-1 rounded-[11px] border border-line2 bg-cream p-1">
      {tab('url', 'Paste URL')}
      {tab('upload', 'Photos or PDF')}
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
  )
}

function ErrorBox({ message, reasons }: { message: string; reasons?: string[] }) {
  return (
    <div className="mt-3 rounded-[10px] border border-danger-border bg-danger-bg px-3 py-2.5 text-[13px] text-danger">
      {message}
      {reasons && reasons.length > 0 && (
        <ul className="mt-1.5 list-disc pl-4 text-[12px]">
          {reasons.map((r) => (
            <li key={r}>{reasonLabel(r)}</li>
          ))}
        </ul>
      )}
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
      <div className="mt-3 text-[13px] text-muted">
        Paste a recipe URL — we'll read the ingredients and steps.
      </div>
      {error && <ErrorBox message={error} reasons={reasons} />}
      <input
        autoFocus
        placeholder="https://…"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && submit()}
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
          onClick={onCancel}
          disabled={create.isPending}
        >
          Cancel
        </Button>
        <Button
          className="flex-1 py-3 text-sm"
          onClick={submit}
          busy={create.isPending}
          disabled={create.isPending || !url.trim()}
        >
          {create.isPending ? 'Reading…' : 'Add recipe'}
        </Button>
      </div>
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

  return (
    <>
      <div className="mt-3 text-[13px] text-muted">
        Upload photos of a recipe (front and back, or a two-page spread) or a PDF. Order matters —
        arrange pages top to bottom. We'll transcribe exactly what's visible; check it against your
        photo before saving.
      </div>
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
        <ul className="mt-3 flex flex-col gap-2">
          {picked.map((p, i) => (
            <li
              key={`${p.file.name}-${i}`}
              className="flex items-center gap-2.5 rounded-[11px] border border-line2 bg-cream p-2"
            >
              <div className="flex h-[46px] w-[46px] flex-none items-center justify-center overflow-hidden rounded-[8px] border border-line2 bg-surface">
                {p.previewUrl ? (
                  <img src={p.previewUrl} alt={p.file.name} className="h-full w-full object-cover" />
                ) : (
                  <span className="text-[20px]">📄</span>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12.5px] font-medium text-ink">{p.file.name}</div>
                <div className="text-[11px] text-faint">Page {i + 1}</div>
              </div>
              <div className="flex flex-none items-center gap-1">
                <button
                  aria-label="Move up"
                  onClick={() => move(i, -1)}
                  disabled={i === 0}
                  className="rounded-[7px] px-2 py-1 text-[13px] text-muted disabled:opacity-30"
                >
                  ↑
                </button>
                <button
                  aria-label="Move down"
                  onClick={() => move(i, 1)}
                  disabled={i === picked.length - 1}
                  className="rounded-[7px] px-2 py-1 text-[13px] text-muted disabled:opacity-30"
                >
                  ↓
                </button>
                <button
                  aria-label="Remove"
                  onClick={() => removeAt(i)}
                  className="rounded-[7px] px-2 py-1 text-[13px] text-danger"
                >
                  ✕
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <button
        onClick={() => inputRef.current?.click()}
        disabled={create.isPending || picked.length >= MAX_UPLOAD_FILES}
        className="mt-3 w-full rounded-[11px] border border-dashed border-[#D8CDB9] bg-transparent py-3 text-[13px] font-semibold text-terracotta disabled:opacity-40"
      >
        {picked.length === 0 ? '＋ Choose photos or a PDF' : '＋ Add another page'}
      </button>

      <input
        placeholder="Optional hint — e.g. the pasta recipe on the left page"
        value={hint}
        onChange={(e) => setHint(e.target.value)}
        disabled={create.isPending}
        className="mt-3 w-full rounded-[11px] border border-line2 bg-cream px-3.5 py-3 text-sm outline-none focus:border-terracotta disabled:opacity-60"
      />

      {create.isPending && (
        <div className="mt-3 flex items-center gap-2 text-[12.5px] text-muted">
          <Spinner /> Reading your {picked.length > 1 ? 'pages' : 'photo'}… this can take a few
          seconds.
        </div>
      )}

      <div className="mt-4 flex gap-2.5">
        <Button
          variant="secondary"
          className="flex-1 py-3 text-sm"
          onClick={onCancel}
          disabled={create.isPending}
        >
          Cancel
        </Button>
        <Button
          className="flex-1 py-3 text-sm"
          onClick={submit}
          busy={create.isPending}
          disabled={create.isPending || picked.length === 0}
        >
          {create.isPending ? 'Reading…' : 'Add recipe'}
        </Button>
      </div>
    </>
  )
}
