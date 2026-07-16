#!/usr/bin/env python3
"""Fetch LA Metro Rail + Busway line geometry from OSM Overpass and emit the
`la.transit-lines.geojson.json` overlay (one continuous LineString feature per
line, colored by the line's official OSM `colour`).

Reuses the region-agnostic stitching/bridging/branch-building machinery from
`fetch_transit_lines.py` (the continuous-transit-lines algorithm) — only the
source selection (LA Metro rail + BRT), the metres-per-degree reference latitude
and the per-line colors are LA-specific.
"""
import json
import math
import sys
import time
import urllib.parse
import urllib.request

import fetch_transit_lines as base

OVERPASS = "https://overpass-api.de/api/interpreter"
FALLBACK_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
BBOX = "33.6,-118.9,34.4,-117.5"

# Metro Rail (A/B/C/D/E/K) is route=subway|light_rail; Metro Busway (G/J) is a
# BRT tagged route=bus. Restrict to LA Metro (LACMTA) so we don't pull the
# hundreds of local bus routes in the same bbox.
QUERY = f"""
[out:json][timeout:240];
(
  relation["route"~"subway|light_rail|tram"]["network"~"Metro|LACMTA",i]({BBOX});
  relation["route"="bus"]["ref"~"^[GJ]$"]["network"~"Metro|LACMTA",i]({BBOX});
);
out geom;
"""

# The 8 lines we draw and their official OSM colours (verified against the
# route relations' `colour` tags).
LINE_REFS = {"A", "B", "C", "D", "E", "K", "G", "J"}
LINE_COLOR = {
    "A": "#0072bc",  # Blue  (Azusa – Long Beach)
    "B": "#e3131b",  # Red   (North Hollywood – Union Station)
    "C": "#58a738",  # Green (Redondo Beach – Norwalk)
    "D": "#a05da5",  # Purple(Wilshire/Western – Union Station)
    "E": "#f7b618",  # Gold  (Santa Monica – East LA)
    "K": "#e96bb0",  # Pink  (Expo/Crenshaw – Westchester/Veterans)
    "G": "#fc4c02",  # Orange BRT (Chatsworth – North Hollywood)
    "J": "#adb8bf",  # Silver BRT (El Monte – San Pedro / Harbor Gateway)
}
SYSTEM = "Metro"

# LA reference latitude for the metres-per-degree conversion used by the shared
# stitching helpers. Override the Bay-Area constants in the imported module.
base._MX = 111320.0 * math.cos(math.radians(34.05))
base._MY = 110540.0


def fetch():
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    for ep in FALLBACK_ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    ep, data=data, headers={"User-Agent": "la-hideandseek/1.0 (transit-overlay)"}
                )
                with urllib.request.urlopen(req, timeout=260) as r:
                    print(f"  overpass ok: {ep}", file=sys.stderr)
                    return json.load(r)
            except Exception as e:  # noqa: BLE001
                print(f"  {ep} attempt {attempt+1} failed: {e}", file=sys.stderr)
                time.sleep(6)
    raise SystemExit("Overpass fetch failed on all endpoints")


def rel_ways(el):
    out = []
    for m in el.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        geom = [[p["lon"], p["lat"]] for p in m["geometry"]]
        if len(geom) >= 2:
            out.append(geom)
    return out


def main():
    raw = fetch()
    # Group route relations by line ref (each line has one relation per
    # direction plus service variants).
    by_ref = {}
    for el in raw.get("elements", []):
        if el.get("type") != "relation":
            continue
        ref = el.get("tags", {}).get("ref", "")
        if ref in LINE_REFS:
            by_ref.setdefault(ref, []).append(rel_ways(el))

    missing = LINE_REFS - set(by_ref)
    if missing:
        print(f"  WARNING: no relations for {sorted(missing)}", file=sys.stderr)

    feats = []
    for ref in sorted(by_ref):
        built = base.build_line(by_ref[ref])
        color = LINE_COLOR[ref]
        kept = [c for c in built if base.chain_len_m(c) >= base.STRAY_MIN_M]
        for chain in kept:
            feats.append({
                "type": "Feature",
                "properties": {"system": SYSTEM, "colors": [color]},
                "geometry": {"type": "LineString", "coordinates": base.round_coords(chain)},
            })
        print(f"  {ref} Line: {len(kept)} chain(s), "
              f"{sum(base.chain_len_m(c) for c in kept)/1609.34:.1f} mi", file=sys.stderr)

    # Explicit downtown loops that build_line() cannot recover from OSM:
    #   A Line (Long Beach): OSM carries the northbound Pacific Ave leg only in the
    #     opposite-direction relation, which build_line() discards as a near-total
    #     duplicate of the mainline (its _covered check), taking the unique loop leg
    #     with it.
    #   J Line (San Pedro): the stitched mainline starts mid-block on Pacific Ave
    #     and runs Pacific->22nd->Gaffey->19th->north, so the loop's east side
    #     (Pacific Ave between 22nd and 19th) is never drawn.
    # Add each saved alignment as its own feature (same pattern as the Bay Area OAK
    # connector); endpoints meet the mainline so each renders as a closed loop.
    for fname, ref in (("scripts/la_a_loop.json", "A"), ("scripts/la_j_loop.json", "J")):
        try:
            with open(fname) as f:
                loop = json.load(f)
        except FileNotFoundError:
            continue
        if len(loop) >= 2:
            feats.append({
                "type": "Feature",
                "properties": {"system": SYSTEM, "colors": [LINE_COLOR[ref]]},
                "geometry": {"type": "LineString", "coordinates": base.round_coords(loop)},
            })

    out = {"type": "FeatureCollection", "features": feats}
    path = "src/data/la.transit-lines.geojson.json"
    with open(path, "w") as f:
        json.dump(out, f)
    print(f"features: {len(feats)} -> {path}")


if __name__ == "__main__":
    main()
