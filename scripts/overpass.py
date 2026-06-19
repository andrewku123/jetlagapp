import requests, json, sys, time

OVERPASS="https://overpass-api.de/api/interpreter"

def run(q):
    for attempt in range(3):
        r=requests.post(OVERPASS, data={"data":q}, timeout=180, headers={"User-Agent":"jetlag-bayarea/1.0 (game tool)"})
        if r.status_code==200:
            return r.json()
        time.sleep(5)
    r.raise_for_status()

def stops_from_relations(data, want_refs=None):
    nodes={e['id']:e for e in data['elements'] if e['type']=='node'}
    rels=[e for e in data['elements'] if e['type']=='relation']
    out={}  # ref -> list of (name, lat, lon)
    for rel in rels:
        ref=rel.get('tags',{}).get('ref')
        if want_refs is not None and ref not in want_refs:
            continue
        line=out.setdefault(ref, [])
        seen=set()
        for m in rel['members']:
            if m['type']!='node': continue
            role=m.get('role','')
            if 'stop' not in role and 'platform' not in role: 
                continue
            n=nodes.get(m['ref'])
            if not n: continue
            name=n.get('tags',{}).get('name')
            if not name: continue
            if name in seen: continue
            seen.add(name)
            line.append((name, n['lat'], n['lon']))
    return out

queries={
 'caltrain':'[out:json][timeout:180];rel["route"="train"]["operator"~"Caltrain",i];(._;>;);out;',
 'muni':'[out:json][timeout:180];rel["route"~"light_rail|tram"]["network"~"Muni|Municipal",i];(._;>;);out;',
 'vta':'[out:json][timeout:180];rel["route"="light_rail"]["operator"~"Valley Transportation|VTA",i];(._;>;);out;',
}

results={}
for k,q in queries.items():
    print("== querying",k,"==", file=sys.stderr)
    d=run(q)
    results[k]=d
    # quick summary of relations found
    rels=[e for e in d['elements'] if e['type']=='relation']
    print(k, "relations:", [(r.get('tags',{}).get('ref'), r.get('tags',{}).get('name')) for r in rels], file=sys.stderr)
    json.dump(d, open(f'raw_{k}.json','w'))
print("done", file=sys.stderr)
