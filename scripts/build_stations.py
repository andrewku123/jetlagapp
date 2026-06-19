import json, csv, math
from collections import defaultdict

def hav(a, b):
    R = 6371000
    dlat = math.radians(b[0]-a[0]); dlon = math.radians(b[1]-a[1])
    x = math.sin(dlat/2)**2 + math.cos(math.radians(a[0]))*math.cos(math.radians(b[0]))*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(x))

FREQUENT = {'wd': {'served': True, 'hourly': True}, 'we': {'served': True, 'hourly': True}}

stations = []  # {name, lat, lon, systems:set, lines:set, names:set, service:dict}

# ---- BART (GTFS, location_type=1). Runs >hourly daytime every day. ----
with open('gtfs/bart/stops.txt') as f:
    for r in csv.DictReader(f):
        if r['location_type'] == '1':
            stations.append({'name': r['stop_name'], 'lat': float(r['stop_lat']), 'lon': float(r['stop_lon']),
                             'systems': {'BART'}, 'lines': set(), 'names': {r['stop_name']},
                             'service': json.loads(json.dumps(FREQUENT))})

# ---- Caltrain (authoritative GTFS-derived service file), SF -> Tamien ----
ct = json.load(open('caltrain_service.json'))
for o in ct:
    nm = 'San Francisco (4th & King)' if o['name'] == 'San Francisco' else o['name']
    stations.append({'name': nm, 'lat': o['lat'], 'lon': o['lon'],
                     'systems': {'Caltrain'}, 'lines': {'Caltrain'}, 'names': {nm},
                     'service': {'wd': {'served': o['wd_served'], 'hourly': o['wd_hourly']},
                                 'we': {'served': o['we_served'], 'hourly': o['we_hourly']}}})

# ---- VTA (OSM light rail). Runs >hourly daytime every day. ----
dv = json.load(open('raw_vta.json'))
vnodes = {e['id']: e for e in dv['elements'] if e['type'] == 'node'}
vstops = defaultdict(lambda: {'lines': set()})
for rel in [e for e in dv['elements'] if e['type'] == 'relation']:
    ref = rel.get('tags', {}).get('ref')
    for m in rel['members']:
        if m['type'] != 'node':
            continue
        if 'stop' not in m.get('role', '') and 'platform' not in m.get('role', ''):
            continue
        n = vnodes.get(m['ref'])
        if not n:
            continue
        nm = n.get('tags', {}).get('name')
        if not nm:
            continue
        s = vstops[nm]; s['lat'] = n['lat']; s['lon'] = n['lon']; s['lines'].add(ref)
for nm, s in vstops.items():
    stations.append({'name': nm, 'lat': s['lat'], 'lon': s['lon'], 'systems': {'VTA'},
                     'lines': {'VTA ' + l for l in s['lines']}, 'names': {nm},
                     'service': json.loads(json.dumps(FREQUENT))})

# ---- Muni (OSM): ALL rail stops on N/J/F/K/L/M/T (labeled + unlabeled dots),
# deduped within Muni at 120m (merges both directions + shared subway platforms).
# North Beach on the T is excluded (not in service / not in OSM). ----
dm = json.load(open('raw_muni.json'))
mnodes = {e['id']: e for e in dm['elements'] if e['type'] == 'node'}
want = {'N', 'J', 'F', 'K', 'L', 'M', 'T'}
muni_pts = []
for rel in [e for e in dm['elements'] if e['type'] == 'relation']:
    tg = rel.get('tags', {}); name = tg.get('name', ''); ref = tg.get('ref')
    if 'Muni' not in name or ref not in want:
        continue
    for m in rel['members']:
        if m['type'] != 'node':
            continue
        if 'stop' not in m.get('role', '') and 'platform' not in m.get('role', ''):
            continue
        n = mnodes.get(m['ref'])
        if not n:
            continue
        nm = n.get('tags', {}).get('name')
        if not nm or 'north beach' in nm.lower():
            continue
        # Glen Park has no Muni rail service (BART-only on the official map);
        # drop spurious OSM nodes tagged onto a Muni relation there.
        if nm.strip().lower() == 'glen park':
            continue
        muni_pts.append((nm, n['lat'], n['lon'], ref))

