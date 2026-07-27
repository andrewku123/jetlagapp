// Regenerate STATIONS.md — the per-map list of eligible hiding stations.
//
// STATIONS.md is documentation only (nothing imports it). Its job is to make a
// data change reviewable: a rename, a re-coordinate, a line gained or lost shows
// up as a diff in the PR, which is impossible to see in a JSON blob or in the
// running app. So it is GENERATED — never hand-edit it, or the next run of this
// script silently reverts the edit.
//
//   node scripts/build_stations_md.mjs
//
// The file holds every map at once, so the script always writes all of them. A
// new map appears here once it is added to MAPS — keep an unfinished map out of
// that list until it ships, since this file is user-facing.

import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..')

// `priority` orders the per-system sections and picks each shared station's
// primary system, so a station served by several systems is listed exactly once.
const MAPS = [
  {
    id: 'bayarea',
    label: 'Bay Area',
    file: 'src/data/stations.json',
    priority: ['BART', 'Caltrain', 'VTA', 'Muni', 'SFO AirTrain'],
    note:
      'Ten F-only surface stops on Market St inland of Embarcadero are excluded — ' +
      'they sit directly above the Muni Metro subway and duplicate those stations.',
  },
  {
    id: 'sfmuni',
    label: 'SF Muni',
    file: 'src/data/sfmuni.stations.json',
    priority: ['Muni'],
    note:
      'These are the Bay Area map’s Muni rail stops, scoped to the City & County ' +
      'of San Francisco — the same stations, played as their own day-pass map.',
  },
  {
    id: 'la',
    label: 'LA Metro',
    file: 'src/data/la.stations.json',
    priority: ['Metro'],
    note:
      'Metro rail (A/B/C/D/E/K) plus the two busways the rulebook counts as ' +
      'rapid transit (G, J); each busway stop is a station in its own right.',
  },
]

const eligible = (day) => (st) => st.service[day].served && st.service[day].hourly
const cell = (st, day) => (eligible(day)(st) ? '✓' : '—')
const byName = (a, b) => a.name.localeCompare(b.name)
const fmtCoord = (st) => `${st.lat.toFixed(4)}, ${st.lon.toFixed(4)}`

const primaryOf = (st, priority) =>
  priority.find((sys) => st.systems.includes(sys)) ?? st.systems[0]

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

const sharedTag = (st, priority) => {
  if (st.systems.length < 2) return ''
  const ordered = priority.filter((s) => st.systems.includes(s))
  return ` _(shared: ${ordered.join(', ')})_`
}

function section(map) {
  const stations = JSON.parse(readFileSync(join(root, map.file), 'utf8'))
  const groups = new Map(map.priority.map((s) => [s, []]))
  for (const st of stations) {
    const p = primaryOf(st, map.priority)
    if (!groups.has(p)) groups.set(p, [])
    groups.get(p).push(st)
  }
  const membership = [...groups.keys()].map(
    (s) => `${s} ${stations.filter((st) => st.systems.includes(s)).length}`,
  )
  const wd = stations.filter(eligible('wd')).length
  const we = stations.filter(eligible('we')).length
  const multi = groups.size > 1

  const out = []
  out.push(`## ${map.label} — ${stations.length} stations`, '')
  out.push(
    `**${stations.length} unique hideable stations**` +
      (multi ? ' (deduped within and across systems)' : '') +
      `. Eligible after the at-least-hourly rule: **${wd} weekday / ${we} weekend**.`,
    '',
  )
  if (multi) {
    out.push(
      'Each station is listed once, under its **primary system**; the "shared" tag ' +
        'names the others (e.g. 4th & King is under Caltrain, not also Muni). ' +
        `Membership counts, which do count a shared station in every system it ` +
        `serves: ${membership.join(' · ')}.`,
      '',
    )
  }
  if (map.note) out.push(map.note, '')

  for (const [sys, rows] of groups) {
    if (!rows.length) continue
    if (multi) out.push(`### ${sys} (${rows.length})`, '')
    out.push('| Station | Lines | WD | WE | Lat, Lon |', '|---|---|:--:|:--:|---|')
    for (const st of rows.slice().sort(byName)) {
      out.push(
        `| ${st.name}${sharedTag(st, map.priority)} | ${lineLabels(st, sys)} | ` +
          `${cell(st, 'wd')} | ${cell(st, 'we')} | ${fmtCoord(st)} |`,
      )
    }
    out.push('')
  }
  return { text: out.join('\n'), count: stations.length, wd, we }
}

const built = MAPS.map((m) => [m, section(m)])
const lines = [
  '# Jet Lag: Hide & Seek — Eligible Stations',
  '',
  'The hider may only hide at a station listed here; travel is by any public',
  'transit. **WD / WE** = served on a weekday / weekend, **✓** = at least one',
  'train an hour through the daytime window (the game’s eligibility rule), **—**',
  '= not eligible that day.',
  '',
  '_Generated from the app’s own station data by `scripts/build_stations_md.mjs`',
  '— edit the data, not this file._',
  '',
]
for (const [m, s] of built) lines.push(`- [${m.label}](#${anchor(m, s)}) — ${s.count} stations`)
lines.push('')
for (const [, s] of built) lines.push(s.text)

function anchor(m, s) {
  return `${m.label}-${s.count}-stations`.toLowerCase().replace(/[^a-z0-9]+/g, '-')
}

writeFileSync(join(root, 'STATIONS.md'), lines.join('\n').replace(/\n+$/, '\n'))
console.log(
  built.map(([m, s]) => `${m.label} ${s.count} (${s.wd} wd / ${s.we} we)`).join(' · '),
)
