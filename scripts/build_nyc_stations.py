#!/usr/bin/env python3
"""Build the NYC map's station list from the agencies' own data.

Systems in play (each passed the three line gates; see the NYC build plan):
  * Subway + Staten Island Railway: every MTA station complex.
  * LIRR: the six branches with a majority of stops in the five boroughs
    (Port Washington, Far Rockaway, Long Beach, West Hempstead, Hempstead,
    City Terminal Zone). The other branches fail the stops-in-play gate.
  * NYC Ferry: weekdays only. A landing is a hiding station on a weekday when it
    passes the hourly test over the shortened 07:30-21:15 weekday game day; on
    weekends no NYC Ferry landing counts (headwayMin.we = 999).
  * Staten Island Ferry (24/7) and the Roosevelt Island Tram.
PATH, Metro-North and New Jersey are out.

Station identity is the MTA `complex_id`, never the name: NYC has six different
"86 St" stations, so build_stations.py's merge-identical-names rule would
collapse them. A complex is one station (Times Sq and Port Authority are one,
joined by a free in-system transfer) and keeps one sign name; services go into
`lines`, not the name.

Other systems join a subway complex when their stop is within MERGE_M of it
(adding only a line label), else they become a station of their own.

A line is a service letter or number. Express variants fold into the base
service (6X -> 6, 7X -> 7, FX -> F); the three "S" shuttles are separate lines.

Sources (cached under scripts/_gtfs_nyc/, re-downloaded when missing):
  MTA subway GTFS (includes SIR), LIRR GTFS, NYC Ferry GTFS, and the MTA
  "Subway Stations" list on data.ny.gov (39hk-dx4f) for complex_id.

    python3 scripts/build_nyc_stations.py
then build_attributes.py --region nyc as for every map.
"""
import csv
import io
import json
import math
import os
import re
import urllib.request
import zipfile
from collections import defaultdict

from shapely.geometry import Point, shape
from shapely.ops import unary_union

import compute_headways
import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_gtfs_nyc")
OUT = poi_geo.work("nyc", "stations.json")
BOROUGHS = os.path.join(HERE, "measure_src", "nyc_boroughs.geojson")

FEEDS = {
    "gtfs_subway": "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip",
    "gtfslirr": "https://rrgtfsfeeds.s3.amazonaws.com/gtfslirr.zip",
    "nycferry": "https://nycferry.connexionz.net/rtt/public/utility/gtfs.aspx",
}
MTA_STATIONS_URL = "https://data.ny.gov/resource/39hk-dx4f.json?$limit=1000"

# Weekday game day ends at 21:15 on this map (the ferry decision); weekends keep
# the usual 22:00. Applied to every system so one window governs the map.
END_SEC = {"wd": 21 * 3600 + 15 * 60, "we": compute_headways.GAME_END_SEC}
START_SEC = compute_headways.GAME_START_SEC
THRESHOLD = compute_headways.THRESHOLD_MIN
MERGE_M = 250
IN_CITY_TOL_M = 100

SUBWAY_LINE = {"FX": "F", "6X": "6", "7X": "7", "GS": "42 St Shuttle",
               "FS": "Franklin Av Shuttle", "H": "Rockaway Park Shuttle",
               "SI": "SIR"}
LIRR_BRANCHES = {"2": "Hempstead Branch", "6": "Long Beach Branch",
                 "7": "Far Rockaway Branch", "8": "West Hempstead Branch",
                 "9": "Port Washington Branch", "12": "City Terminal Zone"}
SI_FERRY = [("Whitehall Terminal", 40.701403, -74.013189),
            ("St. George Terminal", 40.643708, -74.072961)]
# Roosevelt Island Operating Corp: 6 AM-2 AM daily, every 7-15 min (peak/off).
TRAM = [("Tramway Plaza", 40.761353, -73.964149),
        ("Roosevelt Island Tram", 40.757083, -73.953968)]
