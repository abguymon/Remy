// Minimal functional login (T8 restyles). The flow needs auth, so this is a
// working sign-in against POST /auth/login. Matches the prototype's warm login
// gradient closely enough to not jar.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useLogin } from '../lib/queries'
import { useAuth } from '../stores/auth'
import RatIcon from '../components/RatIcon'
import { Button } from '../components/ui'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const setToken = useAuth((s) => s.setToken)
  const login = useLogin()
  const navigate = useNavigate()

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const res = await login.mutateAsync({ username, password })
      setToken(res.access_token)
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.status === 401
            ? "That username or password didn't match."
            : err.message,
        )
      } else {
        setError('Something went wrong. Try again.')
      }
    }
  }

  return (
    <div
      className="flex min-h-full flex-col justify-center px-8 py-12"
      style={{ background: 'linear-gradient(180deg,#F6F0E8 0%,#F1E7D8 100%)' }}
    >
      <div className="mb-8 text-center">
        <RatIcon size={56} hole="#F4EDE1" className="mx-auto mb-2 text-terracotta" />
        <div className="font-serif text-[52px] font-semibold tracking-tight text-ink">Remy</div>
        <div className="mt-1.5 text-[14.5px] text-muted">Meals in, groceries out.</div>
      </div>
      <form onSubmit={onSubmit} className="mx-auto flex w-full max-w-[340px] flex-col gap-3">
        {error && (
          <div className="flex items-center gap-2 rounded-[10px] border border-danger-border bg-danger-bg px-3 py-2.5 text-[13px] text-danger">
            <b className="font-bold">!</b> {error}
          </div>
        )}
        <input
          placeholder="Username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="rounded-[11px] border border-line2 bg-surface px-4 py-3.5 text-[15px] outline-none focus:border-terracotta"
        />
        <input
          placeholder="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-[11px] border border-line2 bg-surface px-4 py-3.5 text-[15px] outline-none focus:border-terracotta"
        />
        <Button type="submit" className="mt-1 py-3.5 text-[15px]" disabled={login.isPending}>
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
