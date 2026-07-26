#!/usr/bin/env python3
"""Fetch WMATA Metrorail line geometry from OSM Overpass and emit the
`dc.transit-lines.geojson.json` overlay (one continuous LineString feature per
line, in WMATA's official line colors).

Reuses the region-agnostic stitching/bridging/branch-building machinery from
`fetch_transit_lines.py` (the continuous-transit-lines algorithm) — only the
source selection, the metres-per-degree reference latitude and the per-line
colors are DC-specific.

OSM tags Metrorail `network="Washington Metro"` (not "WMATA"), the same gotcha
build_dc_stations.py documents: a WMATA-keyed query returns nothing.

Run: python3 scripts/fetch_dc_transit_lines.py
"""
import json
import math
import sys
import time
import urllib.parse
import urllib.request

import fetch_transit_lines as base
import poi_geo

FALLBACK_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

QUERY = """
[out:json][timeout:240];
relation["route"="subway"]["network"="Washington Metro"];
out geom;
"""

# WMATA's official line colors (wmata.com line pages / the OSM `colour` tags).
LINE_COLOR = {
    "R": ("Red Line", "#bf0d3e"),
    "B": ("Blue Line", "#009cde"),
    "O": ("Orange Line", "#ed8b00"),
    "S": ("Silver Line", "#919d9d"),
    "Y": ("Yellow Line", "#ffd100"),
    "G": ("Green Line", "#00b140"),
}
SYSTEM = "Metrorail"
OUT = poi_geo.repo_path("dc", "transitLines")

# DC reference latitude for the metres-per-degree conversion used by the shared
# stitching helpers. Override the Bay-Area constants in the imported module.
base._MX = 111320.0 * math.cos(math.radians(38.9))
base._MY = 110540.0


def fetch():
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    for ep in FALLBACK_ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    ep, data=data,
                    headers={"User-Agent": "jetlag-dc/1.0 (transit-overlay)"})
                with urllib.request.urlopen(req, timeout=260) as r:
                    print(f"  overpass ok: {ep}", file=sys.stderr)
                    return json.load(r)
            except Exception as e:  # noqa: BLE001
                print(f"  {ep} attempt {attempt+1}: {e}", file=sys.stderr)
                time.sleep(5)
    raise SystemExit("Overpass fetch failed")


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
    by_ref = {}
    for el in raw.get("elements", []):
        if el.get("type") != "relation":
            continue
        ref = el.get("tags", {}).get("ref", "")
        if ref in LINE_COLOR:
            by_ref.setdefault(ref, []).append(rel_ways(el))

    missing = set(LINE_COLOR) - set(by_ref)
    if missing:
        raise SystemExit(f"no route relations for {sorted(missing)}")

    feats = []
    for ref in sorted(by_ref, key=lambda r: LINE_COLOR[r][0]):
        name, color = LINE_COLOR[ref]
        kept = [c for c in base.build_line(by_ref[ref])
                if base.chain_len_m(c) >= base.STRAY_MIN_M]
        for chain in kept:
            feats.append({
                "type": "Feature",
                "properties": {"system": SYSTEM, "colors": [color]},
                "geometry": {"type": "LineString",
                             "coordinates": base.round_coords(chain)},
            })
        print(f"  {name}: {len(kept)} chain(s), "
              f"{sum(base.chain_len_m(c) for c in kept)/1609.34:.1f} mi",
              file=sys.stderr)

    with open(OUT, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    print(f"wrote {OUT} — {len(feats)} features")


if __name__ == "__main__":
    main()
