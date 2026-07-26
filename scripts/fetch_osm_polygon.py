#!/usr/bin/env python3
"""Fetch one OSM area (relation or closed way) as a GeoJSON polygon.

For play-area pieces that are not Census places: an airport, a big park, a
military reservation. The result is committed so `build_play_area.py` stays
offline and reproducible.

    python3 scripts/fetch_osm_polygon.py --relation 949847 \\
        --name "Washington Dulles International Airport" \\
        --out scripts/dc_dulles_airport.geojson
"""
import argparse
import json
import time
import urllib.parse
import urllib.request

from shapely.geometry import LineString, mapping
from shapely.ops import linemerge, polygonize, unary_union

OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


def query(q):
    last = None
    for url in OVERPASS:
        try:
            req = urllib.request.Request(
                url, data=b"data=" + urllib.parse.quote(q).encode(),
                headers={"User-Agent": "jetlag-hideandseek/1.0 (play area)"})
            with urllib.request.urlopen(req, timeout=200) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  {url} failed: {e}")
            time.sleep(3)
    raise SystemExit(f"all overpass endpoints failed: {last}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--relation", type=int)
    g.add_argument("--way", type=int)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    kind, oid = ("rel", args.relation) if args.relation else ("way", args.way)
    data = query(f"[out:json][timeout:180];{kind}({oid});out geom;")
    el = data["elements"][0]
    if kind == "way":
        rings = [LineString([(p["lon"], p["lat"]) for p in el["geometry"]])]
    else:
        # An outer ring of a multipolygon relation is split across member ways,
        # so merge them before polygonizing; inner rings (holes) are ignored —
        # a play-area piece should not have out-of-play pockets punched in it.
        rings = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
                 for m in el["members"]
                 if m["type"] == "way" and m.get("role") in ("outer", "")]
    geom = unary_union(list(polygonize(linemerge(unary_union(rings)))))
    if geom.is_empty:
        raise SystemExit(f"{kind} {oid}: no closed ring")
    json.dump({"type": "Feature",
               "properties": {"name": args.name, "osm": f"{kind}/{oid}"},
               "geometry": mapping(geom)}, open(args.out, "w"))
    print(f"wrote {args.out}: {geom.geom_type}, {geom.area * 69 * 54:.1f} sq mi (approx)")


if __name__ == "__main__":
    main()
