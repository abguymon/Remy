import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useLogin } from '../lib/queries'
import { useAuth } from '../stores/auth'
import RatIcon from '../components/RatIcon'
import { Button } from '../components/ui'
import Icon from '../components/Icon'

const inputCls =
  'h-[52px] rounded-[14px] border border-line2 bg-surface px-4 text-[15px] font-normal text-ink outline-none transition-colors focus:border-terracotta'

type LoginState = {
  from?: string
  joined?: boolean
}

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const setToken = useAuth((s) => s.setToken)
  const login = useLogin()
  const navigate = useNavigate()
  const location = useLocation()
  const state = (location.state ?? {}) as LoginState
  const destination = state.from?.startsWith('/app') ? state.from : '/app'

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const res = await login.mutateAsync({ username, password })
      setToken(res.access_token)
      navigate(destination, { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "That username or password didn't match." : err.message)
      } else {
        setError('Something went wrong. Try again.')
      }
    }
  }

  return (
    <div className="grid min-h-full bg-cream text-ink lg:grid-cols-[minmax(440px,.9fr)_minmax(520px,1.1fr)]">
      <main className="relative flex min-h-screen flex-col px-4 py-6 sm:px-10 lg:px-14 lg:py-10">
        <Link to="/" className="flex w-fit items-center gap-2.5 text-ink" aria-label="Back to Remy home">
          <RatIcon size={30} className="text-terracotta" />
          <span className="font-serif text-[27px] font-medium tracking-[-0.02em]">Remy</span>
        </Link>

        <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-12">
          <div className="mb-8">
            <div className="text-[11.5px] font-bold uppercase tracking-[.14em] text-terracotta-deep">
              Welcome back
            </div>
            <h1 className="mt-3 font-serif text-[44px] font-medium leading-[1.02] tracking-[-0.03em] sm:text-[52px]">
              Let’s get dinner sorted.
            </h1>
            <p className="mt-4 text-[15px] leading-6 text-muted">
              Sign in to pick up your current plan, cookbook, and grocery cart.
            </p>
          </div>

          <form onSubmit={onSubmit} className="flex w-full flex-col gap-4">
            {state.joined && !error && (
              <div
                role="status"
                className="flex items-center gap-2.5 rounded-[14px] bg-success-bg px-4 py-3 text-[13.5px] font-medium text-success"
              >
                <Icon name="check" size={17} strokeWidth={2.4} className="flex-none" /> Your account is ready. Sign in to begin.
              </div>
            )}
            {error && (
              <div
                role="alert"
                className="flex items-center gap-2.5 rounded-[14px] border border-danger-border bg-danger-bg px-4 py-3 text-[13.5px] font-medium text-danger"
              >
                <Icon name="alert" size={17} className="flex-none" /> {error}
              </div>
            )}

            <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-ink">
              Username
              <input
                required
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className={inputCls}
              />
            </label>
            <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-ink">
              Password
              <input
                required
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputCls}
              />
            </label>
            <Button
              type="submit"
              className="mt-2 h-[54px] text-[15.5px]"
              busy={login.isPending}
              busyLabel="Signing in…"
            >
              Sign in <Icon name="chevronRight" size={18} strokeWidth={2.2} />
            </Button>
          </form>

          <div className="mt-7 flex gap-3 rounded-card border border-line bg-surface px-4 py-3.5 text-[13px] leading-5 text-muted">
            <Icon name="key" size={18} className="mt-px flex-none text-faint" />
            <span>New to Remy? Use the private invitation link you received to create your account.</span>
          </div>
        </div>

        <Link
          to="/"
          className="inline-flex w-fit items-center gap-1 text-[13px] font-semibold text-muted hover:text-ink"
        >
          <Icon name="back" size={15} strokeWidth={2.2} /> Learn more about Remy
        </Link>
      </main>

      <aside className="relative hidden min-h-screen p-5 lg:block xl:p-6">
        <div className="relative h-full overflow-hidden rounded-panel bg-tile">
          <img
            src="/landing/pasta-norma.jpg"
            alt="Pasta alla Norma with eggplant, tomato and ricotta salata"
            className="absolute inset-0 h-full w-full object-cover"
          />
          <span className="absolute left-5 top-5 inline-flex items-center gap-1.5 rounded-full bg-surface/85 px-3 py-1.5 text-[12px] font-semibold text-ink backdrop-blur">
            <Icon name="clock" size={13} /> Pasta alla Norma · 45 min
          </span>

          <div className="absolute inset-x-5 bottom-5 rounded-panel border border-line bg-surface p-6 xl:inset-x-8 xl:bottom-8 xl:p-7">
            <div className="text-[11.5px] font-bold uppercase tracking-[.14em] text-terracotta-deep">
              Your plan is waiting
            </div>
            <h2 className="mt-2 max-w-[460px] font-serif text-[32px] font-medium leading-[1.06] tracking-[-0.025em] xl:text-[38px]">
              Less list-making. More looking forward to dinner.
            </h2>

            <div className="mt-5 flex items-center justify-between border-t border-divider pt-4">
              <div className="font-serif text-[19px] font-medium">How Remy helps</div>
              <span className="inline-flex items-center gap-1 rounded-full bg-success-bg px-2.5 py-1 text-[11px] font-bold text-success">
                <Icon name="key" size={12} strokeWidth={2.4} /> Private
              </span>
            </div>
            <div className="mt-0.5 text-[12.5px] text-faint">You approve every step</div>
            <ol className="mt-3 grid grid-cols-2 gap-x-5 gap-y-3 2xl:grid-cols-4">
              {[
                ['1', 'Plan', 'Say what sounds good'],
                ['2', 'Pick', 'Choose recipes you’ll enjoy'],
                ['3', 'Review', 'Tidy the list and products'],
                ['4', 'Shop', 'Finish checkout with your store'],
              ].map(([number, title, body]) => (
                <li key={number} className="flex gap-2.5">
                  <span className="tab-fig flex h-7 w-7 flex-none items-center justify-center rounded-full bg-terracotta-soft font-serif text-[14px] font-medium text-terracotta-deep">
                    {number}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[13.5px] font-bold">{title}</span>
                    <span className="block text-[12.5px] leading-[1.35] text-muted">{body}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </aside>
    </div>
  )
}
