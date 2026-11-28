// Soft password gate. GitHub Pages can't authenticate, so this only keeps casual
// visitors out: the data is still in the public bundle. The repo stores a salted
// hash, never the password. A phone that unlocked stores that hash plus the typed
// password (for the review backend) and walks straight in until PASSWORD_HASH changes; the saved boards are separate keys and
// are never touched. Regenerate with `node scripts/gate_hash.mjs <password>`.
export const PASSWORD_HASH = 'e0417033ef40530eb49015eebaea9ee0c78653b80413f91b6ce0df804e887e9f'

const SALT = 'bahs-gate:'
const UNLOCK_KEY = 'bahs.unlock'
// The typed password, kept so saved rounds can authenticate to the review
// backend (X-Group-Password); the Worker only stores its hash.
const PASSWORD_KEY = 'bahs.group.pw'

export async function hashPassword(password: string): Promise<string> {
  const bytes = new TextEncoder().encode(SALT + password)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

export function isUnlocked(expected: string = PASSWORD_HASH): boolean {
  try {
    return localStorage.getItem(UNLOCK_KEY) === expected && !!localStorage.getItem(PASSWORD_KEY)
  } catch {
    return false
  }
}

export async function tryUnlock(password: string, expected: string = PASSWORD_HASH): Promise<boolean> {
  const typed = password.trim()
  if ((await hashPassword(typed)) !== expected) return false
  try {
    localStorage.setItem(UNLOCK_KEY, expected)
    localStorage.setItem(PASSWORD_KEY, typed)
  } catch {
    // storage disabled: unlocked for this page load only
  }
  return true
}

export function groupPassword(): string {
  try {
    return localStorage.getItem(PASSWORD_KEY) ?? ''
  } catch {
    return ''
  }
}
