#!/usr/bin/env python3
"""Build the review page's timetable: public/transit/bayarea.json.

Postgame review only (src/lib/transitNetwork.ts reads it). Every trip of every
system on the Bay Area map, reduced to the map's stations, with which days each
trip runs, so the review can compute "fastest way from here to every station,
leaving at 2:14 pm on Sunday".

Feeds come from 511's per-operator GTFS (BART, Muni rail, Caltrain, VTA light
rail, SFO AirTrain, and the Oakland Alameda Water Shuttle from SF Bay Ferry).
Muni cable cars and all buses are left out: they aren't lines on the map.

Run:  SF511_API_KEY=... python3 scripts/build_transit_network.py [--days 120]
      (or --gtfs-dir DIR with already unzipped DIR/<operator>/ feeds)
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sys
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIONS = ROOT / 'src/data/stations.json'
OUT = ROOT / 'public/transit/bayarea.json'

# operator id -> (map system name, route filter)
FEEDS = {
    'BA': ('BART', lambda r: True),
    'SF': ('Muni', lambda r: r['route_type'] == '0'),
    'CT': ('Caltrain', lambda r: r['route_type'] == '2'),
    'SC': ('VTA', lambda r: r['route_type'] == '0'),
    'SI': ('SFO AirTrain', lambda r: r['route_type'] == '0'),
    'SB': ('Water Shuttle', lambda r: r['route_id'] == 'OAS'),
}
MATCH_M = 200  # a GTFS stop belongs to the nearest map station of its system within this


def dist_m(a_lat, a_lon, b_lat, b_lon):
    r = 6371000
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def secs(t):
    h, m, s = (int(x) for x in t.strip().split(':'))
    return h * 3600 + m * 60 + s


def read_feed(op, gtfs_dir, key):
    if gtfs_dir:
        base = Path(gtfs_dir) / op
        return lambda name: (open(base / name, encoding='utf-8-sig') if (base / name).exists() else None)
    url = f'https://api.511.org/transit/datafeeds?api_key={key}&operator_id={op}'
    with urllib.request.urlopen(url, timeout=180) as res:
        z = zipfile.ZipFile(io.BytesIO(res.read()))
    names = set(z.namelist())
    return lambda name: (io.TextIOWrapper(z.open(name), encoding='utf-8-sig') if name in names else None)


def active_days(open_file, first: date, n: int):
    """service_id -> bitstring over [first, first+n) of the days it runs."""
    out: dict[str, list[str]] = {}
    f = open_file('calendar.txt')
    wd = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    if f:
        for r in csv.DictReader(f):
            start = datetime.strptime(r['start_date'][:8], '%Y%m%d').date()
            end = datetime.strptime(r['end_date'][:8], '%Y%m%d').date()
            bits = ['0'] * n
            for i in range(n):
                d = first + timedelta(days=i)
                if start <= d <= end and r[wd[d.weekday()]] == '1':
                    bits[i] = '1'
            out[r['service_id']] = bits
    f = open_file('calendar_dates.txt')
    if f:
        for r in csv.DictReader(f):
            d = datetime.strptime(r['date'], '%Y%m%d').date()
            i = (d - first).days
            bits = out.setdefault(r['service_id'], ['0'] * n)
            if 0 <= i < n:
                bits[i] = '1' if r['exception_type'] == '1' else '0'
    return {k: ''.join(v) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gtfs-dir')
    ap.add_argument('--days', type=int, default=120)
    ap.add_argument('--first-day', help='YYYY-MM-DD, default a week ago')
    args = ap.parse_args()
    key = os.environ.get('SF511_API_KEY', '')
    if not args.gtfs_dir and not key:
        sys.exit('set SF511_API_KEY or pass --gtfs-dir')
    first = date.fromisoformat(args.first_day) if args.first_day else date.today() - timedelta(days=7)

    stations = json.load(open(STATIONS))
    st_index = {s['id']: i for i, s in enumerate(stations)}
    services: list[str] = []
    svc_index: dict[str, int] = {}
    patterns: dict[tuple, dict] = {}
    report = []

    for op, (system, keep_route) in FEEDS.items():
        open_file = read_feed(op, args.gtfs_dir, key)
        mine = [s for s in stations if system in s['systems']]
        routes = {r['route_id']: r for r in csv.DictReader(open_file('routes.txt')) if keep_route(r)}
        trips = {t['trip_id']: t for t in csv.DictReader(open_file('trips.txt')) if t['route_id'] in routes}
        stop_map: dict[str, str | None] = {}
        for s in csv.DictReader(open_file('stops.txt')):
            lat, lon = float(s['stop_lat'] or 0), float(s['stop_lon'] or 0)
            best, bd = None, MATCH_M
            for m in mine:
                d = dist_m(lat, lon, m['lat'], m['lon'])
                if d < bd:
                    best, bd = m['id'], d
            stop_map[s['stop_id']] = best
        days = active_days(open_file, first, args.days)
        rows: dict[str, list[tuple[int, int, str]]] = {}
        for r in csv.DictReader(open_file('stop_times.txt')):
            if r['trip_id'] in trips:
                t = r['departure_time'] or r['arrival_time']
                if t:
                    rows.setdefault(r['trip_id'], []).append((int(r['stop_sequence']), secs(t), r['stop_id']))
        used = set()
        for trip_id, st in rows.items():
            st.sort()
            seq: list[tuple[str, int]] = []
            for _, t, stop in st:
                sid = stop_map.get(stop)
                if sid is None:
                    continue
                if seq and seq[-1][0] == sid:
                    continue
                seq.append((sid, t))
            if len(seq) < 2:
                continue
            trip = trips[trip_id]
            bits = days.get(trip['service_id'])
            if not bits or '1' not in bits:
                continue
            skey = f'{op}:{trip["service_id"]}'
            if skey not in svc_index:
                svc_index[skey] = len(services)
                services.append(bits)
            r = routes[trip['route_id']]
            name = f'{system} {r["route_short_name"] or r["route_long_name"]}'.strip()
            stops = tuple(st_index[s] for s, _ in seq)
            start = seq[0][1]
            offs = tuple(t - start for _, t in seq)
            p = patterns.setdefault((name, stops), {'route': name, 'stops': list(stops), 'shapes': {}, 'trips': []})
            shape = p['shapes'].setdefault(offs, len(p['shapes']))
            p['trips'].append([svc_index[skey], start, shape])
            used.update(s for s, _ in seq)
        missing = [m['name'] for m in mine if m['id'] not in used]
        report.append(f'{system}: {len(used)}/{len(mine)} stations served' + (f'; none for {", ".join(missing)}' if missing else ''))

    out_patterns = []
    for p in patterns.values():
        shapes = sorted(p['shapes'].items(), key=lambda kv: kv[1])
        p['trips'].sort(key=lambda t: (t[1], t[0]))
        out_patterns.append({'route': p['route'], 'stops': p['stops'], 'shapes': [list(s) for s, _ in shapes], 'trips': p['trips']})
    out = {
        'v': 1,
        'built': date.today().isoformat(),
        'firstDay': first.isoformat(),
        'days': args.days,
        'stations': [s['id'] for s in stations],
        'services': services,
        'patterns': out_patterns,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(',', ':')))
    print('\n'.join(report))
    print(f'{len(out_patterns)} patterns, {sum(len(p["trips"]) for p in out_patterns)} trips, {OUT.stat().st_size // 1024} KB -> {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
