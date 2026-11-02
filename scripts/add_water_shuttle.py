#!/usr/bin/env python3
"""Add the Oakland Alameda Water Shuttle to the Bay Area map (weekends only).

The free shuttle across the Oakland Estuary is the only Bay Area boat that
passes the hourly 07:30-22:00 rule, and only Friday to Sunday (every 22-40 min;
it runs Tue-Thu until ~19:40 and not at all on Mondays). So its two docks are
hiding spots on weekends only (headwayMin.wd = 999), and its line is listed in
the Bay entry's `weekdayExcludedLines` in src/data/regions.ts, which keeps it
out of the line questions and off the map on weekdays.

This is a later stage of the station pipeline (like the SFO AirTrain stops):
run it after build_attributes.py / patch_lines.py. It is idempotent: it drops
any Water Shuttle stations/feature already there and re-adds them.

    python3 scripts/add_water_shuttle.py            # downloads the WETA GTFS
    python3 scripts/add_water_shuttle.py --gtfs DIR # or reads an unzipped feed

Then: python3 scripts/build_zone_elevation.py --region bay
      node scripts/build_stations_md.mjs
"""
import argparse
import io
import json
import os
import re
import urllib.request
import zipfile

import build_attributes as ba
import compute_headways as ch
import poi_geo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIONS = os.path.join(ROOT, 'src/data/stations.json')
TRANSIT = os.path.join(ROOT, 'src/data/transit-lines.geojson.json')
GTFS_URL = 'https://data.trilliumtransit.com/gtfs/sfbayferry-ca-us/sfbayferry-ca-us.zip'
GTFS_DIR = os.path.join(ROOT, 'scripts/_gtfs_weta')

SYSTEM = 'Water Shuttle'
LINE = 'Oakland Alameda Water Shuttle'
COLOR = '#c2185b'
ROUTE_SHORT_NAME = 'OAS'
# GTFS stop_id -> (display name, aka). Names in short sign form (St, Sq).
DOCKS = {
    '7216': ('Bohol Circle Immigrant Park', ['Alameda Bohol Circle Immigrant Park Dock']),
    '7215': ('Jack London Sq', ['Oakland Jack London Square Water Shuttle Dock']),
}


def fetch_gtfs(path):
    if os.path.exists(os.path.join(path, 'stops.txt')):
        return path
    with urllib.request.urlopen(GTFS_URL, timeout=60) as r:
        zipfile.ZipFile(io.BytesIO(r.read())).extractall(path)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--gtfs', help='unzipped WETA GTFS dir (default: download to scripts/_gtfs_weta)')
    gtfs = fetch_gtfs(ap.parse_args().gtfs or GTFS_DIR)

    stops = {r['stop_id']: r for r in ch._read_csv(os.path.join(gtfs, 'stops.txt'))}
    route = next(r for r in ch._read_csv(os.path.join(gtfs, 'routes.txt'))
                 if r['route_short_name'] == ROUTE_SHORT_NAME)
    # Weekday = every Mon-Fri: the Tue-Thu service doesn't count as a weekday
    # pattern, so the docks score 999 (no service on Mondays) and are weekend-only.
    heads = ch.gtfs_headways(gtfs)

    cfg = poi_geo.REGIONS['bay']
    places = ba.place_lookup(cfg)
    counties = ba.place_lookup({'places': cfg['countiesGeo']})
    st = [s for s in json.load(open(STATIONS)) if SYSTEM not in s['systems']]
    next_id = max(int(s['id'][1:]) for s in st if re.fullmatch(r's\d+', s['id'])) + 1
    for i, (stop_id, (name, aka)) in enumerate(DOCKS.items()):
        lat, lon = float(stops[stop_id]['stop_lat']), float(stops[stop_id]['stop_lon'])
        h = heads[stop_id]
        dist = {k: round(ba.hav((lat, lon), v), 1) for k, v in cfg['airports'].items()}
        st.append({
            'name': name,
            'lat': lat,
            'lon': lon,
            'systems': [SYSTEM],
            'lines': [LINE],
            'aka': aka,
            'service': {d: {'served': True, 'hourly': h[d] <= ch.THRESHOLD_MIN} for d in ('wd', 'we')},
            'id': f's{next_id + i:03d}',
            'nameLength': len(name),
            'county': ba.polygon_at(counties, lat, lon),
            'city': ba.polygon_at(places, lat, lon),
            'elevation': ba.usgs_elev(lat, lon),
            'airportDist': dist,
            'nearestAirport': min(dist, key=dist.get),
            'headwayMin': {'wd': h['wd'], 'we': h['we']},
        })
        print(st[-1]['id'], name, st[-1]['city'], st[-1]['headwayMin'])
    with open(STATIONS, 'w') as f:
        json.dump(st, f, indent=1)

    # Route geometry: the GTFS shape of one direction (the other is its reverse).
    trip = next(t for t in ch._read_csv(os.path.join(gtfs, 'trips.txt'))
                if t['route_id'] == route['route_id'] and t['direction_id'] == '0')
    pts = sorted((int(r['shape_pt_sequence']), float(r['shape_pt_lon']), float(r['shape_pt_lat']))
                 for r in ch._read_csv(os.path.join(gtfs, 'shapes.txt'))
                 if r['shape_id'] == trip['shape_id'])
    fc = json.load(open(TRANSIT))
    fc['features'] = [f for f in fc['features'] if f['properties']['system'] != SYSTEM]
    fc['features'].append({
        'type': 'Feature',
        'properties': {'system': SYSTEM, 'colors': [COLOR], 'name': LINE},
        'geometry': {'type': 'LineString', 'coordinates': [[round(x, 6), round(y, 6)] for _, x, y in pts]},
    })
    with open(TRANSIT, 'w') as f:
        json.dump(fc, f)


if __name__ == '__main__':
    main()
