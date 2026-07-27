"""Enrich a region's station list with the attributes the elimination engine needs.

Adds per station: id, nameLength, county, city, elevation (m), distance to each
of the region's commercial airports and the nearest one — plus `state` on a map
that spans more than one (read off the region's own state polygons, so it agrees
with the shading the app draws). Writes the enriched file to the app's data dir.

Adding a city is one entry in `poi_geo.REGIONS` (`stations`, `agencies`,
`airports`), then:

    python3 scripts/build_attributes.py --region dc

It reads the raw station list the city's builder wrote (scripts/stations.dc.json
from build_dc_stations.py) and writes the enriched file the app imports.
"""
import argparse, json, math, os, time, sys, re, urllib.request, urllib.parse

import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


# `agencies` lists the system names a station builder may append to disambiguate
# same-named stations across agencies ("San Bruno (BART)"): the name-length
# question counts the *base* name, so only that parenthetical is stripped —
# never a descriptive one like "(Ocean Beach)".
def name_length(name, agencies):
    if not agencies:
        return len(name)
    suffix = re.compile(r'\s*\((?:' + '|'.join(map(re.escape, agencies)) + r')\)\s*$')
    return len(suffix.sub('', name))


def hav(a, b):
    R = 6371000.0
    dlat = math.radians(b[0]-a[0]); dlon = math.radians(b[1]-a[1])
    x = math.sin(dlat/2)**2 + math.cos(math.radians(a[0]))*math.cos(math.radians(b[0]))*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(x))

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'jetlag-bayarea/1.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def census_geo(lat, lon):
    base = 'https://geocoding.geo.census.gov/geocoder/geographies/coordinates'
    q = urllib.parse.urlencode({'x': lon, 'y': lat, 'benchmark': 'Public_AR_Current',
                                'vintage': 'Current_Current', 'format': 'json', 'layers': 'all'})
    try:
        d = get(base + '?' + q)
        geos = d['result']['geographies']
        county = None; city = None
        for key in geos:
            if 'Counties' in key and geos[key]:
                county = geos[key][0]['NAME']
        for key in geos:
            if 'Incorporated Places' in key and geos[key]:
                city = geos[key][0]['NAME']
        if city is None:
            for key in geos:
                if 'Census Designated Places' in key and geos[key]:
                    city = geos[key][0]['NAME']
        return county, city
    except Exception as e:
        print('census err', lat, lon, e, file=sys.stderr)
        return None, None

def usgs_elev(lat, lon):
    url = f'https://epqs.nationalmap.gov/v1/json?x={lon}&y={lat}&units=Meters&wkid=4326&includeDate=false'
    try:
        d = get(url)
        v = d.get('value')
        return round(float(v), 1) if v is not None else None
    except Exception as e:
        print('elev err', lat, lon, e, file=sys.stderr)
        return None

def place_lookup(cfg):
    """name -> [rings] for the region's Census places, or None before they exist.

    A station's `city` MUST be the polygon the app's `cityAt()` will resolve it
    to, not the Census geocoder's answer: the geocoder places a point by address
    range, so it names a city for a station that is (correctly) outside every
    polygon — Colma and Bayshore/NASA sit on unincorporated land — and the app
    would then print one city and eliminate on another. The places file is built
    after this script on a new map, so run this script again once it exists.
    """
    if 'places' not in cfg:
        return None
    path = os.path.join(ROOT, cfg['places'])
    if not os.path.exists(path):
        return None
    fc = json.load(open(path))
    out = []
    for f in fc['features']:
        g = f['geometry']
        polys = ([g['coordinates']] if g['type'] == 'Polygon' else g['coordinates'])
        out.append((f['properties']['name'], polys))
    return out


def state_lookup(cfg):
    """name -> [rings] for a multi-state map, so each station carries the state
    its dot sits in. Single-state maps get None (the question is log-only there)."""
    if 'statesGeo' not in cfg:
        return None
    fc = json.load(open(os.path.join(ROOT, cfg['statesGeo'])))
    out = []
    for f in fc['features']:
        g = f['geometry']
        polys = ([g['coordinates']] if g['type'] == 'Polygon' else g['coordinates'])
        out.append((f['properties']['name'], polys))
    return out


