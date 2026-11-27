#!/usr/bin/env python3
"""Extract OSM main-line railway track around NYC for build_nyc_transit_lines.py.

The LIRR's GTFS shapes have a point every ~60 m and cut corners; OSM traces the
track at ~30 m. Overpass is often unreachable from the build VM, so this reads
Geofabrik's New York extract and writes the railway=rail ways (no service=yard/
siding/spur/crossover) as arcs split at every junction node. It also writes the
NYC Ferry / Staten Island Ferry route relations and the Roosevelt Island Tram
cable car, whose OSM geometry is more detailed than GTFS / a straight line:

    curl -LO https://download.geofabrik.de/north-america/us/new-york-latest.osm.pbf
    pip install osmium
    python3 scripts/extract_osm_rail_nyc.py new-york-latest.osm.pbf
"""
import json
import os
import sys
from collections import Counter

import osmium

OUT = os.path.join(os.path.dirname(__file__), "measure_src", "osm_rail_nyc.geojson")
WATER_OUT = os.path.join(os.path.dirname(__file__), "measure_src", "osm_ferry_tram_nyc.geojson")
BBOX = (-74.05, 40.54, -73.68, 40.82)
# Ferry route relations whose geometry build_nyc_transit_lines.py may use
# (NYC Ferry is run by Hornblower; NYCDOT runs the Staten Island Ferry).
FERRY_OPERATORS = ("Hornblower Cruises", "NYCDOT")


class Rail(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways = []
        self.ferry_ways = {}
        self.water = []

    def way(self, w):
        if w.tags.get("route") == "ferry" or w.tags.get("aerialway") == "cable_car":
            try:
                coords = [[round(n.lon, 6), round(n.lat, 6)] for n in w.nodes]
            except osmium.InvalidLocationError:
                return
            self.ferry_ways[w.id] = coords
            if w.tags.get("aerialway") == "cable_car" and w.tags.get("name"):
                self.water.append({"type": "Feature",
                                   "properties": {"kind": "aerialway", "name": w.tags["name"]},
                                   "geometry": {"type": "LineString", "coordinates": coords}})
        if w.tags.get("railway") != "rail" or w.tags.get("service"):
            return
        try:
            nodes = [(n.ref, round(n.lon, 6), round(n.lat, 6)) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if any(BBOX[0] < x < BBOX[2] and BBOX[1] < y < BBOX[3] for _, x, y in nodes):
            self.ways.append((w.id, nodes))

    def relation(self, r):
        if r.tags.get("route") != "ferry" or r.tags.get("operator") not in FERRY_OPERATORS:
            return
        lines = [self.ferry_ways[m.ref] for m in r.members if m.type == "w" and m.ref in self.ferry_ways]
        if lines:
            self.water.append({"type": "Feature",
                               "properties": {"kind": "ferry", "relation": r.id,
                                              "name": r.tags.get("name", ""), "ref": r.tags.get("ref", ""),
                                              "operator": r.tags["operator"]},
                               "geometry": {"type": "MultiLineString", "coordinates": lines}})


def main(pbf):
    h = Rail()
    h.apply_file(pbf, locations=True, idx="flex_mem")
    uses = Counter(ref for _, nodes in h.ways for ref, _, _ in nodes)
    feats = []
    for wid, nodes in h.ways:
        cur = [nodes[0]]
        for n in nodes[1:]:
            cur.append(n)
            if uses[n[0]] > 1 or n is nodes[-1]:
                feats.append({"type": "Feature", "properties": {"way": wid},
                              "geometry": {"type": "LineString",
                                           "coordinates": [[x, y] for _, x, y in cur]}})
                cur = [n]
    json.dump({"type": "FeatureCollection", "features": feats}, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(feats)} arcs from {len(h.ways)} ways")
    json.dump({"type": "FeatureCollection", "features": h.water}, open(WATER_OUT, "w"), separators=(",", ":"))
    print(f"wrote {WATER_OUT}: {len(h.water)} ferry routes and aerialways")


if __name__ == "__main__":
    main(sys.argv[1])
