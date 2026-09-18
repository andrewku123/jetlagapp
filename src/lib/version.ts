// A phone once sat on a black page because its cached index.html pointed at asset
// hashes the deploy had replaced; only a new deploy (or clearing site data) fixed
// it. Every build stamps itself and ships the same stamp in version.json, so the
// running page can notice it is stale and reload itself once.

export const BUILD_ID: string = __BUILD_ID__

const ATTEMPT_KEY = 'bahs.reloadedFor'

// Reload only when the served build differs from the running one, and only once
// per remote build: if the reload comes back stale anyway (a cache that refuses to
// revalidate), a second attempt would loop forever on a page the player can't use.
export function shouldReload(
  local: string,
  remote: string | null,
  lastAttempt: string | null,
): boolean {
  if (!remote || !local) return false
  if (remote === local) return false
  return remote !== lastAttempt
}

export async function checkForNewBuild(now: () => void = () => location.reload()): Promise<void> {
  const remote = await fetchBuildId()
  let lastAttempt: string | null = null
  try {
    lastAttempt = sessionStorage.getItem(ATTEMPT_KEY)
  } catch {
    // private mode / storage disabled: fall through with no attempt recorded
  }
  if (!shouldReload(BUILD_ID, remote, lastAttempt)) return
  try {
    sessionStorage.setItem(ATTEMPT_KEY, remote!)
  } catch {
    // ignore
  }
  await dropCaches()
  now()
}

async function fetchBuildId(): Promise<string | null> {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}version.json`, { cache: 'no-store' })
    if (!res.ok) return null
    const body: unknown = await res.json()
    const id = (body as { build?: unknown }).build
    return typeof id === 'string' ? id : null
  } catch {
    return null // offline mid-game: leave the running build alone
  }
}

async function dropCaches(): Promise<void> {
  try {
    if (!('caches' in window)) return
    const keys = await caches.keys()
    await Promise.all(keys.map((k) => caches.delete(k)))
  } catch {
    // ignore
  }
}

// Check on load, and again whenever the tab is brought back — a deploy usually
// lands while the phone is in a pocket between games.
export function watchForNewBuild(): void {
  void checkForNewBuild()
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') void checkForNewBuild()
  })
}
