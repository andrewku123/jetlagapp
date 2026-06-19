#!/usr/bin/env python3
"""Count how many stops the app has on each transit line.

Reads `src/data/stations.json` and tallies, for every line, how many stations
list it (a station counts on every line that serves it, so shared stations are
counted once per line). Lines are grouped by system in `SYSTEM_ORDER` and sorted
by descending count within each system.

Optionally cross-checks each count against the authoritative OSM route relations
(`--osm path/to/overpass.json`, the same dump `build_station_lines.py` fetches):
it counts the distinct `stop` member nodes per canonical line and flags any line
whose app count diverges from OSM by more than `--tol` (default 2). This is how
you confirm a suspicious-looking tally (e.g. several lines landing on the exact
same count) is real and not an over-/under-matching bug.

Usage:
    python scripts/count_line_stops.py
    python scripts/count_line_stops.py --osm /tmp/osm_full.json
"""
import argparse
import json
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(__file__)
STATIONS = os.path.join(HERE, "..", "src", "data", "stations.json")
SYSTEM_ORDER = ["BART", "Caltrain", "VTA", "Muni"]


def system_of(line):
    for sys in SYSTEM_ORDER:
        if line == sys or line.startswith(sys + " "):
            return sys
    return "Other"


def app_counts():
    stations = json.load(open(STATIONS))
    c = Counter()
    for st in stations:
        for line in st.get("lines", []):
            c[line] += 1
    return c, len(stations)


def osm_counts(path, match_m=170.0):
    """Physical stops per canonical line, from an Overpass relation dump.

    OSM models each line with several directional/short-turn route relations, so
    a physical station shows up as many stop nodes (one per direction, and BART's
    NB/SB nodes are >170 m apart). Counting raw nodes therefore over-counts ~2x.
    Instead we snap every stop node to its nearest app station (within `match_m`,
    the same rule `build_station_lines.py` uses) and count the **distinct
    stations** each line touches — a physical, app-comparable count. Stops with
    no station within `match_m` are ignored (yards/non-revenue/out-of-area)."""
    import sys as _sys
    _sys.path.insert(0, HERE)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "bsl", os.path.join(HERE, "build_station_lines.py")
    )
    bsl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bsl)
    stations = json.load(open(STATIONS))
    raw = json.load(open(path))
    hit = defaultdict(set)
    for el in raw.get("elements", []):
        if el.get("type") != "relation":
            continue
        sysn = bsl.system(el.get("tags", {}))
        if not sysn:
            continue
        line = bsl.canon_line(sysn, el.get("tags", {}))
        if not line:
            continue
        for m in el.get("members", []):
            if m.get("type") != "node" or not m.get("role", "").startswith("stop"):
                continue
            p = (m["lat"], m["lon"])
            best, bestd = None, match_m
            for st in stations:
                if sysn not in st["systems"]:
                    continue
                d = bsl.dist_m(p, (st["lat"], st["lon"]))
                if d < bestd:
                    best, bestd = st["id"], d
            if best is not None:
                hit[line].add(best)
    return {line: len(s) for line, s in hit.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", help="Overpass relation dump to cross-check against")
    ap.add_argument("--tol", type=int, default=2, help="allowed app-vs-OSM diff")
    args = ap.parse_args()

    counts, n = app_counts()
    osm = osm_counts(args.osm) if args.osm else None

    by_sys = defaultdict(list)
    for line, ct in counts.items():
        by_sys[system_of(line)].append((line, ct))

    flags = []
    for sys in SYSTEM_ORDER + ["Other"]:
        rows = sorted(by_sys.get(sys, []), key=lambda x: (-x[1], x[0]))
        if not rows:
            continue
        print(f"\n{sys}")
        for line, ct in rows:
            extra = ""
            if osm is not None:
                ock = osm.get(line)
                if ock is None:
                    extra = "  (no OSM line — preserved/special, e.g. Silver)"
                else:
                    diff = ct - ock
                    extra = f"  [OSM {ock}{'' if diff == 0 else f', diff {diff:+d}'}]"
                    if abs(diff) > args.tol:
                        flags.append((line, ct, ock))
            print(f"  {ct:3d}  {line}{extra}")

    print(f"\ntotal station-line memberships: {sum(counts.values())}  ({n} stations)")
    if osm is not None:
        if flags:
            print("\nFLAGS (app vs OSM diverges beyond tol):")
            for line, ct, ock in flags:
                print(f"  {line}: app {ct} vs OSM {ock}")
        else:
            print("\nAll lines within tolerance of OSM. ✓")


if __name__ == "__main__":
    main()
