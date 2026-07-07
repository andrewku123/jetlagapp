#!/usr/bin/env python3
"""Build the SF Muni region data files by filtering/clipping the Bay Area files.

No new data is gathered: the SF Muni map is a strict subset of the Bay Area
dataset — the Muni-served stations on lines J/K/L/M/N/T/F (no cable car, no E),
with every other data file (POIs, play area, coastline/borders, places,
counties, ZCTAs, transit lines) clipped to the City & County of San Francisco.

Outputs src/data/sfmuni.*.json, all the exact same shape as their Bay Area
counterparts so the region-agnostic app code needs no per-city branching.
"""
import json
import os
from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union

DATA = os.path.join(os.path.dirname(__file__), '..', 'src', 'data')


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


def dump(name, obj):
    with open(os.path.join(DATA, name), 'w') as f:
        json.dump(obj, f, separators=(',', ':'))
    print('wrote', name, os.path.getsize(os.path.join(DATA, name)), 'bytes')


# ---------------------------------------------------------------------------
# 1. Stations: keep Muni-served stops; strip non-Muni systems/lines so the
#    shared downtown subway stops (Embarcadero, Powell, ...) read as Muni.
stations = load('stations.json')
muni = []
for s in stations:
    if 'Muni' not in s.get('systems', []):
        continue
    s = dict(s)
    s['systems'] = ['Muni']
    s['lines'] = [l for l in s['lines'] if l.startswith('Muni')]
    muni.append(s)
print('muni stations:', len(muni))
line_set = sorted({l for s in muni for l in s['lines']})
print('lines:', line_set)

# ---------------------------------------------------------------------------
# 2. Play area = the SF-city place polygon(s) that actually hold Muni stations
#    (drops the detached southern sliver + tiny offshore rings with no stations).
places = load('places.geojson.json')
sf_feats = [f for f in places['features'] if f['properties']['name'] == 'San Francisco city']
station_pts = [Point(s['lon'], s['lat']) for s in muni]
station_hull = unary_union([p.buffer(0.004) for p in station_pts])  # ~0.28 mi

play_polys = []
for f in sf_feats:
    g = shape(f['geometry'])
    parts = list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]
    for part in parts:
        if part.intersects(station_hull):
            play_polys.append(part)
play_area = unary_union(play_polys)
print('play area parts:', len(play_polys), 'bounds:', [round(b, 3) for b in play_area.bounds])

play_fc = {
    'type': 'FeatureCollection',
    'features': [{'type': 'Feature', 'properties': {'name': 'San Francisco'},
                  'geometry': mapping(play_area)}],
}
dump('sfmuni.play-area.geojson.json', play_fc)
dump('sfmuni.stations.json', muni)

# ---------------------------------------------------------------------------
# 3. POIs: keep those inside the play area.
poi = load('poi.json')
poi_out = {}
kept = dropped = 0
for cat, items in poi.items():
    keep = [p for p in items if play_area.contains(Point(p['lon'], p['lat']))]
    poi_out[cat] = keep
    kept += len(keep)
    dropped += len(items) - len(keep)
print('poi kept:', kept, 'dropped:', dropped, '->', {k: len(v) for k, v in poi_out.items()})
dump('sfmuni.poi.json', poi_out)

# ---------------------------------------------------------------------------
# 4. Transit lines: keep the Muni features (the 7 rail lines).
tl = load('transit-lines.geojson.json')
tl_out = {'type': 'FeatureCollection',
          'features': [f for f in tl['features'] if f['properties'].get('system') == 'Muni']}
print('transit-line features kept:', len(tl_out['features']))
dump('sfmuni.transit-lines.geojson.json', tl_out)

# ---------------------------------------------------------------------------
# 5. Places (city Matching): just San Francisco, clipped to the play area.
sf_place_geom = play_area  # SF is a consolidated city-county == play area
places_out = {'type': 'FeatureCollection',
              'features': [{'type': 'Feature', 'properties': {'name': 'San Francisco city'},
                            'geometry': mapping(sf_place_geom)}]}
dump('sfmuni.places.geojson.json', places_out)

# ---------------------------------------------------------------------------
# 6. Counties: keep SF + immediate neighbours (only SF is in play; neighbours
#    are kept for the out-of-play dim + the county-border measure feature).
counties = load('counties.geojson.json')
KEEP_COUNTIES = {'San Francisco', 'San Mateo', 'Marin', 'Alameda', 'Contra Costa'}
counties_out = {'type': 'FeatureCollection',
                'features': [f for f in counties['features']
                             if f['properties']['name'] in KEEP_COUNTIES]}
print('counties kept:', [f['properties']['name'] for f in counties_out['features']])
dump('sfmuni.counties.geojson.json', counties_out)

# ---------------------------------------------------------------------------
# 7. ZCTAs (ZIP measuring): keep those intersecting the play area.
zctas = load('zctas.geojson.json')
z_out = []
for f in zctas['features']:
    g = shape(f['geometry'])
    if g.intersects(play_area):
        z_out.append(f)
print('zctas kept:', len(z_out))
dump('sfmuni.zctas.geojson.json',
     {'type': 'FeatureCollection', 'features': z_out})

# ---------------------------------------------------------------------------
# 8. Measure features (coastline + county border): clip to the play area with a
#    generous buffer so nearby shore/border is still measured from inside SF.
mf = load('measure-features.geojson.json')
clip = play_area.buffer(0.05)  # ~3.5 mi buffer around SF
mf_out = {'type': 'FeatureCollection', 'features': []}
for f in mf['features']:
    g = shape(f['geometry'])
    c = g.intersection(clip)
    if c.is_empty:
        continue
    mf_out['features'].append({'type': 'Feature', 'properties': f['properties'],
                               'geometry': mapping(c)})
    print('measure feature', f['properties']['key'], 'clipped ->', c.geom_type)
dump('sfmuni.measure-features.geojson.json', mf_out)

print('\nDONE. SF Muni region built.')