TRAM_HEADWAY = 15

# Complexes whose stations carry different sign names, keyed by MTA complex_id:
# the name Google Maps and the station signs lead with; the others become `aka`.
COMPLEX_NAME = {
    "601": "14 St", "605": "168 St", "606": "Court Sq", "609": "42 St-Bryant Pk",
    "611": "Times Sq-42 St", "612": "Lexington Av/53 St", "613": "Lexington Av/59 St",
    "615": "New Utrecht Av", "616": "Jackson Hts-Roosevelt Av",
    "618": "14 St", "619": "Broadway-Lafayette St", "620": "Borough Hall",
    "622": "Brooklyn Bridge-City Hall", "624": "World Trade Center",
    "626": "Franklin Av-Medgar Evers College", "629": "Lorimer St",
    "635": "South Ferry",
}
# Stops that are the same station as a subway complex but sit past MERGE_M from
# its pins: Grand Central Madison is under Grand Central Terminal, and the LIRR
# Nostrand Av platform is directly above the A/C at Atlantic & Nostrand.
MERGE_INTO = {("LIRR", "Grand Central"): "Grand Central-42 St",
              ("LIRR", "Nostrand Avenue"): "Nostrand Av"}


def short_name(name):
    """Agency names in sign form (St, Av), as on every other map."""
    for long, short in (("Street", "St"), ("Avenue", "Av"), ("Ave", "Av"), ("St.", "St")):
        name = re.sub(rf"\b{re.escape(long)}(?=\W|$)", short, name)
    return name


# Long-term planned work that the static GTFS bakes into every day of the feed,
# keyed by the affected stop -> a neighbouring stop on the same service that
# runs normally. MTA alert "In Queens, Flushing-bound [7] skips 52 St and 69 St"
# runs May 2026 - Sep 2027; outside it both stations have 7 local service both
# ways, so they take 61 St-Woodside's headway instead of failing the
# both-directions rule on a construction diversion. Drop an entry once the feed
# no longer carries the diversion.
PLANNED_WORK_HEADWAY = {"711": "712", "713": "712"}


def hav(a, b):
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def feed(name):
    d = os.path.join(SRC, name)
    if not os.path.isdir(d):
        os.makedirs(SRC, exist_ok=True)
        req = urllib.request.Request(FEEDS[name], headers={"User-Agent": "jetlagapp-build"})
        with urllib.request.urlopen(req, timeout=300) as r:
            zipfile.ZipFile(io.BytesIO(r.read())).extractall(d)
    return d


def mta_stations():
    p = os.path.join(SRC, "mta_stations.json")
    if not os.path.exists(p):
        with urllib.request.urlopen(MTA_STATIONS_URL, timeout=120) as r:
            open(p, "wb").write(r.read())
    return json.load(open(p))


