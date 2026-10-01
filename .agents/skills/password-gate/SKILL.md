---
name: password-gate
description: Change or work on the site's password screen (soft gate in front of the app) — rotate the password, understand what it does and doesn't protect, or debug "it keeps asking for the password". Use when asked to change the password, lock/unlock the site, or touch src/lib/gate.ts / PasswordGate.tsx.
---

# Password gate

## What it is
- `src/components/PasswordGate.tsx` wraps `<App />` in `src/main.tsx` (inside `CrashBoundary`).
- `src/lib/gate.ts` holds `PASSWORD_HASH` = SHA-256 of `'bahs-gate:' + password`. The plaintext is never in the repo.
- On a correct entry the browser stores that hash in `localStorage['bahs.unlock']`. Later loads compare it with
  `PASSWORD_HASH`, so the device stays unlocked until the hash in the code changes.
- Saved boards (`bahs.game.v1.<region>`) are separate keys. Unlocking, re-locking and rotating the password never touch them.
- The gate is per origin: unlocking production also unlocks PR previews (same `andrewku123.github.io` origin).

## What it is NOT
GitHub Pages has no server-side auth. The JS bundle and all station/POI data are still publicly fetchable, and anyone
can set `bahs.unlock` by hand. It keeps out casual visitors only. Real protection would need something like Cloudflare
Access in front of a custom domain.

## Rotate the password
1. `node scripts/gate_hash.mjs <new password>` prints the new hash.
2. Replace `PASSWORD_HASH` in `src/lib/gate.ts`.
3. Don't put the plaintext anywhere in the repo — `gate.test.ts` deliberately tests against a fixture password, not
   the real one. Tell players the new password out-of-band.
4. PR + merge. Every device is re-prompted on its next load; the stale-bundle check (`version.json`) makes phones pick
   up the new build on the next focus/load, so nobody is stuck on the old gate.

## Gotchas
- `crypto.subtle` exists only in secure contexts (https or `localhost`). Opening the dev server over a LAN IP
  (`http://192.168.x.x:5173`) shows "This browser cannot check the password (needs https)" — use localhost or the preview.
- The input `.trim()`s, so a phone keyboard's trailing autocorrect space doesn't fail the entry.
- Font size on the input is 16px on purpose: iOS Safari zooms the page on focus for anything smaller.
