// Settings (DESIGN_BRIEF §4.10) — edit register. Kroger account (connect/return
// toast/disconnect), store picker (ZIP search → select), fulfillment control,
// pantry chip editor, favorite sites list, appearance, API tokens with
// show-once modal, admin invitations/users, password change.
// v2 visual language (§8): serif headings, grouped surface cards, icon-led rows.
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError } from '../lib/api'
import {
  useAdminUsers,
  useApiTokens,
  useChangePassword,
  useCreateAdminUser,
  useCreateInvitation,
  useCreateApiToken,
  useDisconnectKroger,
  useKrogerAuth,
  useInvitations,
  useKrogerStatus,
  useMe,
  useResetUserPassword,
  useRevokeApiToken,
  useRevokeInvitation,
  useSelectStore,
  useSetUserActive,
  useSettings,
  useStoreSearch,
  useUpdateSettings,
} from '../lib/queries'
import type {
  AdminUserInfo,
  InvitationCreated,
  ApiTokenCreated,
  FulfillmentMethod,
  SettingsResponse,
  StoreLocation,
} from '../lib/types'
import { shortDate } from '../lib/format'
import { toast } from '../stores/toast'
import { useTheme } from '../stores/theme'
import type { ThemePref } from '../stores/theme'
import {
  Button,
  ConfirmDialog,
  IconButton,
  ScreenHeader,
  SectionHeading,
  SectionLabel,
  SegmentedControl,
  Spinner,
  StatusPill,
} from '../components/ui'
import Icon from '../components/Icon'
import type { IconName } from '../components/Icon'
import UsualsSettings from './settings/UsualsSettings'

const KROGER_ERRORS: Record<string, string> = {
  exchange_failed: "Couldn't complete the Kroger connection. Try again.",
  state_expired: 'The connection link expired. Try again.',
  invalid_state: 'The connection link was invalid. Try again.',
  missing_code_or_state: 'Kroger returned an incomplete response. Try again.',
  access_denied: 'You declined the Kroger connection.',
}

// Shared edit-register styles.
const inputClass =
  'h-11 w-full min-w-0 rounded-[12px] border border-line2 bg-cream px-3.5 text-[14px] text-ink outline-none placeholder:text-faint focus:border-terracotta'
const smallBtn = 'h-11 flex-none px-4 text-[13.5px]'
const pillAction =
  'inline-flex h-9 flex-none items-center gap-1.5 rounded-full border border-line2 bg-surface px-3.5 text-[13px] font-semibold hover:bg-cream disabled:cursor-not-allowed disabled:opacity-40'

export default function Settings() {
  const settings = useSettings()
  const me = useMe()
  const [params, setParams] = useSearchParams()

  // Handle the OAuth return (?kroger=connected|error&reason=…): toast + clean URL.
  useEffect(() => {
    const kroger = params.get('kroger')
    if (!kroger) return
    if (kroger === 'connected') {
      toast('Kroger connected')
    } else {
      const reason = params.get('reason') ?? ''
      toast(KROGER_ERRORS[reason] ?? 'Kroger connection failed. Try again.')
    }
    const next = new URLSearchParams(params)
    next.delete('kroger')
    next.delete('reason')
    setParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const subtitle = me.data ? `Signed in as ${me.data.username}` : undefined

  if (settings.isLoading || !settings.data) {
    return (
      <div className="pb-12">
        <ScreenHeader title="Settings" subtitle={subtitle} />
        <div className="mt-8 flex items-center gap-2 px-5 text-sm text-muted">
          <Spinner /> Loading…
        </div>
      </div>
    )
  }

  return (
    <div className="pb-12">
      <ScreenHeader title="Settings" subtitle={subtitle} />
      <KrogerSection />
      <StoreSection settings={settings.data} />
      <UsualsSettings settings={settings.data} />
      <PantrySection settings={settings.data} />
      <SitesSection settings={settings.data} />
      <AppearanceSection />
      <TokensSection />
      {me.data?.is_admin && <InvitationsSection />}
      {me.data?.is_admin && <UsersSection currentUserId={me.data.id} />}
      <AccountSection />
    </div>
  )
}

// --- Layout primitives -------------------------------------------------------

function Section({
  title,
  sub,
  children,
}: {
  title: string
  sub?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="mt-9 px-5">
      <SectionHeading sub={sub} className="mb-3">
        {title}
      </SectionHeading>
      {children}
    </section>
  )
}

function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`divide-y divide-divider overflow-hidden rounded-card border border-line bg-surface shadow-card ${className}`}
    >
      {children}
    </div>
  )
}

