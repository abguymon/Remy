import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useRegisterWithInvitation } from '../lib/queries'
import RatIcon from '../components/RatIcon'
import { Button } from '../components/ui'
import Icon from '../components/Icon'

const labelCls = 'flex flex-col gap-1.5 text-[13px] font-semibold text-ink'
const inputCls =
  'h-[52px] rounded-[14px] border border-line2 bg-surface px-4 text-[15px] font-normal text-ink outline-none transition-colors placeholder:text-faint focus:border-terracotta'

export default function Join() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get('invite') ?? ''
  const register = useRegisterWithInvitation()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(token ? null : 'This invitation link is incomplete.')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!token) return
    if (password.length < 12) {
      setError('Choose a password with at least 12 characters.')
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setError(null)
    try {
      await register.mutateAsync({ username, password, invitation_token: token })
      navigate('/login', { replace: true, state: { joined: true } })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create your account.')
    }
  }

  return (
    <div className="flex min-h-full flex-col bg-cream px-4 py-6 text-ink sm:px-10">
      <Link to="/" className="flex w-fit items-center gap-2.5" aria-label="Remy home">
        <RatIcon size={30} className="text-terracotta" />
        <span className="font-serif text-[27px] font-medium tracking-[-0.02em]">Remy</span>
      </Link>

      <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-10">
        <div className="mb-7 grid grid-cols-3 gap-2.5" aria-hidden>
          {['/landing/lemony-orzo.jpg', '/landing/massaman-curry.jpg', '/landing/carrot-risotto.jpg'].map((src) => (
            <img key={src} src={src} alt="" className="aspect-square w-full rounded-card bg-tile object-cover" />
          ))}
        </div>

        <div className="mb-7">
          <div className="text-[11.5px] font-bold uppercase tracking-[.14em] text-terracotta-deep">
            You’re invited
          </div>
          <h1 className="mt-3 font-serif text-[44px] font-medium leading-[1.02] tracking-[-0.03em] sm:text-[52px]">
            Join Remy
          </h1>
          <p className="mt-3 text-[15px] leading-6 text-muted">Create your own account to get started.</p>
        </div>

        <form onSubmit={submit} className="flex w-full flex-col gap-4">
          {error && (
            <div
              role="alert"
              className="flex items-center gap-2.5 rounded-[14px] border border-danger-border bg-danger-bg px-4 py-3 text-[13.5px] font-medium text-danger"
            >
              <Icon name="alert" size={17} className="flex-none" /> {error}
            </div>
          )}
          <label className={labelCls}>
            Username
            <input required minLength={3} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} className={inputCls} />
          </label>
          <label className={labelCls}>
            Password
            <input required minLength={12} type="password" autoComplete="new-password" placeholder="12+ characters" value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
          </label>
          <label className={labelCls}>
            Confirm password
            <input required type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputCls} />
          </label>
          <Button type="submit" className="mt-2 h-[54px] text-[15.5px]" disabled={!token || register.isPending}>
            {register.isPending ? 'Creating account…' : 'Create account'}
          </Button>
          <div className="mt-1 text-center text-[13.5px] text-muted">
            Already have an account?{' '}
            <Link to="/login" className="font-semibold text-terracotta-deep hover:text-terracotta">
              Sign in
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
