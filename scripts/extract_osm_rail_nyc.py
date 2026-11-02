#!/usr/bin/env python3
"""Extract OSM main-line railway track around NYC for build_nyc_transit_lines.py.

The LIRR's GTFS shapes have a point every ~60 m and cut corners; OSM traces the
track at ~30 m. Overpass is often unreachable from the build VM, so this reads
Geofabrik's New York extract and writes the railway=rail ways (no service=yard/
siding/spur/crossover) as arcs split at every junction node:

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
BBOX = (-74.05, 40.54, -73.68, 40.82)


class Rail(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways = []

    def way(self, w):
        if w.tags.get("railway") != "rail" or w.tags.get("service"):
            return
        try:
            nodes = [(n.ref, round(n.lon, 6), round(n.lat, 6)) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if any(BBOX[0] < x < BBOX[2] and BBOX[1] < y < BBOX[3] for _, x, y in nodes):
            self.ways.append((w.id, nodes))


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


if __name__ == "__main__":
    main(sys.argv[1])