// Round icon tile that leads a settings row.
function RowIcon({ icon, tone = 'neutral' }: { icon: IconName; tone?: 'neutral' | 'accent' }) {
  return (
    <span
      className={`flex h-9 w-9 flex-none items-center justify-center rounded-full ${
        tone === 'accent' ? 'bg-terracotta-soft text-terracotta-deep' : 'bg-chip text-muted'
      }`}
    >
      <Icon name={icon} size={18} />
    </span>
  )
}

// "＋ Create …" footer row inside a card.
function AddRow({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex min-h-[52px] w-full items-center gap-3 px-4 text-left text-[14px] font-semibold text-terracotta-deep hover:bg-cream"
    >
      <span className="flex h-9 w-9 flex-none items-center justify-center rounded-full border border-dashed border-line2">
        <Icon name="plus" size={16} strokeWidth={2.4} />
      </span>
      {label}
    </button>
  )
}

// Inline "name + Create/Cancel" form row used by tokens, users, invitations.
function InlineCreate({
  placeholder,
  value,
  onChange,
  onSubmit,
  onCancel,
  pending,
}: {
  placeholder: string
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  onCancel: () => void
  pending: boolean
}) {
  return (
    <div className="flex items-center gap-2 px-4 py-3">
      <input
        autoFocus
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
        className={`${inputClass} flex-1`}
      />
      <Button className={smallBtn} onClick={onSubmit} busy={pending} busyLabel="…">
        Create
      </Button>
      <Button variant="ghost" className="h-11 flex-none px-2 text-[13.5px]" onClick={onCancel}>
        Cancel
      </Button>
    </div>
  )
}

// --- Kroger account --------------------------------------------------------

function KrogerSection() {
  const status = useKrogerStatus()
  const auth = useKrogerAuth()
  const disconnect = useDisconnectKroger()
  const [confirm, setConfirm] = useState(false)
  const connected = status.data?.connected ?? false

  async function connect() {
    try {
      const { auth_url } = await auth.mutateAsync()
      window.location.href = auth_url
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not start Kroger connect.')
    }
  }

  return (
    <Section title="Kroger account" sub="Remy fills your Kroger cart for you.">
      <Card>
        <div className="flex items-center gap-3 px-4 py-3.5">
          <RowIcon icon="link" tone={connected ? 'accent' : 'neutral'} />
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-semibold">Kroger</div>
            <div className="mt-1">
              {status.isLoading ? (
                <StatusPill tone="neutral">Checking…</StatusPill>
              ) : connected ? (
                <StatusPill tone="success">Connected</StatusPill>
              ) : (
                <StatusPill tone="danger">Not connected</StatusPill>
              )}
            </div>
          </div>
          {connected ? (
            <Button variant="danger" className="h-10 flex-none px-4 text-[13.5px]" onClick={() => setConfirm(true)}>
              Disconnect
            </Button>
          ) : (
            <Button
              className="h-10 flex-none px-4 text-[13.5px]"
              onClick={connect}
              busy={auth.isPending}
              busyLabel="Connecting…"
            >
              Connect
            </Button>
          )}
        </div>
      </Card>

      <ConfirmDialog
        open={confirm}
        title="Disconnect Kroger?"
        body="Remy won't be able to add items to your cart until you reconnect. Your saved recipes and store are kept."
        confirmLabel="Disconnect"
        destructive
        onCancel={() => setConfirm(false)}
        onConfirm={async () => {
          await disconnect.mutateAsync()
          setConfirm(false)
          toast('Kroger disconnected')
        }}
      />
    </Section>
  )
}

// --- Store -----------------------------------------------------------------

