#!/usr/bin/env python3
"""Build the DC map's station list: WMATA Metrorail, from OSM.

Metrorail is the whole map. MARC, VRE and Amtrak were each audited against the
three line-inclusion gates (add-transit-city skill) and all three fail:

  * Fares: Amtrak is reservation-based, so a hider can't be assumed able to board
    the next train. MARC/VRE pass this one (walk-up, unreserved).
  * Service: VRE runs no weekend service at all; MARC Camden/Brunswick are
    weekday-only. Only MARC Penn runs seven days, and not hourly.
  * Share of stops in play: Penn 2/13, Camden 4/11, Brunswick 5/14-17,
    VRE Fredericksburg 4/9, VRE Manassas 5/10, Amtrak NE Regional 3/25 — every
    one a minority, with the rest running out to Baltimore, Martinsburg and
    Spotsylvania. All six Metrorail lines are 100% in play.

They would also have added almost nothing: 13 of the 17 non-Metro rail stops
inside the play area are within ~250 m of a Metrorail station already here, so
the only new suspects would be Backlick Road, Garrett Park, Kensington and
Riverdale — all on lines that fail the service gate.

The H Street streetcar is a different case: it has no OSM route relation and no
named stops, so it can't be built from OSM at all.

Two OSM quirks handled here:
  * Metro is tagged network="Washington Metro" (NOT "WMATA"), so a WMATA-keyed
    query silently returns nothing.
  * The four two-level transfer stations (Metro Center, Gallery Place, Fort
    Totten, L'Enfant Plaza) each carry TWO station nodes, one per level. They are
    one station, so identical names merge at any distance.

Line membership comes from the route relations' stop/platform members snapped to
the nearest station; the per-line totals are asserted against WMATA's published
counts so a bad OSM edit can't silently shrink a line.

Service (headwayMin, and the served/hourly flags behind it) is measured from
WMATA's own rail GTFS rather than assumed — same longest-gap-per-direction rule
as every other map. That feed needs a free key from https://developer.wmata.com
(any tier):

    WMATA_API_KEY=… python3 scripts/build_dc_stations.py   # -> scripts/stations.dc.json
    python3 scripts/build_attributes.py --region dc

The download is cached, so a rerun needs no key.
"""
import json
import math
import os
import time
import zipfile
from collections import defaultdict

import requests

import compute_headways
import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = poi_geo.work("dc", "raw_metro.json")
OUT = poi_geo.work("dc", "stations.json")
GTFS_ZIP = poi_geo.work("dc", "wmata_rail_gtfs.zip")
GTFS_DIR = poi_geo.work("dc", "wmata_rail_gtfs")
GTFS_URL = "https://api.wmata.com/gtfs/rail-gtfs-static.zip"
OVERPASS = "https://overpass-api.de/api/interpreter"
GTFS_SNAP_M = 500  # GTFS station pin -> OSM station pin

LINES = {"R": "Red Line", "B": "Blue Line", "O": "Orange Line",
         "S": "Silver Line", "Y": "Yellow Line", "G": "Green Line"}
# Published station counts per line (Wikipedia, current as of the 2025 service
# pattern: some Silver trains run past Largo to New Carrollton and some Yellow
# trains past Mount Vernon Square to Greenbelt, so those branches count).
EXPECTED = {"Red Line": 27, "Blue Line": 28, "Orange Line": 26,
            "Silver Line": 39, "Yellow Line": 22, "Green Line": 21}
SNAP_M = 400  # stop node -> station node; platforms sit a block from the pin

# OSM spells stations out in full; WMATA's own signage, maps and announcements
# abbreviate, and the game is played off the signs. Keyed by the OSM name.
NAME_OVERRIDES = {
    "Addison Road": "Addison Rd",
    "Benning Road": "Benning Rd",
    "Braddock Road": "Braddock Rd",
    "Branch Avenue": "Branch Av",
    "College Park\u2013University of Maryland": "College Park\u2013U of Md",
    "Dunn Loring\u2013Merrifield": "Dunn Loring",
    "Eisenhower Avenue": "Eisenhower Av",
    "Federal Center Southwest": "Federal Center SW",
    "Georgia Avenue\u2013Petworth": "Georgia Av\u2013Petworth",
    "Judiciary Square": "Judiciary Sq",
    "King Street\u2013Old Town": "King St\u2013Old Town",
    "McPherson Square": "McPherson Sq",
    "Minnesota Avenue": "Minnesota Av",
    "Morgan Boulevard": "Morgan Blvd",
    "Mount Vernon Square": "Mount Vernon Sq",
    "Naylor Road": "Naylor Rd",
    "Potomac Avenue": "Potomac Av",
    "Rhode Island Avenue\u2013Brentwood": "Rhode Island Av",
    "Shaw\u2013Howard University": "Shaw\u2013Howard U",
    "Southern Avenue": "Southern Av",
    "U Street": "U St",
    "Van Dorn Street": "Van Dorn St",
    "Vienna/Fairfax\u2013GMU": "Vienna",
    "West Falls Church\u2013VT": "West Falls Church",
}

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


