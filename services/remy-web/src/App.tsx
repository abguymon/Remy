import { useEffect, useState } from 'react'

type Health = { status: string; version: string }

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setHealth)
      .catch((e: Error) => setError(e.message))
  }, [])

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-3 bg-stone-50 text-stone-800">
      <h1 className="text-3xl font-semibold">Remy</h1>
      <p className="text-stone-500">v2 scaffold — the app is being rebuilt.</p>
      <p className="text-sm text-stone-400">
        API:{' '}
        {health ? (
          <span className="text-green-600">healthy (v{health.version})</span>
        ) : error ? (
          <span className="text-red-600">unreachable ({error})</span>
        ) : (
          <span>checking…</span>
        )}
      </p>
    </main>
  )
}
