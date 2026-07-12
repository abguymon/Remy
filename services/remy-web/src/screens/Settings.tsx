// Settings (DESIGN_BRIEF §4.10) — edit register. Kroger account (connect/return
// toast/disconnect), store picker (ZIP search → select), fulfillment control,
// pantry chip editor, favorite sites list, API tokens with show-once modal.
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError } from '../lib/api'
import {
  useAdminUsers,
  useApiTokens,
  useChangePassword,
  useCreateAdminUser,
  useCreateApiToken,
  useDisconnectKroger,
  useKrogerAuth,
  useKrogerStatus,
  useMe,
  useResetUserPassword,
  useRevokeApiToken,
  useSelectStore,
  useSetUserActive,
  useSettings,
  useStoreSearch,
  useUpdateSettings,
} from '../lib/queries'
import type {
  AdminUserInfo,
  ApiTokenCreated,
  FulfillmentMethod,
  SettingsResponse,
  StoreLocation,
} from '../lib/types'
import { shortDate } from '../lib/format'
import { toast } from '../stores/toast'
import { Button, ConfirmDialog, SectionLabel, Spinner } from '../components/ui'
import UsualsSettings from './settings/UsualsSettings'

const KROGER_ERRORS: Record<string, string> = {
  exchange_failed: "Couldn't complete the Kroger connection. Try again.",
  state_expired: 'The connection link expired. Try again.',
  invalid_state: 'The connection link was invalid. Try again.',
  missing_code_or_state: 'Kroger returned an incomplete response. Try again.',
  access_denied: 'You declined the Kroger connection.',
}

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

  if (settings.isLoading || !settings.data) {
    return (
      <div className="px-5 py-6">
        <div className="font-serif text-[28px] font-semibold tracking-tight">Settings</div>
        <div className="mt-6 flex items-center gap-2 text-sm text-muted">
          <Spinner /> Loading…
        </div>
      </div>
    )
  }

  return (
    <div className="px-5 pb-10 pt-3.5">
      <div className="font-serif text-[28px] font-semibold tracking-tight">Settings</div>
      <KrogerSection />
      <StoreSection settings={settings.data} />
      <UsualsSettings settings={settings.data} />
      <PantrySection settings={settings.data} />
      <SitesSection settings={settings.data} />
      <TokensSection />
      {me.data?.is_admin && <UsersSection currentUserId={me.data.id} />}
      <AccountSection />
    </div>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-6">
      <SectionLabel className="mb-2">{label}</SectionLabel>
      {children}
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
    <Section label="Kroger account">
      <div className="flex items-center justify-between gap-3 rounded-card border border-line bg-surface p-4">
        <div>
          <div className="text-[15px] font-semibold">Kroger</div>
          <div
            className={`mt-1.5 inline-flex items-center gap-1.5 rounded-md px-2 py-[3px] text-[12px] font-semibold ${
              connected ? 'bg-success-bg text-success' : 'bg-danger-bg text-danger'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-success-dot' : 'bg-danger-dot'}`}
            />
            {status.isLoading ? 'Checking…' : connected ? 'Connected' : 'Not connected'}
          </div>
        </div>
        {connected ? (
          <button
            onClick={() => setConfirm(true)}
            className="rounded-[9px] border border-line2 bg-cream px-3.5 py-2.5 text-[13px] font-semibold text-danger"
          >
            Disconnect
          </button>
        ) : (
          <Button className="px-4 py-2.5 text-[13px]" onClick={connect} disabled={auth.isPending}>
            {auth.isPending ? 'Connecting…' : 'Connect'}
          </Button>
        )}
      </div>

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
    <Section label="Store">
      <div className="rounded-card border border-line bg-surface p-4">
        {settings.store_location_id && !changing ? (
          <div className="flex items-start gap-3">
            <div className="flex-1">
              <div className="text-[15px] font-semibold">{settings.store_name ?? 'Selected store'}</div>
              {settings.zip_code && (
                <div className="mt-0.5 text-[12.5px] text-faint">ZIP {settings.zip_code}</div>
              )}
            </div>
            <button
              onClick={() => setChanging(true)}
              className="text-[12.5px] font-semibold text-terracotta"
            >
              Change
            </button>
          </div>
        ) : (
          <StoreSearch
            initialZip={settings.zip_code ?? ''}
            hasStore={!!settings.store_location_id}
            onCancel={() => setChanging(false)}
            onSelected={() => setChanging(false)}
          />
        )}

        {/* Fulfillment segmented control */}
        <div className="mt-3.5 flex gap-1.5 rounded-[10px] border border-line2 bg-cream p-1">
          {(['PICKUP', 'DELIVERY'] as FulfillmentMethod[]).map((m) => {
            const active = settings.fulfillment_method === m
            return (
              <button
                key={m}
                onClick={() => updateSettings.mutate({ fulfillment_method: m })}
                className={`flex-1 rounded-[7px] py-2.5 text-[13px] font-semibold ${
                  active ? 'bg-terracotta text-white' : 'text-muted'
                }`}
              >
                {m === 'PICKUP' ? 'Pickup' : 'Delivery'}
              </button>
            )
          })}
        </div>
      </div>
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
      <div className="flex gap-2">
        <input
          placeholder="ZIP code"
          value={zip}
          inputMode="numeric"
          onChange={(e) => setZip(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && run()}
          className="flex-1 rounded-[10px] border border-line2 bg-cream px-3 py-2.5 text-sm outline-none focus:border-terracotta"
        />
        <Button className="px-4 py-2.5 text-sm" onClick={run} disabled={search.isPending}>
          {search.isPending ? 'Searching…' : 'Search'}
        </Button>
        {hasStore && (
          <Button variant="ghost" className="px-2 py-2.5 text-sm" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>

      {error && <div className="mt-2 text-[12.5px] text-danger">{error}</div>}

      {search.isSuccess && results.length === 0 && (
        <div className="mt-3 text-[13px] text-muted">No stores found near that ZIP.</div>
      )}

      {results.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-[11px] border border-line2">
          {results.map((s: StoreLocation) => (
            <button
              key={s.id}
              disabled={select.isPending}
              onClick={async () => {
                await select.mutateAsync(s.id)
                toast(`Store set to ${s.name ?? 'selected store'}`)
                onSelected()
              }}
              className="flex w-full items-center justify-between gap-3 border-b border-divider px-3.5 py-3 text-left last:border-0 hover:bg-cream disabled:opacity-60"
            >
              <div className="min-w-0">
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
    <Section label="Pantry staples">
      <div className="rounded-card border border-line bg-surface p-4">
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <span
              key={item}
              className="inline-flex items-center gap-1.5 rounded-full border border-line2 bg-cream py-1.5 pl-3 pr-1.5 text-[13px] text-ink"
            >
              {item}
              <button
                aria-label={`Remove ${item}`}
                onClick={() => persist(items.filter((i) => i !== item))}
                className="flex h-[18px] w-[18px] items-center justify-center rounded-full bg-line2 text-[11px] leading-none text-muted"
              >
                ✕
              </button>
            </span>
          ))}
          <input
            placeholder="Add staple…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') add()
            }}
            onBlur={add}
            className="w-[120px] rounded-full border border-dashed border-[#D8CDB9] bg-transparent px-3.5 py-1.5 text-[13px] outline-none"
          />
        </div>
        <button
          onClick={() => persist(defaultsRef.current)}
          className="mt-3 text-[12.5px] font-semibold text-terracotta"
        >
          Reset to defaults
        </button>
      </div>
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

  return (
    <Section label="Favorite recipe sites">
      <div className="overflow-hidden rounded-card border border-line bg-surface">
        {sites.map((domain, i) => (
          <div
            key={domain}
            className="flex items-center gap-2.5 border-b border-divider px-3.5 py-2.5"
          >
            <div className="flex flex-col">
              <button
                aria-label="Move up"
                disabled={i === 0}
                onClick={() => move(i, -1)}
                className="text-[11px] leading-none text-hint disabled:opacity-30"
              >
                ▲
              </button>
              <button
                aria-label="Move down"
                disabled={i === sites.length - 1}
                onClick={() => move(i, 1)}
                className="text-[11px] leading-none text-hint disabled:opacity-30"
              >
                ▼
              </button>
            </div>
            <span className="tab-fig w-4 text-[12px] text-hint">{i + 1}</span>
            <span className="flex-1 text-[14px] text-ink">{domain}</span>
            <button
              aria-label={`Remove ${domain}`}
              onClick={() => persist(sites.filter((s) => s !== domain))}
              className="text-[15px] text-hint"
            >
              ✕
            </button>
          </div>
        ))}
        <div className="flex items-center gap-2 px-3.5 py-2.5">
          <input
            placeholder="Add a site (e.g. seriouseats.com)"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && add()}
            className="flex-1 rounded-[9px] border border-line2 bg-cream px-3 py-2 text-[13.5px] outline-none focus:border-terracotta"
          />
          <Button variant="secondary" className="px-3.5 py-2 text-[13px]" onClick={add}>
            Add
          </Button>
        </div>
      </div>
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
    <Section label="API tokens">
      <div className="overflow-hidden rounded-card border border-line bg-surface">
        {active.map((t) => (
          <div key={t.id} className="flex items-center gap-2.5 border-b border-divider px-3.5 py-3">
            <div className="flex-1">
              <div className="text-[14px] font-semibold">{t.name}</div>
              <div className="text-[11.5px] text-faint">
                Created {shortDate(t.created_at)} ·{' '}
                {t.last_used_at ? `Last used ${shortDate(t.last_used_at)}` : 'Never used'}
              </div>
            </div>
            <button
              onClick={() => setRevokeId(t.id)}
              className="text-[12.5px] font-semibold text-danger"
            >
              Revoke
            </button>
          </div>
        ))}

        {active.length === 0 && !creating && (
          <div className="px-3.5 py-3 text-[13px] text-muted">
            No tokens yet. Create one to connect an MCP client.
          </div>
        )}

        {creating ? (
          <div className="flex items-center gap-2 px-3.5 py-3">
            <input
              autoFocus
              placeholder="Token name (e.g. Claude Desktop)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submitCreate()}
              className="flex-1 rounded-[9px] border border-line2 bg-cream px-3 py-2 text-[13.5px] outline-none focus:border-terracotta"
            />
            <Button className="px-3.5 py-2 text-[13px]" onClick={submitCreate} disabled={create.isPending}>
              {create.isPending ? '…' : 'Create'}
            </Button>
            <Button
              variant="ghost"
              className="px-2 py-2 text-[13px]"
              onClick={() => {
                setCreating(false)
                setName('')
              }}
            >
              Cancel
            </Button>
          </div>
        ) : (
          <button
            onClick={() => setCreating(true)}
            className="w-full px-3.5 py-3 text-left text-[13.5px] font-semibold text-terracotta"
          >
            ＋ Create token
          </button>
        )}
      </div>

      {created && (
        <SecretModal
          title="Token created"
          blurb={
            <>
              Copy it now — <b>you won't be able to see it again.</b>
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

  const tooShort = next.length > 0 && next.length < 8
  const mismatch = confirm.length > 0 && next !== confirm
  const canSubmit =
    current.length > 0 && next.length >= 8 && confirm.length > 0 && next === confirm

  async function submit() {
    setError(null)
    if (next !== confirm) {
      setError('New passwords do not match.')
      return
    }
    if (next.length < 8) {
      setError('New password must be at least 8 characters.')
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

  const inputClass =
    'w-full rounded-[10px] border border-line2 bg-cream px-3 py-3 text-sm outline-none focus:border-terracotta'

  return (
    <Section label="Account">
      <div className="rounded-card border border-line bg-surface p-4">
        <div className="text-[15px] font-semibold">Change password</div>
        <div className="mt-3 flex flex-col gap-2.5">
          <input
            type="password"
            autoComplete="current-password"
            placeholder="Current password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className={inputClass}
          />
          <input
            type="password"
            autoComplete="new-password"
            placeholder="New password (min 8 characters)"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            className={inputClass}
          />
          <input
            type="password"
            autoComplete="new-password"
            placeholder="Confirm new password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && canSubmit && submit()}
            className={inputClass}
          />
        </div>

        {tooShort && (
          <div className="mt-2 text-[12.5px] text-muted">
            New password must be at least 8 characters.
          </div>
        )}
        {mismatch && <div className="mt-2 text-[12.5px] text-danger">Passwords don't match.</div>}
        {error && <div className="mt-2 text-[12.5px] text-danger">{error}</div>}

        <Button
          className="mt-3.5 w-full py-3"
          onClick={submit}
          disabled={!canSubmit || changePassword.isPending}
        >
          {changePassword.isPending ? 'Updating…' : 'Update password'}
        </Button>
      </div>
    </Section>
  )
}

// --- Users (admin only) ----------------------------------------------------

function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'danger' }) {
  return (
    <span
      className={`flex-none rounded-md px-1.5 py-[2px] text-[10.5px] font-semibold ${
        tone === 'danger' ? 'bg-danger-bg text-danger' : 'border border-line2 bg-cream text-muted'
      }`}
    >
      {children}
    </span>
  )
}

type Reveal = { title: string; blurb: React.ReactNode; secret: string }

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
            Temporary password for <b>{created.username}</b>. Share it securely — they should change
            it after signing in, and <b>you won't see it again.</b>
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
            New temporary password for <b>{u.username}</b> — <b>you won't see it again.</b>
          </>
        ),
        secret: res.temp_password,
      })
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not reset password.')
    }
  }

  const actionClass =
    'rounded-[9px] border border-line2 bg-cream px-3 py-2.5 text-[12.5px] font-semibold'

  return (
    <Section label="Users">
      <div className="overflow-hidden rounded-card border border-line bg-surface">
        {rows.map((u) => {
          const isSelf = u.id === currentUserId
          return (
            <div key={u.id} className="border-b border-divider px-3.5 py-3 last:border-0">
              <div className="flex items-center gap-2.5">
                <span
                  className={`h-2 w-2 flex-none rounded-full ${
                    u.kroger_connected ? 'bg-success-dot' : 'bg-line2'
                  }`}
                  title={u.kroger_connected ? 'Kroger connected' : 'Kroger not connected'}
                />
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
                  <span className="truncate text-[14px] font-semibold text-ink">{u.username}</span>
                  {u.is_admin && <Badge>Admin</Badge>}
                  {isSelf && <Badge>You</Badge>}
                  {!u.is_active && <Badge tone="danger">Inactive</Badge>}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  onClick={() => resetPassword(u)}
                  className={`${actionClass} text-muted hover:text-ink`}
                >
                  Reset password
                </button>
                {u.is_active ? (
                  <button
                    disabled={isSelf}
                    onClick={() => setConfirm({ user: u, activate: false })}
                    className={`${actionClass} text-danger disabled:opacity-40`}
                    title={isSelf ? "You can't deactivate your own account" : undefined}
                  >
                    Deactivate
                  </button>
                ) : (
                  <button
                    onClick={() => setConfirm({ user: u, activate: true })}
                    className={`${actionClass} text-terracotta`}
                  >
                    Activate
                  </button>
                )}
              </div>
            </div>
          )
        })}

        {rows.length === 0 && !adding && (
          <div className="px-3.5 py-3 text-[13px] text-muted">
            {users.isLoading ? 'Loading…' : 'No users yet.'}
          </div>
        )}

        {adding ? (
          <div className="flex items-center gap-2 px-3.5 py-3">
            <input
              autoFocus
              placeholder="Username"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submitCreate()}
              className="flex-1 rounded-[9px] border border-line2 bg-cream px-3 py-2 text-[13.5px] outline-none focus:border-terracotta"
            />
            <Button className="px-3.5 py-2 text-[13px]" onClick={submitCreate} disabled={create.isPending}>
              {create.isPending ? '…' : 'Create'}
            </Button>
            <Button
              variant="ghost"
              className="px-2 py-2 text-[13px]"
              onClick={() => {
                setAdding(false)
                setName('')
              }}
            >
              Cancel
            </Button>
          </div>
        ) : (
          <button
            onClick={() => setAdding(true)}
            className="w-full px-3.5 py-3 text-left text-[13.5px] font-semibold text-terracotta"
          >
            ＋ Add user
          </button>
        )}
      </div>

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
  blurb: React.ReactNode
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
      className="absolute inset-0 z-30 flex animate-pop items-center justify-center p-6"
      style={{ background: 'rgba(40,30,20,.4)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-[360px] rounded-[18px] bg-surface p-[22px] shadow-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="font-serif text-xl font-semibold">{title}</div>
        <div className="mt-1.5 text-[13px] leading-relaxed text-muted">{blurb}</div>
        <div className="my-3.5 break-all rounded-[10px] bg-dark px-3.5 py-3 font-mono text-[12.5px] text-[#E4B8A6]">
          {secret}
        </div>
        <div className="flex gap-2.5">
          <Button variant="secondary" className="flex-1 py-3 text-sm" onClick={copy}>
            {copied ? 'Copied ✓' : 'Copy'}
          </Button>
          <Button className="flex-1 py-3 text-sm" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </div>
  )
}
