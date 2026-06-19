#!/usr/bin/env python3
"""Rebuild each station's `lines` list from authoritative OSM route relations.

For every rail route relation (BART, Muni Metro, VTA, Caltrain) we read its
ordered `stop` member nodes and assign the relation's canonical line name to any
station within MATCH_M metres of one of those stops. This is the single source of
truth for line membership, replacing hand-maintained / GTFS-derived lists that
carried artifacts (e.g. BART Yellow wrongly on Milpitas).

Notes / deliberate choices:
- BART matches both `subway` and `light_rail` routes: the Antioch/Pittsburg
  Center eBART extension is tagged `light_rail` but is branded as the Yellow line.
- The BART Silver (Coliseum-OAK) connector is an automated guideway with no rail
  route relation, so it is preserved from the existing data.
- Muni "S" (the discontinued Castro shuttle) is excluded — OSM still carries it
  but it is not a current service.
- Caltrain is split into Local / Limited / Express service patterns (the
  generic single "Caltrain" entry is replaced).
"""
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = "36.9,-122.7,38.25,-121.4"
QUERY = f"""[out:json][timeout:240];
(relation["route"~"subway|light_rail|tram|train"]({BBOX}););
out geom;"""

HERE = os.path.dirname(os.path.abspath(__file__))
STATIONS = os.path.join(HERE, "..", "src", "data", "stations.json")

MATCH_M = 170.0  # a station is "on" a line if a stop node is within this distance

BART_REF = {
    "Blue": "BART Blue (Dublin/Pleasanton–Daly City)",
    "Green": "BART Green (Berryessa–Daly City)",
    "Red": "BART Red (Richmond–Millbrae/SFO)",
    "Orange": "BART Orange (Berryessa–Richmond)",
    "Yellow": "BART Yellow (Antioch–SFO/Millbrae)",
}
SILVER = "BART Silver (Coliseum–OAK)"
MUNI_EXCLUDE_REF = {"S"}  # discontinued Castro shuttle

# Only these systems are rebuilt from OSM. Muni membership is left untouched: its
# dense, overlapping surface/subway stops make proximity unreliable and the Muni
# F/Market memberships are deliberately hand-curated (see stations.test.ts).
REBUILD_SYSTEMS = {"BART", "VTA", "Caltrain"}


def fetch():
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                OVERPASS, data=data, headers={"User-Agent": "bayarea-hideandseek/1.0"}
            )
            with urllib.request.urlopen(req, timeout=260) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            print(f"  attempt {attempt+1} failed: {e}", file=sys.stderr)
            time.sleep(5)
    raise SystemExit("Overpass fetch failed")


def system(t):
    op = (t.get("operator", "") + " " + t.get("network", "")).lower()
    name = t.get("name", "").lower()
    route = t.get("route", "")
    if route == "cable_car" or "cable car" in name or "cable_car" in name:
        return None
    if "caltrain" in op or "peninsula corridor" in op:
        return "Caltrain"
    if route in ("subway", "light_rail") and ("bart" in op or "bay area rapid" in op):
        return "BART"
    if route in ("light_rail", "tram") and ("muni" in op or "san francisco municipal" in op or "sfmta" in op):
        return "Muni"
    if route == "light_rail" and ("vta" in op or "santa clara valley" in op):
        return "VTA"
    return None


def canon_line(sysn, t):
    ref = t.get("ref", "")
    name = t.get("name", "")
    if sysn == "BART":
        return BART_REF.get(ref)
    if sysn == "Muni":
        if not ref or ref in MUNI_EXCLUDE_REF:
            return None
        return "Muni " + ref
    if sysn == "VTA":
        return "VTA " + ref if ref else None
    if sysn == "Caltrain":
        if name.startswith("Local"):
            return "Caltrain Local"
        if name.startswith("Limited"):
            return "Caltrain Limited"
        if name.startswith("Express"):
            return "Caltrain Express"
        return None  # Holiday / game-day / South County Connector specials
    return None


_MX = 111320.0 * math.cos(math.radians(37.7))
_MY = 110540.0


def dist_m(a, b):
    return math.hypot((a[1] - b[1]) * _MX, (a[0] - b[0]) * _MY)


def main():
    raw = fetch()
    line_stops = {}
    for el in raw.get("elements", []):
        if el.get("type") != "relation":
            continue
        t = el.get("tags", {})
        sysn = system(t)
        if not sysn:
            continue
        line = canon_line(sysn, t)
        if not line:
            continue
        for m in el.get("members", []):
            if m.get("type") == "node" and m.get("role", "").startswith("stop"):
                line_stops.setdefault(line, []).append((m["lat"], m["lon"]))

    stations = json.load(open(STATIONS))
    changed = 0
    for st in stations:
        if not st.get("systems"):
            continue
        p = (st["lat"], st["lon"])
        # keep existing membership for systems we don't rebuild (e.g. Muni)
        assigned = {l for l in st.get("lines", []) if l.split()[0] not in REBUILD_SYSTEMS}
        for line, stops in line_stops.items():
            lsys = line.split()[0]
            if lsys not in REBUILD_SYSTEMS or lsys not in st["systems"]:
                continue
            if any(dist_m(p, s) < MATCH_M for s in stops):
                assigned.add(line)
        if SILVER in st.get("lines", []):
            assigned.add(SILVER)
        # safety: never blank out a rebuilt system that previously had lines
        for sysn in set(st["systems"]) & REBUILD_SYSTEMS:
            if not any(l.split()[0] == sysn for l in assigned):
                kept = [l for l in st.get("lines", []) if l.split()[0] == sysn]
                if kept:
                    print(f"  WARN {st['name']}: no OSM match for {sysn}, keeping {kept}", file=sys.stderr)
                    assigned.update(kept)
        new = sorted(assigned)
        if new != st.get("lines"):
            changed += 1
        st["lines"] = new

    json.dump(stations, open(STATIONS, "w"), indent=1)
    print(f"rebuilt lines for {len(stations)} stations ({changed} changed) -> {STATIONS}")


if __name__ == "__main__":
    main()
