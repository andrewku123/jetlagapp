#!/usr/bin/env python3
"""Build the DC map's station list: WMATA Metrorail, from OSM.

Metrorail is the whole map — MARC/VRE are commuter rail whose stops run out to
Baltimore/Fredericksburg/Martinsburg and mostly fail the "served at least hourly
every day" eligibility rule, and the H Street streetcar is barely mapped in OSM
(no route relation, no named stops), so neither is included. See the
add-transit-city skill.

Two OSM quirks handled here:
  * Metro is tagged network="Washington Metro" (NOT "WMATA"), so a WMATA-keyed
    query silently returns nothing.
  * The four two-level transfer stations (Metro Center, Gallery Place, Fort
    Totten, L'Enfant Plaza) each carry TWO station nodes, one per level. They are
    one station, so identical names merge at any distance.

Line membership comes from the route relations' stop/platform members snapped to
the nearest station; the per-line totals are asserted against WMATA's published
counts so a bad OSM edit can't silently shrink a line.

Run: python3 scripts/build_dc_stations.py   # -> scripts/stations.dc.json
Then: python3 scripts/build_attributes.py --region dc
"""
import json
import math
import os
import time
from collections import defaultdict

import requests

import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = poi_geo.work("dc", "raw_metro.json")
OUT = poi_geo.work("dc", "stations.json")
OVERPASS = "https://overpass-api.de/api/interpreter"

# Metrorail runs at worst every 20 min on a branch, all week.
FREQUENT = {"wd": {"served": True, "hourly": True},
            "we": {"served": True, "hourly": True}}

LINES = {"R": "Red Line", "B": "Blue Line", "O": "Orange Line",
         "S": "Silver Line", "Y": "Yellow Line", "G": "Green Line"}
# Published station counts per line (Wikipedia, current as of the 2025 service
# pattern: some Silver trains run past Largo to New Carrollton and some Yellow
# trains past Mount Vernon Square to Greenbelt, so those branches count).
EXPECTED = {"Red Line": 27, "Blue Line": 28, "Orange Line": 26,
            "Silver Line": 39, "Yellow Line": 22, "Green Line": 21}
SNAP_M = 400  # stop node -> station node; platforms sit a block from the pin

QUERY = """[out:json][timeout:300];
(node["railway"="station"]["station"="subway"]["network"="Washington Metro"];
 rel["route"="subway"]["network"="Washington Metro"];);
(._;>;);out;"""


def hav(a, b):
    R = 6371000.0
    dlat, dlon = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    x = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0]))
         * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


def overpass(query):
    for i in range(5):
        r = requests.post(OVERPASS, data={"data": query}, timeout=300,
                          headers={"User-Agent": "jetlag-dc/1.0 (game tool)"})
        if r.status_code == 200 and r.text.startswith("{"):
            return r.json()
        print(f"  overpass retry {i}: {r.status_code}")
        time.sleep(15)
    r.raise_for_status()


def fetch():
    if os.path.exists(RAW):
        return json.load(open(RAW))
    data = overpass(QUERY)
    json.dump(data, open(RAW, "w"))
    return data


def main():
    data = fetch()
    nodes = {e["id"]: e for e in data["elements"] if e["type"] == "node"}

    # --- stations: one per name (merges the two-level transfer stations) ---
    by_name = {}
    for e in nodes.values():
        t = e.get("tags", {})
        if t.get("railway") != "station" or t.get("station") != "subway":
            continue
        if t.get("network") != "Washington Metro" or not t.get("name"):
            continue
        st = by_name.setdefault(t["name"], {"name": t["name"], "lat": 0.0, "lon": 0.0,
                                            "n": 0, "lines": set(), "codes": set()})
        st["lat"] += e["lat"]
        st["lon"] += e["lon"]
        st["n"] += 1
        if t.get("railway:ref"):
            st["codes"].update(t["railway:ref"].split(";"))
    for st in by_name.values():
        st["lat"] /= st["n"]
        st["lon"] /= st["n"]
    print("stations:", len(by_name))

    # --- line membership from the route relations ---
    stations = list(by_name.values())
    unsnapped = defaultdict(set)
    for rel in [e for e in data["elements"] if e["type"] == "relation"]:
        ref = rel.get("tags", {}).get("ref")
        if ref not in LINES:
            continue
        for m in rel["members"]:
            if m["type"] != "node" or ("stop" not in m.get("role", "")
                                       and "platform" not in m.get("role", "")):
                continue
            n = nodes.get(m["ref"])
            if not n:
                continue
            nearest = min(stations, key=lambda s: hav((n["lat"], n["lon"]),
                                                      (s["lat"], s["lon"])))
            if hav((n["lat"], n["lon"]), (nearest["lat"], nearest["lon"])) <= SNAP_M:
                nearest["lines"].add(LINES[ref])
            else:
                unsnapped[LINES[ref]].add(n.get("tags", {}).get("name"))
    if unsnapped:
        print("WARNING unsnapped stops:", {k: sorted(v) for k, v in unsnapped.items()})

    counts = {ln: sum(1 for s in stations if ln in s["lines"]) for ln in EXPECTED}
    print("per-line:", counts)
    bad = {ln: (counts[ln], EXPECTED[ln]) for ln in EXPECTED if counts[ln] != EXPECTED[ln]}
    if bad:
        raise SystemExit(f"line membership disagrees with WMATA (got, want): {bad}")
    orphans = [s["name"] for s in stations if not s["lines"]]
    if orphans:
        raise SystemExit(f"stations with no line: {orphans}")

    out = [{"name": s["name"], "lat": round(s["lat"], 6), "lon": round(s["lon"], 6),
            "systems": ["Metrorail"], "lines": sorted(s["lines"]),
            "aka": sorted(s["codes"]), "service": json.loads(json.dumps(FREQUENT))}
           for s in sorted(stations, key=lambda s: s["name"])]
    json.dump(out, open(OUT, "w"), indent=1)
    print("wrote", OUT, len(out), "stations")


if __name__ == "__main__":
    main()
