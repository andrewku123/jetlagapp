---
name: deploy-hideandseek
description: Build and deploy the Hide & Seek seeker tool as a static site (GitHub Pages by default). Use when asked to publish, deploy, or host the app.
---

# Deploy the app (static site)

It's a Vite + React static SPA — any static host works. GitHub Pages is wired up
out of the box.

## GitHub Pages (default, automatic)

A workflow at `.github/workflows/deploy.yml` runs **lint → test → build** on every
push to `main`/`master` and publishes `dist/` to Pages (a failing lint or test
blocks the deploy). It sets the Vite `base` to `/<repo-name>/` automatically via
the `BASE` env var.

One-time setup in the GitHub repo:
1. **Settings → Pages → Build and deployment → Source = "GitHub Actions"**.
2. Push to `main`. The "Deploy to GitHub Pages" Action runs build → deploy.
3. Site goes live at `https://<owner>.github.io/<repo>/`.

If the deploy fails on permissions, confirm the workflow's
`permissions: { pages: write, id-token: write }` block is present and that Pages
is set to the GitHub Actions source (not "Deploy from a branch").

## PR previews (per-branch) and the concurrency gotcha
Pushing a `devin/*` branch with an open PR triggers a **"Deploy PR previews"**
Action (on `pull_request`) that publishes to
`https://<owner>.github.io/<repo>/pr-preview/pr-<N>/`. This workflow uses a
**shared concurrency group**, so when several PR branches are pushed close
together the in-progress runs get **cancelled** — the result is a stale preview
even though the branch HEAD is up to date and CI shows no failures (the run shows
`completed/cancelled`, not failed). When updating multiple PRs in one go:
- Push them **sequentially**, and push the PR you most want verified (usually the
  app PR) **last**.
- Confirm its deploy actually finished with the Actions API, e.g.
  `GET /repos/<owner>/<repo>/actions/runs?branch=<branch>` and check the latest
  "Deploy PR previews" run is `completed/success` for your HEAD sha (not
  `cancelled`). If it was cancelled, push an empty/no-op commit or re-push to
  re-trigger.
- GitHub Pages caches aggressively; after a successful deploy a hard refresh
  (Cmd-Shift-R) may still be needed to see the change.

## The base-path detail (important)
`vite.config.ts` uses `base: process.env.BASE ?? '/'`. For a **project page**
(`owner.github.io/repo/`) the base **must** be `/repo/` or assets 404. The
workflow handles this; for manual builds do:
```bash
BASE=/<repo>/ npm run build      # project page
npm run build                    # root domain / user page / custom domain
```

## Manual / other hosts
```bash
npm ci
npm run build         # or BASE=/<repo>/ npm run build for a subpath
# deploy the dist/ folder:
#   Netlify:   netlify deploy --prod --dir=dist     (publish dir = dist, base = /)
#   Cloudflare Pages / Vercel: framework = Vite, output dir = dist, build = npm run build
#   any static server: serve dist/ at the chosen base path
```
For SPA hosts, no rewrite rules are needed (the app has no client-side routes).

## PWA note
The app ships a web manifest (`public/manifest.webmanifest`) + Apple meta tags,
so once served over HTTPS it is installable ("Add to Home Screen") on iOS/Android
and runs full-screen. No service worker is bundled; add `vite-plugin-pwa` if you
want offline caching.

## Verify after deploy
Open the live URL on desktop and a phone: map renders, station markers load, the
weekday/weekend + "≥hourly only" toggles change the count, and the mobile
controls bottom-sheet opens via the floating button.
