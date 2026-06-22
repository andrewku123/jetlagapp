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
        # NOTE: the J's surface stop at Glen Park (tagged just "Glen Park" in OSM)
        # is REAL and is kept. It is renamed below and stays a SEPARATE station
        # from Glen Park BART (~80 m away but split by I-280); proximity alone
        # never merges across agencies — see the curated cross-system merge.
        # The F does not stop at Union Square/Market (Central Subway T station);
        # drop the spurious F surface node tagged at Market & Stockton.
        if ref == 'F' and nm.strip().lower() == 'market street & stockton street':
            continue
        muni_pts.append((nm, n['lat'], n['lon'], ref))

# nicer canonical display names for the shared subway / metro stations
RENAME = {
    'Embarcadero': 'Embarcadero Station', 'Montgomery Street': 'Montgomery St Station',
    'Powell Street': 'Powell St Station', 'Civic Center': 'Civic Center Station',
    'Van Ness': 'Van Ness Station', 'Church': 'Church St Station', 'Castro': 'Castro Station',
    'Forest Hill': 'Forest Hill Station', 'West Portal': 'West Portal Station',
    # The J's surface stop at Glen Park BART is tagged just "Glen Park" in OSM;
    # give it its SFMTA name so it doesn't collide with the BART station's name
    # (the two are deliberately NOT merged — see the cross-system merge below).
    'Glen Park': 'San Jose Ave/Glen Park Station',
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
    name = pick(c['names'])
    # Drop the F-only surface stops on Market St inland of Embarcadero — they
    # run directly above the Muni Metro subway and duplicate those stations.
    if c['lines'] == {'Muni F'} and name.startswith('Market Street &'):
        continue
    stations.append({'name': name, 'lat': c['lat'], 'lon': c['lon'], 'systems': {'Muni'},
                     'lines': c['lines'], 'names': set(c['names']) | {name},
                     'service': json.loads(json.dumps(FREQUENT))})

print("PRE cross-system merge counts:")
for sys in ['BART', 'Caltrain', 'VTA', 'Muni']:
    print(f"  {sys}: {sum(1 for s in stations if sys in s['systems'])}")
print("  total points:", len(stations))

# ---- Cross-system merge: CURATED from the official maps, NOT by distance. ----
# Two stops of *different* agencies are the same station ONLY when the official
# transit map marks them as a shared station. Proximity alone is NOT sufficient
# grounds to merge: e.g. Glen Park BART and the San Jose Ave Muni J stop are
# ~80 m apart but are split by I-280 (grade change, no shared concourse) and the
# SFMTA Metro map draws them as two distinct stations — so they stay separate.
#
# SHARED_STATIONS is the set of "Shared Station" markers read off the official
# maps (SF Muni Metro / BART / Caltrain / VTA). Each entry is (label, lat, lon);
# a cross-agency stop merges only if it lies within MERGE_RADIUS_M of an anchor.
#
#   *** HUMAN REVIEW REQUIRED ***
# This list is a real-world judgement call, not a formula. When expanding to a
# new metro, do NOT reinstate an automatic distance rule — review every shared
# station against that system's official map (physical connection, fare gates,
# grade) and add anchors here by hand.
SHARED_STATIONS = [
    ('Embarcadero',                        37.7929, -122.3969),  # BART + Muni
    ('Montgomery Street',                  37.7891, -122.4017),  # BART + Muni
    ('Powell Street',                      37.7846, -122.4074),  # BART + Muni
    ('Civic Center / UN Plaza',            37.7796, -122.4137),  # BART + Muni
    ('Balboa Park',                        37.7214, -122.4471),  # BART + Muni
    ('Millbrae',                           37.6000, -122.3868),  # BART + Caltrain
    ('Milpitas',                           37.4094, -121.8910),  # BART + VTA
    ('Mountain View',                      37.3947, -122.0764),  # Caltrain + VTA
    ('San Francisco (4th & King)',         37.7761, -122.3946),  # Caltrain + Muni
    ('San Jose Diridon',                   37.3287, -121.9034),  # Caltrain + VTA
    ('Tamien',                             37.3118, -121.8844),  # Caltrain + VTA
    # SFO is BART + SFO AirTrain on the map, but AirTrain stops are added by a
    # later pipeline stage (not in this script); kept here for completeness.
    ('San Francisco International Airport', 37.6161, -122.3920),
]
MERGE_RADIUS_M = 250

def shared_anchor(lat, lon):
    """Canonical label of the curated shared-station anchor this stop sits on, or
    None if the stop is not at an official shared station (so it won't merge)."""
    for label, alat, alon in SHARED_STATIONS:
        if hav((lat, lon), (alat, alon)) < MERGE_RADIUS_M:
            return label
    return None

def merge_service(a, b):
    out = {}
    for d in ('wd', 'we'):
        out[d] = {'served': a[d]['served'] or b[d]['served'],
                  'hourly': a[d]['hourly'] or b[d]['hourly']}
    return out

merged = []
for s in stations:
    anchor = shared_anchor(s['lat'], s['lon'])
    hit = None
    if anchor is not None:
        for m in merged:
            if m.get('_anchor') == anchor and m['systems'].isdisjoint(s['systems']):
                hit = m; break
    if hit:
        hit['systems'] |= s['systems']; hit['lines'] |= s['lines']; hit['names'] |= s['names']
        hit['lat'] = (hit['lat']+s['lat'])/2; hit['lon'] = (hit['lon']+s['lon'])/2
        hit['service'] = merge_service(hit['service'], s['service'])
    else:
        nd = dict(s); nd['_anchor'] = anchor; merged.append(nd)

# strip the internal anchor tag before output
for m in merged:
    m.pop('_anchor', None)

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