function StoreSection({ settings }: { settings: SettingsResponse }) {
  const [changing, setChanging] = useState(!settings.store_location_id)
  const updateSettings = useUpdateSettings()

  return (
    <Section title="Store">
      <Card>
        {settings.store_location_id && !changing ? (
          <div className="flex items-center gap-3 px-4 py-3.5">
            <RowIcon icon="store" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[15px] font-semibold">
                {settings.store_name ?? 'Selected store'}
              </div>
              {settings.zip_code && (
                <div className="mt-0.5 text-[12.5px] text-faint">ZIP {settings.zip_code}</div>
              )}
            </div>
            <button
              onClick={() => setChanging(true)}
              className="-mr-2 min-h-[44px] flex-none px-2 text-[13.5px] font-semibold text-terracotta-deep"
            >
              Change
            </button>
          </div>
        ) : (
          <div className="px-4 py-3.5">
            <StoreSearch
              initialZip={settings.zip_code ?? ''}
              hasStore={!!settings.store_location_id}
              onCancel={() => setChanging(false)}
              onSelected={() => setChanging(false)}
            />
          </div>
        )}

        {/* Fulfillment segmented control */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2.5 px-4 py-3.5">
          <RowIcon icon="bag" />
          <div className="min-w-[96px] flex-1 text-[14.5px] font-semibold">Fulfillment</div>
          <SegmentedControl<FulfillmentMethod>
            label="Fulfillment method"
            className="w-full sm:w-[220px]"
            value={settings.fulfillment_method}
            onChange={(m) => updateSettings.mutate({ fulfillment_method: m })}
            options={[
              { value: 'PICKUP', label: 'Pickup' },
              { value: 'DELIVERY', label: 'Delivery' },
            ]}
          />
        </div>
      </Card>
    </Section>
  )
}

function StoreSearch({
  initialZip,
  hasStore,
  onCancel,
  onSelected,
}: {
  initialZip: string
  hasStore: boolean
  onCancel: () => void
  onSelected: () => void
}) {
  const [zip, setZip] = useState(initialZip)
  const search = useStoreSearch()
  const select = useSelectStore()
  const [error, setError] = useState<string | null>(null)

  async function run() {
    if (zip.trim().length < 3) return
    setError(null)
    try {
      await search.mutateAsync(zip.trim())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Store search failed.')
    }
  }

  const results = search.data ?? []

  return (
    <div>
      <SectionLabel className="mb-2">Find a store near you</SectionLabel>
      <div className="flex gap-2">
        <div className="relative min-w-0 flex-1">
          <Icon
            name="search"
            size={17}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-faint"
          />
          <input
            placeholder="ZIP code"
            aria-label="ZIP code"
            value={zip}
            inputMode="numeric"
            onChange={(e) => setZip(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && run()}
            className={`${inputClass} pl-10`}
          />
        </div>
        <Button className={smallBtn} onClick={run} busy={search.isPending} busyLabel="Searching…">
          Search
        </Button>
        {hasStore && (
          <Button variant="ghost" className="h-11 flex-none px-2 text-[13.5px]" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>

      {error && (
        <div className="mt-2.5 flex items-center gap-1.5 text-[12.5px] text-danger">
          <Icon name="alert" size={14} className="flex-none" />
          {error}
        </div>
      )}

      {search.isSuccess && results.length === 0 && (
        <div className="mt-3 rounded-[12px] border border-dashed border-line2 px-3.5 py-3 text-center text-[13px] text-muted">
          No stores found near that ZIP.
        </div>
      )}

      {results.length > 0 && (
        <div className="mt-3 divide-y divide-divider overflow-hidden rounded-[14px] border border-line2">
          {results.map((s: StoreLocation) => (
            <button
              key={s.id}
              disabled={select.isPending}
              onClick={async () => {
                await select.mutateAsync(s.id)
                toast(`Store set to ${s.name ?? 'selected store'}`)
                onSelected()
              }}
              className="flex min-h-[56px] w-full items-center justify-between gap-3 px-3.5 py-3 text-left hover:bg-cream disabled:opacity-60"
            >
              <Icon name="store" size={18} className="flex-none text-faint" />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[14px] font-semibold text-ink">
                  {s.name ?? s.chain ?? 'Kroger store'}
                </div>
                <div className="truncate text-[12px] text-faint">
                  {s.full_address ?? s.address ?? ''}
                </div>
              </div>
              {s.distance != null && (
                <span className="tab-fig flex-none text-[12px] text-faint">
                  {s.distance.toFixed(1)} mi
                </span>
              )}
              <Icon name="chevronRight" size={16} className="flex-none text-faint" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// --- Pantry staples --------------------------------------------------------

function PantrySection({ settings }: { settings: SettingsResponse }) {
  const updateSettings = useUpdateSettings()
  const [items, setItems] = useState<string[]>(settings.pantry_items)
  const [draft, setDraft] = useState('')
  // Snapshot the list as first loaded this session → used for "reset to defaults".
  // (No backend defaults endpoint exists; for a fresh user this snapshot IS the
  // seeded defaults. See T8 status notes.)
  const defaultsRef = useRef<string[]>(settings.pantry_items)

  function persist(next: string[]) {
    setItems(next)
    updateSettings.mutate({ pantry_items: next })
  }

  function add() {
    const value = draft.trim()
    if (!value) return
    if (!items.some((i) => i.toLowerCase() === value.toLowerCase())) {
      persist([...items, value])
    }
    setDraft('')
  }

  return (
    <Section title="Pantry staples" sub="Things you always have — Remy leaves them off your list.">
      <Card>
        <div className="flex flex-wrap gap-2 p-4">
          {items.map((item) => (
            <span
              key={item}
              className="inline-flex h-9 items-center gap-1 rounded-full border border-line bg-cream pl-3.5 pr-1 text-[13.5px] font-medium text-ink"
            >
              {item}
              <button
                aria-label={`Remove ${item}`}
                onClick={() => persist(items.filter((i) => i !== item))}
                className="flex h-7 w-7 items-center justify-center rounded-full text-faint hover:bg-chip hover:text-ink"
              >
                <Icon name="x" size={13} strokeWidth={2.4} />
              </button>
            </span>
          ))}
          <label className="inline-flex h-9 items-center gap-1.5 rounded-full border border-dashed border-line2 pl-3 pr-3.5 text-faint focus-within:border-terracotta">
            <Icon name="plus" size={14} strokeWidth={2.4} className="flex-none" />
            <input
              placeholder="Add staple…"
              aria-label="Add staple"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') add()
              }}
              onBlur={add}
              className="w-[104px] bg-transparent text-[13.5px] text-ink outline-none placeholder:text-faint"
            />
          </label>
        </div>
        <button
          onClick={() => persist(defaultsRef.current)}
          className="flex min-h-[48px] w-full items-center gap-2 px-4 text-left text-[13.5px] font-semibold text-terracotta-deep hover:bg-cream"
        >
          <Icon name="refresh" size={16} />
          Reset to defaults
        </button>
      </Card>
    </Section>
  )
}

// --- Favorite recipe sites -------------------------------------------------

function SitesSection({ settings }: { settings: SettingsResponse }) {
  const updateSettings = useUpdateSettings()
  const [sites, setSites] = useState<string[]>(settings.favorite_sites)
  const [draft, setDraft] = useState('')

  function persist(next: string[]) {
    setSites(next)
    updateSettings.mutate({ favorite_sites: next })
  }

  function add() {
    const value = draft.trim().replace(/^https?:\/\//, '').replace(/\/$/, '')
    if (!value) return
    if (!sites.some((s) => s.toLowerCase() === value.toLowerCase())) {
      persist([...sites, value])
    }
    setDraft('')
  }

  function move(index: number, dir: -1 | 1) {
    const target = index + dir
    if (target < 0 || target >= sites.length) return
    const next = [...sites]
    ;[next[index], next[target]] = [next[target], next[index]]
    persist(next)
  }

  const arrowBtn =
    'flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-chip hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent'

  return (
    <Section title="Favorite recipe sites" sub="Searched first, in this order.">
      <Card>
        {sites.map((domain, i) => (
          <div key={domain} className="flex items-center gap-2 py-1.5 pl-4 pr-2">
            <span className="tab-fig flex h-7 w-7 flex-none items-center justify-center rounded-full bg-chip text-[12px] font-bold text-muted">
              {i + 1}
            </span>
            <span className="ml-1 min-w-0 flex-1 truncate text-[14.5px] text-ink">{domain}</span>
            <button
              aria-label="Move up"
              disabled={i === 0}
              onClick={() => move(i, -1)}
              className={arrowBtn}
            >
              {/* No chevronUp in the icon set — rotate chevronDown. */}
              <Icon name="chevronUp" size={17} />
            </button>
            <button
              aria-label="Move down"
              disabled={i === sites.length - 1}
              onClick={() => move(i, 1)}
              className={arrowBtn}
            >
              <Icon name="chevronDown" size={17} />
            </button>
            <IconButton
              icon="x"
              variant="plain"
              size={36}
              iconSize={16}
              label={`Remove ${domain}`}
              className="text-faint"
              onClick={() => persist(sites.filter((s) => s !== domain))}
            />
          </div>
        ))}
        <div className="flex items-center gap-2 px-4 py-3">
          <input
            placeholder="e.g. seriouseats.com"
            aria-label="Add a site"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && add()}
            className={`${inputClass} flex-1`}
          />
          <Button variant="secondary" className={smallBtn} onClick={add}>
            <Icon name="plus" size={15} strokeWidth={2.4} />
            Add
          </Button>
        </div>
      </Card>
    </Section>
  )
}

// --- Appearance (per device) -------------------------------------------------

function AppearanceSection() {
  const { pref, setPref } = useTheme()
  const icon = (name: IconName) => <Icon name={name} size={16} />
  return (
    <Section title="Appearance">
      <Card>
        <div className="px-4 py-3.5">
          <SegmentedControl<ThemePref>
            label="Theme"
            value={pref}
            onChange={setPref}
            options={[
              { value: 'system', label: <>{icon('monitor')}System</> },
              { value: 'light', label: <>{icon('sun')}Light</> },
              { value: 'dark', label: <>{icon('moon')}Dark</> },
            ]}
          />
          <div className="mt-2.5 text-[12.5px] text-faint">
            Saved on this device only. System follows your device's light/dark setting.
          </div>
        </div>
      </Card>
    </Section>
  )
}

// --- API tokens ------------------------------------------------------------

function TokensSection() {
  const tokens = useApiTokens()
  const create = useCreateApiToken()
  const revoke = useRevokeApiToken()
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<ApiTokenCreated | null>(null)
  const [revokeId, setRevokeId] = useState<string | null>(null)

  const active = (tokens.data ?? []).filter((t) => !t.revoked_at)

  return (
    <Section title="API tokens" sub="Connect an MCP client such as Claude Desktop.">
      <Card>
        {active.map((t) => (
          <div key={t.id} className="flex items-center gap-3 px-4 py-3">
            <RowIcon icon="key" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[14.5px] font-semibold">{t.name}</div>
              <div className="text-[12px] text-faint">
                Created {shortDate(t.created_at)} ·{' '}
                {t.last_used_at ? `Last used ${shortDate(t.last_used_at)}` : 'Never used'}
              </div>
            </div>
            <button
              onClick={() => setRevokeId(t.id)}
              className="-mr-2 min-h-[44px] flex-none px-2 text-[13px] font-semibold text-danger"
            >
              Revoke
            </button>
          </div>
        ))}

        {active.length === 0 && !creating && (
          <div className="px-4 py-3.5 text-[13.5px] text-muted">
            No tokens yet. Create one to connect an MCP client.
          </div>
        )}

        {creating ? (
          <InlineCreate
            placeholder="Token name (e.g. Claude Desktop)"
            value={name}
            onChange={setName}
            onSubmit={submitCreate}
            pending={create.isPending}
            onCancel={() => {
              setCreating(false)
              setName('')
            }}
          />
        ) : (
          <AddRow label="Create token" onClick={() => setCreating(true)} />
        )}
      </Card>

      {created && (
        <SecretModal
          title="Token created"
          blurb={
            <>
              Copy it now — <b className="text-ink">you won't be able to see it again.</b>
            </>
          }
          secret={created.token}
          copyLabel="token"
          onClose={() => setCreated(null)}
        />
      )}

      <ConfirmDialog
        open={!!revokeId}
        title="Revoke this token?"
        body="Any client using it will immediately lose access. This can't be undone."
        confirmLabel="Revoke"
        destructive
        onCancel={() => setRevokeId(null)}
        onConfirm={async () => {
          if (revokeId) await revoke.mutateAsync(revokeId)
          setRevokeId(null)
          toast('Token revoked')
        }}
      />
    </Section>
  )

  async function submitCreate() {
    if (!name.trim()) return
    try {
      const token = await create.mutateAsync(name.trim())
      setCreated(token)
      setCreating(false)
      setName('')
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not create token.')
    }
  }
}

// --- Account (password change) ---------------------------------------------

function AccountSection() {
  const changePassword = useChangePassword()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)

  const tooShort = next.length > 0 && next.length < 12
  const mismatch = confirm.length > 0 && next !== confirm
  const canSubmit =
    current.length > 0 && next.length >= 12 && confirm.length > 0 && next === confirm

  async function submit() {
    setError(null)
    if (next !== confirm) {
      setError('New passwords do not match.')
      return
    }
    if (next.length < 12) {
      setError('New password must be at least 12 characters.')
      return
    }
    try {
      await changePassword.mutateAsync({ current_password: current, new_password: next })
      setCurrent('')
      setNext('')
      setConfirm('')
      toast('Password updated')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update password.')
    }
  }

  return (
    <Section title="Account">
      <Card>
        <div className="p-4">
          <div className="flex items-center gap-3">
            <RowIcon icon="user" />
            <div className="text-[15px] font-semibold">Change password</div>
          </div>
          <div className="mt-3.5 flex flex-col gap-2.5">
            <input
              type="password"
              autoComplete="current-password"
              placeholder="Current password"
              aria-label="Current password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              className={inputClass}
            />
            <input
              type="password"
              autoComplete="new-password"
              placeholder="New password (min 12 characters)"
              aria-label="New password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className={inputClass}
            />
            <input
              type="password"
              autoComplete="new-password"
              placeholder="Confirm new password"
              aria-label="Confirm new password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && canSubmit && submit()}
              className={inputClass}
            />
          </div>

          {tooShort && (
            <div className="mt-2 text-[12.5px] text-muted">
              New password must be at least 12 characters.
            </div>
          )}
          {mismatch && <div className="mt-2 text-[12.5px] text-danger">Passwords don't match.</div>}
          {error && <div className="mt-2 text-[12.5px] text-danger">{error}</div>}

          <Button
            className="mt-3.5 h-12 w-full text-[14.5px]"
            onClick={submit}
            disabled={!canSubmit}
            busy={changePassword.isPending}
            busyLabel="Updating…"
          >
            Update password
          </Button>
        </div>
      </Card>
    </Section>
  )
}

// --- Users (admin only) ----------------------------------------------------

function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'danger' }) {
  return (
    <span
      className={`flex-none rounded-full px-2 py-[2px] text-[11px] font-semibold ${
        tone === 'danger' ? 'bg-danger-bg text-danger' : 'bg-chip text-muted'
      }`}
    >
      {children}
    </span>
  )
}

type Reveal = { title: string; blurb: ReactNode; secret: string }

function UsersSection({ currentUserId }: { currentUserId: string }) {
  const users = useAdminUsers(true)
  const create = useCreateAdminUser()
  const reset = useResetUserPassword()
  const setActive = useSetUserActive()
  const [name, setName] = useState('')
  const [adding, setAdding] = useState(false)
  const [reveal, setReveal] = useState<Reveal | null>(null)
  const [confirm, setConfirm] = useState<{ user: AdminUserInfo; activate: boolean } | null>(null)

  const rows = users.data ?? []

  async function submitCreate() {
    const username = name.trim()
    if (!username) return
    try {
      const created = await create.mutateAsync(username)
      setReveal({
        title: 'User created',
        blurb: (
          <>
            Temporary password for <b className="text-ink">{created.username}</b>. Share it
            securely — they should change it after signing in, and{' '}
            <b className="text-ink">you won't see it again.</b>
          </>
        ),
        secret: created.temp_password,
      })
      setAdding(false)
      setName('')
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not create user.')
    }
  }

  async function resetPassword(u: AdminUserInfo) {
    try {
      const res = await reset.mutateAsync(u.id)
      setReveal({
        title: 'Password reset',
        blurb: (
          <>
            New temporary password for <b className="text-ink">{u.username}</b> —{' '}
            <b className="text-ink">you won't see it again.</b>
          </>
        ),
        secret: res.temp_password,
      })
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not reset password.')
    }
  }

  return (
    <Section title="Users" sub="Admin only. Green dot = Kroger connected.">
      <Card>
        {rows.map((u) => {
          const isSelf = u.id === currentUserId
          return (
            <div key={u.id} className="px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="relative flex-none">
                  <RowIcon icon="user" />
                  <span
                    className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-surface ${
                      u.kroger_connected ? 'bg-success-dot' : 'bg-line2'
                    }`}
                    title={u.kroger_connected ? 'Kroger connected' : 'Kroger not connected'}
                  />
                </span>
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
                  <span className="truncate text-[14.5px] font-semibold text-ink">{u.username}</span>
                  {u.is_admin && <Badge>Admin</Badge>}
                  {isSelf && <Badge>You</Badge>}
                  {!u.is_active && <Badge tone="danger">Inactive</Badge>}
                </div>
              </div>
              <div className="mt-2.5 flex flex-wrap gap-2 pl-12">
                <button onClick={() => resetPassword(u)} className={`${pillAction} text-ink`}>
                  <Icon name="refresh" size={14} />
                  Reset password
                </button>
                {u.is_active ? (
                  <button
                    disabled={isSelf}
                    onClick={() => setConfirm({ user: u, activate: false })}
                    className={`${pillAction} text-danger`}
                    title={isSelf ? "You can't deactivate your own account" : undefined}
                  >
                    Deactivate
                  </button>
                ) : (
                  <button
                    onClick={() => setConfirm({ user: u, activate: true })}
                    className={`${pillAction} text-terracotta-deep`}
                  >
                    Activate
                  </button>
                )}
              </div>
            </div>
          )
        })}

        {rows.length === 0 && !adding && (
          <div className="px-4 py-3.5 text-[13.5px] text-muted">
            {users.isLoading ? 'Loading…' : 'No users yet.'}
          </div>
        )}

        {adding ? (
          <InlineCreate
            placeholder="Username"
            value={name}
            onChange={setName}
            onSubmit={submitCreate}
            pending={create.isPending}
            onCancel={() => {
              setAdding(false)
              setName('')
            }}
          />
        ) : (
          <AddRow label="Add user" onClick={() => setAdding(true)} />
        )}
      </Card>

      {reveal && (
        <SecretModal
          title={reveal.title}
          blurb={reveal.blurb}
          secret={reveal.secret}
          copyLabel="password"
          onClose={() => setReveal(null)}
        />
      )}

      <ConfirmDialog
        open={!!confirm}
        title={confirm?.activate ? 'Activate this user?' : 'Deactivate this user?'}
        body={
          confirm?.activate
            ? 'They will be able to sign in again.'
            : "They'll be signed out and can't sign in until reactivated. Their recipes and data are kept."
        }
        confirmLabel={confirm?.activate ? 'Activate' : 'Deactivate'}
        destructive={!confirm?.activate}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (confirm) {
            try {
              await setActive.mutateAsync({ id: confirm.user.id, active: confirm.activate })
              toast(confirm.activate ? 'User activated' : 'User deactivated')
            } catch (err) {
              toast(err instanceof ApiError ? err.message : 'Action failed.')
            }
          }
          setConfirm(null)
        }}
      />
    </Section>
  )
}

// Show-once reveal modal, shared by API tokens and admin temp passwords: the
// secret is displayed exactly once with a copy affordance and can't be re-fetched.
function SecretModal({
  title,
  blurb,
  secret,
  copyLabel = 'secret',
  onClose,
}: {
  title: string
  blurb: ReactNode
  secret: string
  copyLabel?: string
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(secret)
      setCopied(true)
      toast(`${copyLabel[0].toUpperCase()}${copyLabel.slice(1)} copied`)
    } catch {
      setCopied(false)
      toast('Copy failed — select and copy manually.')
    }
  }

  return (
    <div
      className="fixed inset-0 z-30 flex animate-pop items-center justify-center bg-dark/50 p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-[380px] rounded-panel bg-surface p-6 shadow-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-warn-bg text-warn">
          <Icon name="key" size={20} />
        </div>
        <div className="mt-3 font-serif text-[22px] font-medium tracking-[-0.01em]">{title}</div>
        <div className="mt-1.5 text-[13.5px] leading-relaxed text-muted">{blurb}</div>
        <div className="mt-4 rounded-[14px] border border-warn-border bg-warn-bg/60 p-3">
          <SectionLabel tone="warn" className="mb-2 flex items-center gap-1.5">
            <Icon name="alert" size={13} strokeWidth={2.4} />
            Shown once
          </SectionLabel>
          <div className="select-all break-all rounded-[10px] border border-line bg-surface px-3.5 py-3 font-mono text-[13px] leading-relaxed text-ink">
            {secret}
          </div>
        </div>
        <div className="mt-4 flex gap-2.5">
          <Button variant="secondary" className="h-12 flex-1 text-sm" onClick={copy}>
            <Icon name={copied ? 'check' : 'copy'} size={16} strokeWidth={copied ? 2.6 : 2} />
            {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button className="h-12 flex-1 text-sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </div>
  )
}

// --- Invitations (admin only) ----------------------------------------------

function InvitationsSection() {
  const invitations = useInvitations(true)
  const create = useCreateInvitation()
  const revoke = useRevokeInvitation()
  const [label, setLabel] = useState('')
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState<InvitationCreated | null>(null)
  const active = (invitations.data ?? []).filter(
    (invite) => !invite.redeemed_at && !invite.revoked_at && new Date(invite.expires_at) > new Date(),
  )
  const inviteUrl = created ? window.location.origin + '/join#invite=' + created.invitation_token : ''

  async function submit() {
    try {
      const invite = await create.mutateAsync({ recipient_label: label.trim() || undefined })
      setCreated(invite)
      setLabel('')
      setCreating(false)
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not create invitation.')
    }
  }

  return (
    <Section
      title="Invitations"
      sub="Invite someone with a one-time link. They choose their own password; links expire after 7 days."
    >
      <Card>
        {active.map((invite) => (
          <div key={invite.id} className="flex items-center gap-3 px-4 py-3">
            <RowIcon icon="link" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[14.5px] font-semibold">
                {invite.recipient_label || 'Unlabeled invitation'}
              </div>
              <div className="text-[12px] text-faint">Expires {shortDate(invite.expires_at)}</div>
            </div>
            <button
              onClick={async () => {
                await revoke.mutateAsync(invite.id)
                toast('Invitation revoked')
              }}
              className="-mr-2 min-h-[44px] flex-none px-2 text-[13px] font-semibold text-danger"
            >
              Revoke
            </button>
          </div>
        ))}
        {creating ? (
          <InlineCreate
            placeholder="Name (optional)"
            value={label}
            onChange={setLabel}
            onSubmit={submit}
            pending={create.isPending}
            onCancel={() => setCreating(false)}
          />
        ) : (
          <AddRow label="Create invitation" onClick={() => setCreating(true)} />
        )}
      </Card>
      {created && (
        <SecretModal
          title="Invitation created"
          blurb={
            <>
              Copy this link now — <b className="text-ink">you won't be able to see it again.</b>
            </>
          }
          secret={inviteUrl}
          copyLabel="invite link"
          onClose={() => setCreated(null)}
        />
      )}
    </Section>
  )
}