def rows(d, f):
    with open(os.path.join(d, f), encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def routes_by_stop(d, route_ok=lambda r: True):
    """{parent stop: {'wd': {route_id}, 'we': {route_id}}} for trips departing it
    inside each day type's game window on a representative weekday/Saturday."""
    dates = compute_headways.representative_dates(d)
    running = compute_headways._dates_with_services(d)
    svc_day = defaultdict(set)
    for day, date in dates.items():
        for s in running[date]:
            svc_day[s].add(day)
    routes = {r["route_id"]: r for r in rows(d, "routes.txt")}
    trips = {t["trip_id"]: t for t in rows(d, "trips.txt")
             if svc_day.get(t["service_id"]) and route_ok(routes[t["route_id"]])}
    parent = compute_headways._parent_of(d)
    out = defaultdict(lambda: {"wd": set(), "we": set()})
    for r in rows(d, "stop_times.txt"):
        t = trips.get(r["trip_id"])
        if not t:
            continue
        sec = compute_headways._to_sec(r["departure_time"] or r["arrival_time"])
        for day in svc_day[t["service_id"]]:
            if START_SEC <= sec <= END_SEC[day]:
                out[parent.get(r["stop_id"], r["stop_id"])][day].add(t["route_id"])
    return out


def headways(d):
    return compute_headways.gtfs_headways(d, by_date=True, end_sec=END_SEC)


def main():
    city = unary_union([shape(f["geometry"]) for f in json.load(open(BOROUGHS))["features"]])
    city_tol = city.buffer(IN_CITY_TOL_M / 111000)

    # --- subway + SIR, one station per complex ---
    sub = feed("gtfs_subway")
    sub_routes = routes_by_stop(sub)
    sub_hw = headways(sub)
    for sid, twin in PLANNED_WORK_HEADWAY.items():
        sub_hw[sid] = dict(sub_hw[twin])
    complexes = defaultdict(list)
    for r in mta_stations():
        complexes[r["complex_id"]].append(r)
    stations = []
    for cid, members in sorted(complexes.items(), key=lambda kv: int(kv[0])):
        names = [m["stop_name"] for m in members]
        if len(set(names)) > 1 and cid not in COMPLEX_NAME:
            raise SystemExit(f"complex {cid} has several names {sorted(set(names))}: add it to COMPLEX_NAME")
        top = COMPLEX_NAME.get(cid, names[0])
        lines = {"wd": set(), "we": set()}
        hw = {"wd": 999.0, "we": 999.0}
        for m in members:
            sid = m["gtfs_stop_id"]
            for day in ("wd", "we"):
                lines[day] |= {SUBWAY_LINE.get(x, x) for x in sub_routes[sid][day]}
                hw[day] = min(hw[day], sub_hw.get(sid, {}).get(day, 999.0))
        systems = ["SIR"] if all(m["line"] == "Staten Island" for m in members) else ["Subway"]
        stations.append({
            "name": top,
            "lat": sum(float(m["gtfs_latitude"]) for m in members) / len(members),
            "lon": sum(float(m["gtfs_longitude"]) for m in members) / len(members),
            "systems": systems, "linesDay": lines, "hw": hw,
            "aka": sorted(set(names) - {top}),
            "pts": [(float(m["gtfs_latitude"]), float(m["gtfs_longitude"])) for m in members],
        })
    print("subway/SIR complexes:", len(stations))

    def dist(s, lat, lon):
        return min(hav((lat, lon), p) for p in s["pts"])

    def nearest(lat, lon):
        best = min(stations, key=lambda s: dist(s, lat, lon))
        return best, dist(best, lat, lon)

    def attach(name, lat, lon, system, lines, hw, new_ok=True):
        name = short_name(name)
        st, d = nearest(lat, lon)
        forced = MERGE_INTO.get((system, name)) or MERGE_INTO.get((system, name.replace(" Av", " Avenue")))
        if forced:
            st = next(s for s in stations if s["name"] == forced)
            d = 0.0
        if d <= MERGE_M:
            if system not in st["systems"]:
                st["systems"].append(system)
            for day in ("wd", "we"):
                st["linesDay"][day] |= lines[day]
                st["hw"][day] = min(st["hw"][day], hw[day])
            return f"merged into {st['name']} ({d:.0f} m)"
        if not new_ok:
            return f"dropped (not hourly, {d:.0f} m from {st['name']})"
        stations.append({"name": name, "lat": lat, "lon": lon, "systems": [system],
                         "linesDay": lines, "hw": dict(hw), "aka": [], "pts": [(lat, lon)]})
        return f"new station ({d:.0f} m from {st['name']})"

    # --- LIRR: in-city stops of the six passing branches ---
    lirr = feed("gtfslirr")
    lirr_routes = routes_by_stop(lirr)
    lirr_hw = headways(lirr)
    for s in rows(lirr, "stops.txt"):
        lat, lon = float(s["stop_lat"]), float(s["stop_lon"])
        if not city_tol.contains(Point(lon, lat)):
            continue
        rs = lirr_routes.get(s["stop_id"], {"wd": set(), "we": set()})
        lines = {day: {LIRR_BRANCHES[r] for r in rs[day] if r in LIRR_BRANCHES} for day in rs}
        if not (lines["wd"] or lines["we"]):
            print(f"  LIRR {s['stop_name']}: no passing branch, skipped")
            continue
        hw = lirr_hw.get(s["stop_id"], {"wd": 999.0, "we": 999.0})
        # A new station must be hourly every day (the service gate); a stop next
        # to a subway complex only adds its branch label there.
        hourly = max(hw.values()) <= THRESHOLD
        print(f"  LIRR {s['stop_name']} wd={hw['wd']:.0f} we={hw['we']:.0f}:",
              attach(s["stop_name"], lat, lon, "LIRR", lines, hw, new_ok=hourly))

    # --- NYC Ferry: weekday-only landings ---
    fer = feed("nycferry")
    fer_routes_meta = {r["route_id"]: r for r in rows(fer, "routes.txt")}
    fer_routes = routes_by_stop(fer, lambda r: r["route_type"] == "4")
    fer_hw = headways(fer)
    for s in rows(fer, "stops.txt"):
        rs = fer_routes.get(s["stop_id"])
        if not rs or not rs["wd"]:
            continue
        lat, lon = float(s["stop_lat"]), float(s["stop_lon"])
        if not city_tol.contains(Point(lon, lat)):
            continue
        wd = fer_hw.get(s["stop_id"], {}).get("wd", 999.0)
        lines = {"wd": {"NYC Ferry " + fer_routes_meta[r]["route_long_name"] for r in rs["wd"]},
                 "we": set()}
        hw = {"wd": wd, "we": 999.0}
        print(f"  Ferry {s['stop_name']} wd={wd:.0f}:",
              attach(s["stop_name"], lat, lon, "NYC Ferry", lines, hw, new_ok=wd <= THRESHOLD))

    # --- Staten Island Ferry + Roosevelt Island Tram ---
    for name, lat, lon in SI_FERRY:
        print(f"  {name}:", attach(name, lat, lon, "Staten Island Ferry",
                                   {"wd": {"Staten Island Ferry"}, "we": {"Staten Island Ferry"}},
                                   {"wd": 30.0, "we": 30.0}))
    for name, lat, lon in TRAM:
        print(f"  {name}:", attach(name, lat, lon, "Roosevelt Island Tram",
                                   {"wd": {"Roosevelt Island Tram"}, "we": {"Roosevelt Island Tram"}},
                                   {"wd": TRAM_HEADWAY, "we": TRAM_HEADWAY}))

    out = []
    for s in sorted(stations, key=lambda s: (s["name"], s["lat"])):
        lines = s["linesDay"]["wd"] | s["linesDay"]["we"]
        if not lines:
            raise SystemExit(f"station with no line in the game window: {s['name']}")
        out.append({
            "name": s["name"], "lat": round(s["lat"], 6), "lon": round(s["lon"], 6),
            "systems": s["systems"], "lines": sorted(lines), "aka": s["aka"],
            "service": {day: {"served": s["hw"][day] < 999,
                              "hourly": s["hw"][day] <= THRESHOLD} for day in ("wd", "we")},
            "headwayMin": {day: round(s["hw"][day]) for day in ("wd", "we")},
        })
    names = defaultdict(int)
    for s in out:
        names[s["name"]] += 1
    print("stations:", len(out), "| shared names:",
          sum(1 for v in names.values() if v > 1),
          "| weekday-eligible:", sum(s["headwayMin"]["wd"] <= THRESHOLD for s in out),
          "| weekend-eligible:", sum(s["headwayMin"]["we"] <= THRESHOLD for s in out))
    weekend_lines = {l for s in stations for l in s["linesDay"]["we"]}
    print("weekday-only lines:", sorted({l for s in out for l in s["lines"]} - weekend_lines))
    json.dump(out, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
