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
import math
import os
from shapely.geometry import shape, mapping, Point, Polygon
from shapely.ops import unary_union

DATA = os.path.join(os.path.dirname(__file__), '..', 'src', 'data')
SCRIPTS = os.path.dirname(__file__)

# Endgame hiding-zone radius for a Medium game (matches SIZE_PARAMS in the app).
HIDING_ZONE_MI = 0.25
MILES_PER_METER = 1 / 1609.344


def geodesic_circle(lat, lon, radius_mi, n=128):
    """A geodesic disk of `radius_mi`, using the same spherical metric (R = 6371
    km, destination-point formula) as the app's circlePolygon, so the play-area
    boundary lines up exactly with the rendered green hiding-zone circle."""
    R = 6371000.0  # metres — must match src/lib/geo.ts circlePolygon
    d = (radius_mi / MILES_PER_METER) / R
    lat1, lon1 = math.radians(lat), math.radians(lon)
    pts = []
    for i in range(n):
        brng = 2 * math.pi * i / n
        lat2 = math.asin(math.sin(lat1) * math.cos(d) +
                         math.cos(lat1) * math.sin(d) * math.cos(brng))
        lon2 = lon1 + math.atan2(math.sin(brng) * math.sin(d) * math.cos(lat1),
                                 math.cos(d) - math.sin(lat1) * math.sin(lat2))
        pts.append((math.degrees(lon2), math.degrees(lat2)))
    return Polygon(pts)


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
#    (drops the detached southern sliver + tiny offshore rings with no stations),
#    clipped to land (the raw TIGER place includes a bay-water wedge toward
#    Alameda), then unioned with each station's 0.25 mi endgame hiding zone so an
#    edge station's zone (e.g. Bayshore Blvd & Sunnydale Ave) is never dimmed
#    out of play. The final result is re-clipped to land so the zones never bulge
#    into the bay.
places = load('places.geojson.json')
sf_feats = [f for f in places['features'] if f['properties']['name'] == 'San Francisco city']
station_pts = [Point(s['lon'], s['lat']) for s in muni]
station_hull = unary_union([p.buffer(0.004) for p in station_pts])  # ~0.28 mi

# Dense water mask (SF Bay + Pacific) used by the Bay Area pipeline to trim the
# bay wedge off TIGER polygons.
with open(os.path.join(SCRIPTS, 'bay_water_mask.geojson')) as f:
    water = shape(json.load(f)['geometry'])

play_polys = []
for f in sf_feats:
    g = shape(f['geometry']).difference(water)  # clip the bay wedge off
    parts = list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]
    for part in parts:
        if part.intersects(station_hull):
            play_polys.append(part)
land = unary_union(play_polys)

# Union each station's endgame hiding zone (slightly padded so the rendered
# 128-gon circle sits fully inside), then re-clip to land.
zones = unary_union([geodesic_circle(s['lat'], s['lon'], HIDING_ZONE_MI + 0.01)
                     for s in muni])
play_area = unary_union([land, zones]).difference(water).buffer(0)
print('play area bounds:', [round(b, 3) for b in play_area.bounds],
      'parts:', len(play_area.geoms) if play_area.geom_type == 'MultiPolygon' else 1)

play_fc = {
    'type': 'FeatureCollection',
    'features': [{'type': 'Feature', 'properties': {'name': 'San Francisco'},
                  'geometry': mapping(play_area)}],
}
dump('sfmuni.play-area.geojson.json', play_fc)
dump('sfmuni.stations.json', muni)

# ---------------------------------------------------------------------------
# 3. POIs: keep those inside the play area. A tiny buffer (~40 m) keeps
#    waterfront POIs that sit on piers just past the land clip (e.g. the USS
#    Pampanito / SS Jeremiah O'Brien museums at Fisherman's Wharf) without
#    re-admitting the across-the-bay islands the wedge used to include.
poi = load('poi.json')
poi_keep_area = play_area.buffer(0.0006)
poi_out = {}
kept = dropped = 0
for cat, items in poi.items():
    keep = [p for p in items if poi_keep_area.contains(Point(p['lon'], p['lat']))]
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
# 5. Places (city Matching): just San Francisco, at its TRUE municipal boundary
#    (`land`), NOT the play area. The play area is padded south with each edge
#    station's 0.25 mi endgame hiding zone, which spills across the SF↔San Mateo
#    line into Brisbane; using it here would mislabel those border points as "San
#    Francisco city". The endgame county/city question needs the real border so it
#    can carve the part of a border station's hiding zone that lies outside SF.
sf_place_geom = land
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
