# Train recorder Worker

Cloudflare Worker behind the postgame review: it records BART and 511 live trip
updates every day 07:30-22:00 Pacific and stores saved rounds. Live at
https://jetlag-recorder.andrew-js-ku.workers.dev.

## Recording
- A cron (`*/10 * * * *`) kicks the `Recorder` Durable Object, which polls on an
  alarm while the Pacific clock is inside 07:30-22:00 and stops itself after.
- BART GTFS-RT every 30 s; 511 `tripupdates?agency=RG` every 61 s (59/hour,
  under 511's default 60/hour key limit), kept to the map's lines: Muni rail
  (J/K/L/M/N/T/F), VTA light rail, Caltrain and the Water Shuttle (OAS).
- Each poll is stored in D1 as gzipped JSON: a full snapshot every 10 minutes
  and diffs (changed trips + `gone` ids) in between.
- Days expire after 30 days unless kept or touched by a saved round; the oldest
  unprotected days also go if snapshots pass 400 MB (D1 free-plan cap is 500 MB).

## API
Every route except `/` and `/status` needs `X-Group-Password: <group password>`
(the same password as the app's gate; the Worker stores its salted hash as the
`GROUP_PASSWORD_HASH` secret, in `src/lib/gate.ts` format).

| Route | |
|---|---|
| `GET /status` | recorder state and today's counts (no password) |
| `GET /<region>/<date>` | that day's polls per feed (`bayarea`, `sfmuni`) |
| `GET /<region>/<date>/<bart\|511>?at=HH:MM` | what the feed showed at that time (Pacific, or unix ms) |
| `GET /<region>/<date>/<bart\|511>?from=&to=` | raw polls in a range (max 2 h) |
| `POST\|DELETE /<region>/<date>/keep` | keep a day past 30 days, or undo |
| `POST /rounds` | `{id, region, build, savedAt, game}`; same `id` again returns the stored round (`created: false`) |
| `GET /rounds?region=` | list, newest first, without bodies (`&full=1` adds them) |
| `GET /rounds/<id>` | full round, with `game` and `review` |
| `PUT /rounds/<id>` | `{review, ifUpdatedAt?}`; 409 if someone saved since `ifUpdatedAt` |
| `DELETE /rounds/<id>` | delete |

## Develop and deploy
```sh
cd worker && npm install
npx wrangler d1 migrations apply jetlag-recorder --local
# .dev.vars: SF511_API_KEY=..., GROUP_PASSWORD_HASH=..., ALWAYS_RECORD=1 (record outside the window)
npm run dev        # then curl "localhost:8787/__scheduled?cron=*/10+*+*+*+*" to start polling
npm run typecheck  # tests run from the repo root: npx vitest run worker
npm run migrate && npm run deploy   # needs CLOUDFLARE_API_TOKEN
```