# nicer canonical display names for the shared subway / metro stations
RENAME = {
    'Embarcadero': 'Embarcadero Station', 'Montgomery Street': 'Montgomery St Station',
    'Powell Street': 'Powell St Station', 'Civic Center': 'Civic Center Station',
    'Van Ness': 'Van Ness Station', 'Church': 'Church St Station', 'Castro': 'Castro Station',
    'Forest Hill': 'Forest Hill Station', 'West Portal': 'West Portal Station',
}
mclusters = []
for nm, lat, lon, ref in muni_pts:
    # prefer an existing cluster with the identical stop name (any distance);
    # otherwise the nearest cluster within 150 m.
    target = next((c for c in mclusters if nm in c['names']), None)
    if target is None:
        near = [(hav((lat, lon), (c['lat'], c['lon'])), c) for c in mclusters]
        near = [(d, c) for d, c in near if d < 150]
        if near:
            target = min(near, key=lambda x: x[0])[1]
    if target is not None:
        target['names'].add(nm); target['lines'].add('Muni ' + ref)
        target['lat'] = (target['lat']*target['n']+lat)/(target['n']+1)
        target['lon'] = (target['lon']*target['n']+lon)/(target['n']+1); target['n'] += 1
    else:
        mclusters.append({'lat': lat, 'lon': lon, 'names': {nm}, 'lines': {'Muni ' + ref}, 'n': 1})

def pick(names):
    for n in names:
        if n in RENAME:
            return RENAME[n]
    plain = [x for x in names if '&' not in x]
    pool = plain if plain else list(names)
    return sorted(pool, key=len)[0]

for c in mclusters:
    stations.append({'name': pick(c['names']), 'lat': c['lat'], 'lon': c['lon'], 'systems': {'Muni'},
                     'lines': c['lines'], 'names': set(c['names']) | {pick(c['names'])},
                     'service': json.loads(json.dumps(FREQUENT))})

print("PRE cross-system merge counts:")
for sys in ['BART', 'Caltrain', 'VTA', 'Muni']:
    print(f"  {sys}: {sum(1 for s in stations if sys in s['systems'])}")
print("  total points:", len(stations))

# ---- Cross-system merge at 150m (only across different systems) ----
def merge_service(a, b):
    out = {}
    for d in ('wd', 'we'):
        out[d] = {'served': a[d]['served'] or b[d]['served'],
                  'hourly': a[d]['hourly'] or b[d]['hourly']}
    return out

merged = []
for s in stations:
    hit = None
    for m in merged:
        if m['systems'].isdisjoint(s['systems']) and hav((s["lat"], s["lon"]), (m["lat"], m["lon"])) < 200:
            hit = m; break
    if hit:
        hit['systems'] |= s['systems']; hit['lines'] |= s['lines']; hit['names'] |= s['names']
        hit['lat'] = (hit['lat']+s['lat'])/2; hit['lon'] = (hit['lon']+s['lon'])/2
        hit['service'] = merge_service(hit['service'], s['service'])
    else:
        merged.append(dict(s))

print("\nAFTER cross-system merge: total unique stations =", len(merged))

def eligible(s, day, hourly_only=True):
    sv = s['service'][day]
    return sv['served'] and (sv['hourly'] or not hourly_only)

for day in ('wd', 'we'):
    elig = [m for m in merged if eligible(m, day, True)]
    print(f"  Eligible ({'weekday' if day=='wd' else 'weekend'}, hourly-only): {len(elig)}")

# disambiguate stations that share a display name but are distinct physical
# stations (e.g. BART vs Caltrain "San Bruno") by appending the system.
from collections import Counter
namecount = Counter(m['name'] for m in merged)
for m in merged:
    if namecount[m['name']] > 1:
        m['name'] = f"{m['name']} ({sorted(m['systems'])[0]})"

out = []
for m in merged:
    out.append({'name': m['name'], 'lat': round(m['lat'], 6), 'lon': round(m['lon'], 6),
                'systems': sorted(m['systems']), 'lines': sorted(m['lines']),
                'aka': sorted(m['names']), 'service': m['service']})
out.sort(key=lambda x: (x['systems'][0], x['name']))
json.dump(out, open('stations.json', 'w'), indent=1)
print("\nwrote stations.json with", len(out), "stations")
