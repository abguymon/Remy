import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../lib/api'
import { useRegisterWithInvitation } from '../lib/queries'
import RatIcon from '../components/RatIcon'
import { Button } from '../components/ui'

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
    <div className="flex min-h-full flex-col justify-center px-8 py-12" style={{ background: 'linear-gradient(180deg,#F6F0E8 0%,#F1E7D8 100%)' }}>
      <div className="mb-8 text-center">
        <RatIcon size={56} hole="#F4EDE1" className="mx-auto mb-2 text-terracotta" />
        <div className="font-serif text-[52px] font-semibold tracking-tight text-ink">Join Remy</div>
        <div className="mt-1.5 text-[14.5px] text-muted">Create your own account to get started.</div>
      </div>
      <form onSubmit={submit} className="mx-auto flex w-full max-w-[340px] flex-col gap-3">
        {error && <div className="rounded-[10px] border border-danger-border bg-danger-bg px-3 py-2.5 text-[13px] text-danger">{error}</div>}
        <input required minLength={3} autoComplete="username" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} className="rounded-[11px] border border-line2 bg-surface px-4 py-3.5 text-[15px] outline-none focus:border-terracotta" />
        <input required minLength={12} type="password" autoComplete="new-password" placeholder="Password (12+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} className="rounded-[11px] border border-line2 bg-surface px-4 py-3.5 text-[15px] outline-none focus:border-terracotta" />
        <input required type="password" autoComplete="new-password" placeholder="Confirm password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="rounded-[11px] border border-line2 bg-surface px-4 py-3.5 text-[15px] outline-none focus:border-terracotta" />
        <Button type="submit" className="mt-1 py-3.5 text-[15px]" disabled={!token || register.isPending}>
          {register.isPending ? 'Creating account…' : 'Create account'}
        </Button>
        <div className="text-center text-[13px] text-muted">Already have an account? <Link to="/login" className="font-semibold text-terracotta">Sign in</Link></div>
      </form>
    </div>
  )
}
