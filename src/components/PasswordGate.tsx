import { useState, type FormEvent, type ReactNode } from 'react'
import { isUnlocked, tryUnlock } from '../lib/gate'

export function PasswordGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(isUnlocked)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (unlocked) return <>{children}</>

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      if (await tryUnlock(password)) setUnlocked(true)
      else setError('Wrong password')
    } catch {
      setError('This browser cannot check the password (needs https)')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="gate" onSubmit={(e) => void submit(e)}>
      <h1>Hide &amp; Seek</h1>
      <p>Enter the game password.</p>
      <input
        type="password"
        autoFocus
        autoComplete="current-password"
        value={password}
        onChange={(e) => {
          setPassword(e.target.value)
          setError('')
        }}
        aria-label="Password"
      />
      <button type="submit" disabled={busy || !password}>
        Enter
      </button>
      {error && <div className="gate-error">{error}</div>}
    </form>
  )
}
