import json, urllib.request, urllib.parse, sys, time

OVERPASS = "https://overpass-api.de/api/interpreter"
Q = """
[out:json][timeout:240];
(
  area[admin_level=6]["name"="Alameda County"]["boundary"="administrative"];
  area[admin_level=6]["name"="Contra Costa County"]["boundary"="administrative"];
  area[admin_level=6]["name"="City and County of San Francisco"]["boundary"="administrative"];
  area[admin_level=6]["name"="San Mateo County"]["boundary"="administrative"];
  area[admin_level=6]["name"="Santa Clara County"]["boundary"="administrative"];
)->.a;
(
  nwr[natural=peak][name](area.a);
  nwr[leisure=golf_course][name](area.a);
  nwr[tourism=theme_park][name](area.a);
  nwr[amenity=hospital][name](area.a);
  nwr[natural=water][name](area.a);
  nwr[natural=bay][name](area.a);
  nwr[water=reservoir][name](area.a);
);
out tags center;
"""

def fetch(q):
    data = urllib.parse.urlencode({"data": q}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "bayarea-hideandseek/1.0 (reference-card)"})
            with urllib.request.urlopen(req, timeout=260) as r:
                return json.load(r)
        except Exception as e:
            print(f"attempt {attempt+1} failed: {e}", file=sys.stderr)
            time.sleep(6)
    raise SystemExit("overpass failed")

d = fetch(Q)
json.dump(d, open("/tmp/poi.json", "w"))
print("elements", len(d.get("elements", [])))
