// Regenerate STATIONS.md from src/data/stations.json.
//
// STATIONS.md is documentation only (nothing imports it); this script keeps it
// in sync with the data. Each station is listed once under its PRIMARY system
// (priority order below); stations served by more than one system carry a
// "shared: …" tag and the other systems' lines keep their system prefix.
//
//   node scripts/build_stations_md.mjs   # writes STATIONS.md

import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..')
const stations = JSON.parse(
  readFileSync(join(root, 'src/data/stations.json'), 'utf8'),
)

// Primary-system priority: a shared station is listed under the first system it
// belongs to in this order.
const PRIORITY = ['BART', 'Caltrain', 'VTA', 'Muni', 'SFO AirTrain']
const primaryOf = (st) =>
  PRIORITY.find((sys) => st.systems.includes(sys)) ?? st.systems[0]

const eligible = (day) => (st) =>
  st.service[day].served && st.service[day].hourly
const cell = (st, day) => (eligible(day)(st) ? '✓' : '—')

// Lines for a row, with the primary system's own prefix stripped (other systems
// keep theirs). An entry equal to the bare system name (AirTrain) drops out.
function lineLabels(st, primary) {
  const out = []
  for (const line of st.lines) {
    if (line === primary) continue
    out.push(line.startsWith(primary + ' ') ? line.slice(primary.length + 1) : line)
  }
  return out.length ? out.join(', ') : '—'
}

const sharedTag = (st) => {
  if (st.systems.length < 2) return ''
  const ordered = PRIORITY.filter((s) => st.systems.includes(s))
  return ` _(shared: ${ordered.join(', ')})_`
}

const byName = (a, b) => a.name.localeCompare(b.name)
const fmtCoord = (st) => `${st.lat.toFixed(4)}, ${st.lon.toFixed(4)}`

// Group by primary system.
const groups = new Map(PRIORITY.map((s) => [s, []]))
for (const st of stations) groups.get(primaryOf(st)).push(st)

// Membership counts (a shared station counted in every system it serves).
const membership = Object.fromEntries(
  PRIORITY.map((s) => [s, stations.filter((st) => st.systems.includes(s)).length]),
)
const wdElig = stations.filter(eligible('wd')).length
const weElig = stations.filter(eligible('we')).length

const lines = []
lines.push('# Bay Area Hide & Seek — Eligible Stations', '')
lines.push(
  `**${stations.length} unique hideable stations** (deduped within and across systems).`,
)
lines.push(
  `Eligible counts after the <1 hr-frequency rule: ${wdElig} weekday / ${weElig} weekend.`,
  '',
)
lines.push(
  'Hide only at these stations; travel by any public transit. WD/WE = served on weekday/weekend; ✓ = at least hourly during the daytime window.',
  '',
)
lines.push(
  'Stations are grouped below by **primary system**, so each shared station is',
  'listed once (e.g. 4th & King appears under Caltrain, not also under Muni); the',
  '"shared" tag notes the other systems. Per-system *membership* counts (a shared',
  `station counted in every system it serves) are ${PRIORITY.map(
    (s) => `${s} ${membership[s]}`,
  ).join(' · ')}. (10 F-only surface stops on Market St inland of Embarcadero are`,
  'excluded — they sit directly above the Muni Metro subway and duplicate those',
  'stations.)',
  '',
)

lines.push('| Primary system | Stations |', '|---|---|')
for (const s of PRIORITY) lines.push(`| ${s} | ${groups.get(s).length} |`)
lines.push(`| **Total (deduped)** | **${stations.length}** |`, '')

for (const sys of PRIORITY) {
  const rows = groups.get(sys).slice().sort(byName)
  if (!rows.length) continue
  lines.push(`## ${sys} (${rows.length})`, '')
  lines.push('| Station | Lines | WD | WE | Lat, Lon |', '|---|---|:--:|:--:|---|')
  for (const st of rows) {
    lines.push(
      `| ${st.name}${sharedTag(st)} | ${lineLabels(st, sys)} | ${cell(
        st,
        'wd',
      )} | ${cell(st, 'we')} | ${fmtCoord(st)} |`,
    )
  }
  lines.push('')
}

writeFileSync(join(root, 'STATIONS.md'), lines.join('\n').replace(/\n+$/, '\n'))
console.log(
  `STATIONS.md: ${stations.length} stations (${wdElig} wd / ${weElig} we), ` +
    PRIORITY.map((s) => `${s} ${groups.get(s).length}`).join(' · '),
)