def gtfs_dir():
    """Unzipped WMATA rail GTFS, downloading it once. The API key is only needed
    for that first download."""
    if not os.path.isdir(GTFS_DIR):
        if not os.path.exists(GTFS_ZIP):
            key = os.environ.get("WMATA_API_KEY")
            if not key:
                raise SystemExit(
                    "set WMATA_API_KEY (free at https://developer.wmata.com) to "
                    f"download {GTFS_URL}")
            r = requests.get(GTFS_URL, headers={"api_key": key}, timeout=180)
            r.raise_for_status()
            open(GTFS_ZIP, "wb").write(r.content)
        zipfile.ZipFile(GTFS_ZIP).extractall(GTFS_DIR)
    return GTFS_DIR


def service_by_station(stations):
    """Attach GTFS service to each station: headwayMin plus the served/hourly
    flags derived from it. GTFS stations are matched to the OSM pins by position.

    The four two-level transfer stations appear as two GTFS stations (one per
    level); a hider standing there is reachable by whichever level runs more
    often, so the merged station takes the BEST (smallest) headway of the two.
    """
    d = gtfs_dir()
    hw = compute_headways.gtfs_headways(d)
    pos = {s["stop_id"]: (float(s["stop_lat"]), float(s["stop_lon"]), s["stop_name"])
           for s in compute_headways._read_csv(os.path.join(d, "stops.txt"))}
    best = {}
    unmatched = []
    for sid, rec in hw.items():
        if sid not in pos:
            continue
        lat, lon, name = pos[sid]
        nearest = min(stations, key=lambda s: hav((lat, lon), (s["lat"], s["lon"])))
        if hav((lat, lon), (nearest["lat"], nearest["lon"])) > GTFS_SNAP_M:
            unmatched.append(name)
            continue
        cur = best.get(nearest["name"])
        best[nearest["name"]] = rec if cur is None else {
            day: min(cur[day], rec[day]) for day in ("wd", "we")}
    if unmatched:
        raise SystemExit(f"GTFS stations that matched no OSM station: {unmatched}")
    missing = [s["name"] for s in stations if s["name"] not in best]
    if missing:
        raise SystemExit(f"stations with no GTFS service: {missing}")
    return best


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
        name = NAME_OVERRIDES.get(t["name"], t["name"])
        st = by_name.setdefault(name, {"name": name, "lat": 0.0, "lon": 0.0,
                                       "n": 0, "lines": set()})
        st["lat"] += e["lat"]
        st["lon"] += e["lon"]
        st["n"] += 1
    for st in by_name.values():
        st["lat"] /= st["n"]
        st["lon"] /= st["n"]
    print("stations:", len(by_name))
    stale = [n for n in NAME_OVERRIDES if n not in {
        e.get("tags", {}).get("name") for e in nodes.values()}]
    if stale:
        raise SystemExit(f"NAME_OVERRIDES no longer match OSM: {stale}")

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

    hw = service_by_station(stations)
    worst = max(max(v["wd"], v["we"]) for v in hw.values())
    print(f"headways: worst station gap {worst:.0f} min "
          f"(threshold {compute_headways.THRESHOLD_MIN})")

    out = []
    for s in sorted(stations, key=lambda s: s["name"]):
        h = hw[s["name"]]
        out.append({
            "name": s["name"], "lat": round(s["lat"], 6), "lon": round(s["lon"], 6),
            "systems": ["Metrorail"], "lines": sorted(s["lines"]),
            # no alternate names: Metrorail stations have one name each, and the
            # OSM `railway:ref` codes (N02, D10) are internal platform IDs
            "aka": [],
            "service": {day: {"served": h[day] < 999,
                              "hourly": h[day] <= compute_headways.THRESHOLD_MIN}
                        for day in ("wd", "we")},
            "headwayMin": {day: round(h[day]) for day in ("wd", "we")},
        })
    json.dump(out, open(OUT, "w"), indent=1)
    print("wrote", OUT, len(out), "stations")


if __name__ == "__main__":
    main()
