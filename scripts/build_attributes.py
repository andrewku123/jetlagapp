"""Enrich stations.json with attributes needed by the elimination engine.

Adds per station: nameLength, county, city, elevation (m), distance to each
commercial airport (SFO/OAK/SJC) and nearest airport. Writes enriched file to
the app's data dir.
"""
import json, math, time, sys, urllib.request, urllib.parse

SRC = 'stations.json'
OUT = '/home/ubuntu/repos/bayarea-hideandseek/src/data/stations.json'

# Coordinates of each airport's Google Maps pin/icon (the point the official
# game rules measure from), per andrewku.
AIRPORTS = {
    'SFO': (37.619083, -122.381597),
    'OAK': (37.719016, -122.219595),
    'SJC': (37.363510, -121.928648),
}

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

def load_cache():
    cache = {}
    try:
        prev = json.load(open('stations_enriched.json'))
        for p in prev:
            if p.get('county') is not None or p.get('elevation') is not None:
                cache[(round(p['lat'], 5), round(p['lon'], 5))] = (
                    p.get('county'), p.get('city'), p.get('elevation'))
    except FileNotFoundError:
        pass
    return cache

def main():
    st = json.load(open(SRC))
    cache = load_cache()
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
            rec['id'] = f's{i:03d}'; rec['nameLength'] = len(s['name'])
            rec['county'] = cc; rec['city'] = city; rec['elevation'] = elev
            rec['airportDist'] = dist; rec['nearestAirport'] = nearest
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
        rec['nameLength'] = len(s['name'])
        rec['county'] = (county or '').replace(' County', '') or None
        rec['city'] = city
        rec['elevation'] = elev
        rec['airportDist'] = dist
        rec['nearestAirport'] = nearest
        out.append(rec)
        print(f"{i+1}/{len(st)} {s['name']:30} {rec['county']} / {city} elev={elev}", file=sys.stderr)
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, 'w'), indent=1)
    json.dump(out, open('stations_enriched.json', 'w'), indent=1)
    print('wrote', OUT, len(out))

if __name__ == '__main__':
    main()
