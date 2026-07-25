#!/usr/bin/env python3
"""Build the compact POI data file the app's POI tab loads.

Two inputs, one output shape — `src/data/<region>.poi.json`, keyed by category,
each a list of `{n: name, lat, lon, t: primaryType, r: userRatingCount}` with
coordinates rounded to 6 dp (category labels/colors live in `src/lib/poi.ts`):

    python3 build_poi_data.py                       # Bay Area, from poi_curated.json
    python3 build_poi_data.py --region la           # from the curated review map

`--region` is the "apply to the app" step of a city whose manual pass is done: it
reads the **review map** (`poi_merge_viz.js`), which is the authoritative record
of that pass — every delete, merge and representative swap is already applied to
it — and keeps exactly what a reviewer sees on it: group representatives and
un-grouped singles, never merged-away children (one campus = one POI, at the
representative's own pin, so "nearest hospital" can't be answered by a lab door).

The review map lives on the review branch (it is deployed as a preview site and
deliberately not merged), so from another checkout point `--viz` at it.

`--region bay` reproduces the committed Bay Area place set exactly, which is what
validates this path — but the review map carries no per-place `primaryType`, so
the Bay file is still built from its curated JSON to keep the real `t` values.
"""
import argparse
import json
import math
import os
import sys

import poi_ledger as L

HERE = os.path.dirname(os.path.abspath(__file__))

# The LA/SF Muni-style cheap pull stores no per-place `primaryType`, so a region
# built from the review map records the category's canonical Google type instead
# of inventing a specific one. Neither `t` nor `r` drives gameplay; they are kept
# for provenance and for the POI tab.
CANON_TYPE = {"consulate": "embassy", "mountain": "mountain_peak"}

# How far outside the play polygon a POI may sit and still count as in play. The
# boundary is a simplified city union, so a waterfront pier or a park on the line
# can land a few metres outside it; the discovery pass uses the same 150 m buffer.
EDGE_TOLERANCE_M = 150


def from_curated(path):
    """Legacy path: the Bay Area's curated dataset from curate_places_poi.py."""
    curated = json.load(open(path))
    return {key: [{"n": p["name"], "lat": p["lat"], "lon": p["lon"],
                   "t": p.get("primaryType"), "r": p.get("userRatingCount") or 0}
                  for p in blk["places"]]
            for key, blk in curated.items()}


def from_viz(obj):
    """A finished manual pass: the review map's visible pins, category by category."""
    out = {}
    for cat, c in obj.items():
        if not isinstance(c, dict) or "groups" not in c:
            continue
        visible = [g["rep"] for g in c["groups"]] + c["singles"]
        out[cat] = [{"n": p["n"], "lat": p["lat"], "lon": p["lon"],
                     "t": CANON_TYPE.get(cat, cat), "r": p.get("r") or 0}
                    for p in visible]
    return out


def rings_of(play):
    rings = []
    for feat in play["features"]:
        g = feat["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings += [p[0] for p in polys]
    return rings


def in_play(rings, lat, lon):
    inside = False
    for ring in rings:
        c = False
        for i in range(len(ring) - 1):
            (x1, y1), (x2, y2) = ring[i], ring[i + 1]
            if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) / (y2 - y1) * (x2 - x1):
                c = not c
        inside ^= c
    return inside or edge_distance_m(rings, lat, lon) <= EDGE_TOLERANCE_M


def edge_distance_m(rings, lat, lon):
    """Metres from (lat,lon) to the nearest play-area boundary segment."""
    best, coslat = float("inf"), math.cos(math.radians(lat))
    for ring in rings:
        for i in range(len(ring) - 1):
            (x1, y1), (x2, y2) = ring[i], ring[i + 1]
            ax, ay = (x1 - lon) * 111320 * coslat, (y1 - lat) * 111320
            bx, by = (x2 - lon) * 111320 * coslat, (y2 - lat) * 111320
            dx, dy = bx - ax, by - ay
            t = 0.0 if dx == dy == 0 else max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("curated", nargs="?", help="curated JSON (default poi_curated.json)")
    ap.add_argument("--region", choices=sorted(L.REGIONS),
                    help="build from that region's curated review map instead")
    ap.add_argument("--viz", help="review map path, if not the region's default")
    ap.add_argument("--out", help="output path, if not the region's default")
    a = ap.parse_args()

    if a.region:
        path = a.viz or L.viz_path(a.region)
        with open(path, encoding="utf-8") as f:
            out = from_viz(L.parse_viz(f.read()))
        dest = a.out or os.path.join(HERE, "..", L.REGIONS[a.region]["poi"])
        rings = rings_of(json.load(open(os.path.join(L.ROOT, L.REGIONS[a.region]["play"]))))
    else:
        out = from_curated(a.curated or os.path.join(HERE, "poi_curated.json"))
        dest = a.out or os.path.join(HERE, "..", "src", "data", "poi.json")
        rings = None

    for cat, places in out.items():
        for p in places:
            p["lat"], p["lon"] = round(p["lat"], 6), round(p["lon"], 6)
        places.sort(key=lambda x: x["n"].lower())
        # A duplicate is a de-dup failure, and out-of-play POIs make "nearest X"
        # unanswerable — fail the build rather than ship either.
        spots = [(p["n"], p["lat"], p["lon"]) for p in places]
        if len(set(spots)) != len(spots):
            dupe = next(s for s in spots if spots.count(s) > 1)
            sys.exit(f"{cat}: duplicate POI {dupe}")
        if rings:
            stray = [p for p in places if not in_play(rings, p["lat"], p["lon"])]
            if stray:
                sys.exit(f"{cat}: {len(stray)} POI outside the play area, "
                         f"e.g. {stray[0]['n']} at {stray[0]['lat']},{stray[0]['lon']}")

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    total = sum(len(v) for v in out.values())
    print(f"wrote {os.path.normpath(dest)}: {total} POIs across {len(out)} categories")
    for k, v in out.items():
        print(f"  {k:15s} {len(v)}")


if __name__ == "__main__":
    main()
