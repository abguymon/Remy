import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useLogin } from '../lib/queries'
import { useAuth } from '../stores/auth'
import RatIcon from '../components/RatIcon'
import { Button } from '../components/ui'

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
    <div className="grid min-h-full bg-cream lg:grid-cols-[minmax(420px,.84fr)_minmax(520px,1.16fr)]">
      <main className="relative flex min-h-screen flex-col px-6 py-7 sm:px-10 lg:px-14 lg:py-10">
        <Link to="/" className="flex w-fit items-center gap-2 text-ink" aria-label="Back to Remy home">
          <RatIcon size={29} hole="#F6F0E8" className="text-terracotta" />
          <span className="font-serif text-[27px] font-semibold tracking-tight">Remy</span>
        </Link>

        <div className="mx-auto flex w-full max-w-[390px] flex-1 flex-col justify-center py-12">
          <div className="mb-8">
            <div className="text-[12px] font-bold uppercase tracking-[.14em] text-terracotta">
              Welcome back
            </div>
            <h1 className="mt-3 font-serif text-[44px] font-semibold leading-none tracking-tight sm:text-[50px]">
              Let’s get dinner sorted.
            </h1>
            <p className="mt-4 text-[14.5px] leading-6 text-muted">
              Sign in to pick up your current plan, cookbook, and grocery cart.
            </p>
          </div>

          <form onSubmit={onSubmit} className="flex w-full flex-col gap-4">
            {state.joined && !error && (
              <div
                role="status"
                className="flex items-center gap-2 rounded-[11px] border border-[#C8DDCC] bg-success-bg px-3.5 py-3 text-[13px] text-success"
              >
                <span aria-hidden>✓</span> Your account is ready. Sign in to begin.
              </div>
            )}
            {error && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded-[11px] border border-danger-border bg-danger-bg px-3.5 py-3 text-[13px] text-danger"
              >
                <b className="font-bold" aria-hidden>!</b> {error}
              </div>
            )}

            <label className="flex flex-col gap-1.5 text-[13px] font-bold text-ink">
              Username
              <input
                required
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="min-h-[50px] rounded-[11px] border border-line2 bg-surface px-4 text-[15px] font-normal outline-none transition focus:border-terracotta"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-[13px] font-bold text-ink">
              Password
              <input
                required
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="min-h-[50px] rounded-[11px] border border-line2 bg-surface px-4 text-[15px] font-normal outline-none transition focus:border-terracotta"
              />
            </label>
            <Button
              type="submit"
              className="mt-2 min-h-[52px] text-[15px]"
              busy={login.isPending}
              busyLabel="Signing in…"
            >
              Sign in <span aria-hidden>→</span>
            </Button>
          </form>

          <div className="mt-7 rounded-xl border border-line bg-surface/60 px-4 py-3.5 text-[12.5px] leading-5 text-muted">
            New to Remy? Use the private invitation link you received to create your account.
          </div>
        </div>

        <Link to="/" className="w-fit text-[12px] font-semibold text-muted hover:text-ink">
          ← Learn more about Remy
        </Link>
      </main>

      <aside className="relative hidden min-h-screen overflow-hidden bg-ink p-12 text-surface lg:flex lg:flex-col lg:justify-center xl:p-20">
        <div className="absolute -right-24 -top-24 h-80 w-80 rounded-full bg-terracotta/20 blur-3xl" />
        <div className="absolute -bottom-32 -left-20 h-96 w-96 rounded-full bg-[#81865C]/20 blur-3xl" />
        <div className="relative mx-auto w-full max-w-[580px]">
          <div className="text-[12px] font-bold uppercase tracking-[.15em] text-[#E48A6D]">
            Your plan is waiting
          </div>
          <h2 className="mt-4 max-w-[530px] font-serif text-[47px] font-semibold leading-[1.05] tracking-tight xl:text-[56px]">
            Less list-making. More looking forward to dinner.
          </h2>

          <div className="mt-12 rounded-[20px] border border-white/10 bg-white/[.055] p-6 shadow-[0_25px_70px_rgba(0,0,0,.22)] backdrop-blur-sm xl:p-8">
            <div className="flex items-center justify-between border-b border-white/10 pb-5">
              <div>
                <div className="font-serif text-[24px] font-semibold">How Remy helps</div>
                <div className="mt-1 text-[12px] text-[#AFA398]">You approve every step</div>
              </div>
              <span className="rounded-full bg-[#3F7A50]/25 px-3 py-1.5 text-[10px] font-bold text-[#A9D0B2]">
                Private
              </span>
            </div>
            <div className="mt-2">
              {[
                ['1', 'Plan', 'Say what sounds good'],
                ['2', 'Pick', 'Choose recipes you’ll enjoy'],
                ['3', 'Review', 'Tidy the list and products'],
                ['4', 'Shop', 'Finish checkout with your store'],
              ].map(([number, title, body]) => (
                <div key={number} className="grid grid-cols-[34px_75px_1fr] items-center gap-3 border-b border-white/[.07] py-4 last:border-0">
                  <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/10 font-mono text-[10px] font-bold text-[#E48A6D]">
                    {number}
                  </span>
                  <span className="text-[13px] font-bold">{title}</span>
                  <span className="text-[12.5px] text-[#BFB3A8]">{body}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </aside>
    </div>
  )
}
