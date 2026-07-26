#!/usr/bin/env python3
"""How far each station's dot sits from the transit line it is drawn on.

Station coordinates come from the operator/OSM node (often the entrance or the
mezzanine centre) while the overlay is the track centreline, so the two disagree
by a few metres. Measure before deciding to snap: moving a station coordinate
moves the *game* too (it is the same number the elimination engine reads), so it
is only worth doing when the gap is visible at a zoom people actually play at.

Rule of thumb: **150 ft (~45 m)** — about a platform's width, ~2 px at the app's
default zoom and ~10 px at street level. Under it, snapping is cosmetic.

    python3 scripts/audit_line_offsets.py --region dc [--threshold-ft 150]

Measurement only; nothing is written. `snap_stations_to_lines.py` does the move.
"""
import argparse
import json
import math
import os

import poi_geo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Line overlays carry colours, not names (that is all the app draws), so the
# mapping back to the names stations list lives here.
COLOR_TO_LINE = {
    "dc": {"#bf0d3e": "Red Line", "#009cde": "Blue Line", "#ed8b00": "Orange Line",
           "#00b140": "Green Line", "#ffd100": "Yellow Line", "#919d9d": "Silver Line"},
    "la": {"#0072bc": "A Line", "#e3131b": "B Line", "#58a738": "C Line",
           "#a05da5": "D Line", "#f7b618": "E Line", "#fc4c02": "G Line",
           "#adb8bf": "J Line", "#e96bb0": "K Line"},
}

M2FT = 3.28084


def parts(feat):
    g = feat["geometry"]
    return [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]


def dist_m(lat, lon, polylines):
    """Metres to the nearest point of any polyline (equirectangular, fine at
    these distances)."""
    cr = math.cos(math.radians(lat))
    px, py = lon * cr, lat
    best = float("inf")
    for part in polylines:
        for i in range(len(part) - 1):
            ax, ay = part[i][0] * cr, part[i][1]
            bx, by = part[i + 1][0] * cr, part[i + 1][1]
            dx, dy = bx - ax, by - ay
            t = 0.0 if (dx == 0 and dy == 0) else max(
                0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            d = math.hypot(px - (ax + t * dx), py - (ay + t * dy)) * 111320.0
            best = min(best, d)
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threshold-ft", type=float, default=150.0)
    region = poi_geo.add_region_arg(ap)
    args = ap.parse_args()
    region = args.region
    cfg = poi_geo.REGIONS[region]
    stations = json.load(open(os.path.join(ROOT, cfg["stations"])))
    lines = json.load(open(os.path.join(ROOT, cfg["transitLines"])))
    cmap = COLOR_TO_LINE.get(region, {})

    by_line = {}
    for f in lines["features"]:
        name = cmap.get(f["properties"]["colors"][0])
        if name is None:
            raise SystemExit(f"{region}: no line name for colour "
                             f"{f['properties']['colors'][0]} — add it to COLOR_TO_LINE")
        by_line.setdefault(name, []).extend(parts(f))
    every = [p for ps in by_line.values() for p in ps]

    rows = []
    for s in stations:
        own = [p for ln in s["lines"] for p in by_line.get(ln, [])]
        rows.append((dist_m(s["lat"], s["lon"], own or every) * M2FT,
                     dist_m(s["lat"], s["lon"], every) * M2FT, s))
    rows.sort(key=lambda r: -r[0])
    vals = sorted(r[0] for r in rows)
    n = len(vals)

    def pct(p):
        return vals[min(n - 1, int(p / 100 * n))]

    print(f"{region}: {n} stations, distance to the line(s) they serve (ft)")
    print(f"  median {pct(50):5.0f}   90th {pct(90):5.0f}   95th {pct(95):5.0f}   "
          f"max {vals[-1]:5.0f}")
    for cut in (50, 100, 150, 250, 500):
        print(f"  > {cut:3d} ft: {sum(1 for v in vals if v > cut):3d}")
    over = [r for r in rows if r[0] > args.threshold_ft]
    print(f"\npast {args.threshold_ft:.0f} ft: {len(over)}")
    for d_own, d_any, s in over:
        print(f"  {s['name']:34} own {d_own:6.0f} ft   any {d_any:6.0f} ft   "
              f"{', '.join(s['lines'])}")


if __name__ == "__main__":
    main()
