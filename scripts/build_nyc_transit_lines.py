#!/usr/bin/env python3
"""Build the NYC map's transit-line overlay from the agencies' GTFS shapes.

One feature per colour on the official MTA map: subway services that share a
trunk share a colour (A/C/E are all 8 Av blue), so they are one feature, named
for the trunk ("8 Av: A C E"). The three shuttles share shuttle grey. Each LIRR
branch in play, each NYC Ferry route, SIR, the Staten Island Ferry and the
Roosevelt Island Tram are their own features. LIRR geometry is clipped to the
city (plus CLIP_M, so the line visibly leaves the map); boats are not clipped.

    python3 scripts/build_nyc_transit_lines.py   # after build_nyc_stations.py
"""
import csv
import json
import os

from shapely.geometry import LineString, mapping, shape
from shapely.ops import linemerge, unary_union

import build_nyc_stations as st
import poi_geo

OUT = poi_geo.repo_path("nyc", "transitLines")
CLIP_DEG = 0.015
SIMPLIFY_DEG = 0.00008  # ~8 m

# MTA's published trunk colours.
SUBWAY_TRUNKS = [
    ("8 Av: A C E", "#0039a6", ["A", "C", "E"]),
    ("6 Av: B D F M", "#ff6319", ["B", "D", "F", "FX", "M"]),
    ("Crosstown: G", "#6cbe45", ["G"]),
    ("Nassau St: J Z", "#996633", ["J", "Z"]),
    ("14 St-Canarsie: L", "#a7a9ac", ["L"]),
    ("Broadway: N Q R W", "#fccc0a", ["N", "Q", "R", "W"]),
    ("Shuttles: S", "#808183", ["GS", "FS", "H"]),
    ("Broadway-7 Av: 1 2 3", "#ee352e", ["1", "2", "3"]),
    ("Lexington Av: 4 5 6", "#00933c", ["4", "5", "6", "6X"]),
    ("Flushing: 7", "#b933ad", ["7", "7X"]),
]
SIR = ("Staten Island Railway", "#1d2f6f", ["SI"])


def rows(d, f):
    with open(os.path.join(d, f), encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def route_shapes(d):
    """route_id -> [LineString] of every distinct shape its trips run."""
    sids = {}
    for t in rows(d, "trips.txt"):
        if t.get("shape_id"):
            sids.setdefault(t["route_id"], set()).add(t["shape_id"])
    pts = {}
    for r in rows(d, "shapes.txt"):
        pts.setdefault(r["shape_id"], []).append(
            (int(r["shape_pt_sequence"]), float(r["shape_pt_lon"]), float(r["shape_pt_lat"])))
    lines = {sid: LineString([(x, y) for _, x, y in sorted(v)]) for sid, v in pts.items() if len(v) > 1}
    return {rid: [lines[s] for s in ss if s in lines] for rid, ss in sids.items()}


def feature(system, color, name, lines, clip=None):
    g = unary_union(lines)
    if clip is not None:
        g = g.intersection(clip)
    g = linemerge(g) if g.geom_type == "MultiLineString" else g
    g = g.simplify(SIMPLIFY_DEG)
    geom = mapping(g)
    geom["coordinates"] = json.loads(json.dumps(geom["coordinates"]),
                                     parse_float=lambda v: round(float(v), 6))
    return {"type": "Feature", "properties": {"system": system, "colors": [color], "name": name},
            "geometry": geom}


def main():
    city = unary_union([shape(f["geometry"]) for f in json.load(open(st.BOROUGHS))["features"]])
    clip = city.buffer(CLIP_DEG)
    feats = []
    sub = route_shapes(st.feed("gtfs_subway"))
    for name, color, routes in SUBWAY_TRUNKS:
        feats.append(feature("Subway", color, name, [l for r in routes for l in sub.get(r, [])]))
    feats.append(feature("SIR", SIR[1], SIR[0], [l for r in SIR[2] for l in sub[r]]))

    lirr = st.feed("gtfslirr")
    lirr_meta = {r["route_id"]: r for r in rows(lirr, "routes.txt")}
    lirr_sh = route_shapes(lirr)
    for rid, name in st.LIRR_BRANCHES.items():
        feats.append(feature("LIRR", "#" + lirr_meta[rid]["route_color"].lower(), name,
                             lirr_sh[rid], clip))

    fer = st.feed("nycferry")
    stations = json.load(open(st.OUT))
    ferry_lines = {l for s in stations for l in s["lines"] if l.startswith("NYC Ferry ")}
    fer_sh = route_shapes(fer)
    for r in rows(fer, "routes.txt"):
        name = "NYC Ferry " + r["route_long_name"]
        if r["route_type"] == "4" and name in ferry_lines:
            feats.append(feature("NYC Ferry", "#" + r["route_color"].lower(), name, fer_sh[r["route_id"]]))

    (_, la, lo), (_, lb, lob) = st.SI_FERRY
    feats.append(feature("Staten Island Ferry", "#f58220", "Staten Island Ferry",
                         [LineString([(lo, la), (lob, lb)])]))
    (_, la, lo), (_, lb, lob) = st.TRAM
    feats.append(feature("Roosevelt Island Tram", "#c60c30", "Roosevelt Island Tram",
                         [LineString([(lo, la), (lob, lb)])]))
    json.dump({"type": "FeatureCollection", "features": feats}, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(feats)} lines, {os.path.getsize(OUT) // 1024} KB")


if __name__ == "__main__":
    main()