def in_ring(lat, lon, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def polygon_at(named_polys, lat, lon):
    for name, polys in named_polys:
        for poly in polys:
            if in_ring(lat, lon, poly[0]) and not any(in_ring(lat, lon, h) for h in poly[1:]):
                return name
    return None


def load_cache(path):
    cache = {}
    try:
        prev = json.load(open(path))
        for p in prev:
            if p.get('county') is not None or p.get('elevation') is not None:
                cache[(round(p['lat'], 5), round(p['lon'], 5))] = (
                    p.get('county'), p.get('city'), p.get('elevation'))
    except FileNotFoundError:
        pass
    return cache

def sync_cities(cfg, out_path):
    """Re-resolve every station's `city` from the places polygons, in place.

    The full enrichment pass needs the city builder's raw list (and re-fetches
    elevations), which an older map no longer has; this touches nothing but the
    one field the polygons own, so it is safe to re-run on a live dataset.
    """
    places = place_lookup(cfg)
    if places is None:
        sys.exit('no places file — build it with build_region_geo.py first')
    st = json.load(open(out_path))
    changed = 0
    for s in st:
        was, now = s.get('city'), polygon_at(places, s['lat'], s['lon'])
        if was != now:
            changed += 1
            print(f"{s['name']:30} {was} -> {now}", file=sys.stderr)
        s['city'] = now
    json.dump(st, open(out_path, 'w'), indent=1)
    print(f'wrote {out_path}: {changed}/{len(st)} cities changed')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cities-only', action='store_true',
                    help="only re-resolve `city` from the places polygons "
                         "(run after build_region_geo.py on an existing map)")
    args = poi_geo.add_region_arg(ap).parse_args()
    region, cities_only = args.region, args.cities_only
    cfg = poi_geo.REGIONS[region]
    if not cities_only and 'airports' not in cfg:
        sys.exit(f"{region}: no `agencies`/`airports` in poi_geo.REGIONS — its "
                 "station file is built elsewhere")
    SRC = poi_geo.work(region, 'stations.json')
    OUT = poi_geo.repo_path(region, 'stations')
    if cities_only:
        return sync_cities(cfg, OUT)
    AIRPORTS = cfg['airports']
    states = state_lookup(cfg)
    places = place_lookup(cfg)
    if places is None:
        print('no places file yet — city falls back to the Census geocoder; '
              're-run after build_region_geo.py', file=sys.stderr)
    st = json.load(open(SRC))
    CACHE = poi_geo.work(region, 'stations_enriched.json')
    cache = load_cache(CACHE)
    out = []
    hits = 0
    for i, s in enumerate(st):
        lat, lon = s['lat'], s['lon']
        ck = (round(lat, 5), round(lon, 5))
        if ck in cache:
            cc, city, elev = cache[ck]
            county = (cc + ' County') if cc else None
            hits += 1
            dist = {k: round(hav((lat, lon), v), 1) for k, v in AIRPORTS.items()}
            nearest = min(dist, key=dist.get)
            rec = dict(s)
            rec['id'] = f's{i:03d}'
            rec['nameLength'] = name_length(s['name'], cfg['agencies'])
            rec['county'] = cc
            rec['city'] = polygon_at(places, lat, lon) if places else city
            rec['elevation'] = elev
            rec['airportDist'] = dist; rec['nearestAirport'] = nearest
            if states:
                rec['state'] = polygon_at(states, lat, lon)
            out.append(rec)
            print(f"{i+1}/{len(st)} {s['name']:30} CACHED", file=sys.stderr)
            continue
        county, city = census_geo(lat, lon)
        time.sleep(0.3)
        elev = usgs_elev(lat, lon)
        time.sleep(0.2)
        dist = {k: round(hav((lat, lon), v), 1) for k, v in AIRPORTS.items()}
        nearest = min(dist, key=dist.get)
        rec = dict(s)
        rec['id'] = f's{i:03d}'
        rec['nameLength'] = name_length(s['name'], cfg['agencies'])
        rec['county'] = (county or '').replace(' County', '') or None
        rec['city'] = polygon_at(places, lat, lon) if places else city
        rec['elevation'] = elev
        rec['airportDist'] = dist
        rec['nearestAirport'] = nearest
        if states:
            rec['state'] = polygon_at(states, lat, lon)
        out.append(rec)
        print(f"{i+1}/{len(st)} {s['name']:30} {rec['county']} / {rec['city']} elev={elev}", file=sys.stderr)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, 'w'), indent=1)
    json.dump(out, open(CACHE, 'w'), indent=1)
    print('wrote', OUT, len(out))

if __name__ == '__main__':
    main()
