#!/usr/bin/env python3
"""Build a dense bay-shore land mask (bay_land.geojson) from the OSM coastline.

The bay water in build_play_area.py is a coarse hand-traced corridor minus the
land. Where the land is only the census *place* polygons, unincorporated
shoreline (tidal flats, shoreline parks like Point Pinole, the East Bay edge)
is not subtracted, so the corridor water spills over real land. This script
pulls natural=coastline for the whole bay, polygonizes it against the bbox into
faces, classifies each face as land or water by water seeds, and unions the land
faces into one dense mask. bay_water() subtracts this so the water hugs the real
shoreline at OSM resolution everywhere (supersedes the Marin-only marin_land).

Angel Island is excluded from the mask so it stays in play (covered by the
corridor). This same dense bay-shore polygon is reusable for the future
coastline question (distance-to-coast / Bay-vs-Pacific).
"""
import json
import sys
import time
import urllib.parse
import urllib.request

from shapely.geometry import LineString, Point, Polygon, box, mapping
from shapely.ops import linemerge, polygonize, unary_union

# bbox covering the whole bay corridor + a margin past the Golden Gate (Pacific)
# and past the south-bay tip, so the coastline closes against the bbox edges.
SOUTH, WEST, NORTH, EAST = 37.40, -122.58, 37.99, -121.93

# Points known to be open water (one per distinct water body inside the bbox).
WATER_SEEDS = [
    (-122.36, 37.83),   # central bay
    (-122.33, 37.79),   # central bay (east of SF)
    (-122.20, 37.72),   # central/east bay
    (-122.13, 37.58),   # south bay
    (-122.05, 37.50),   # south bay (Alviso)
    (-121.99, 37.51),   # far south bay
    (-122.42, 37.95),   # San Pablo Bay (north of R-SR bridge)
    (-122.48, 37.90),   # San Pablo Bay / Marin side
    (-122.55, 37.78),   # Pacific, off the Golden Gate
    (-122.52, 37.55),   # Pacific, off the peninsula
]
# Angel Island: drop the land face containing this point so it stays in play.
ANGEL_ISLAND = (-122.4307, 37.8607)

OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def fetch_coastline():
    q = (
        "[out:json][timeout:180];"
        f'way["natural"="coastline"]({SOUTH},{WEST},{NORTH},{EAST});'
        "out geom;"
    )
    last = None
    for url in OVERPASS:
        for attempt in range(2):
            try:
                print(f"querying {url} (attempt {attempt+1})", file=sys.stderr)
                req = urllib.request.Request(
                    url,
                    data=b"data=" + urllib.parse.quote(q).encode(),
                    headers={"User-Agent": "jetlag-hideandseek/1.0 (bay coastline)"},
                )
                with urllib.request.urlopen(req, timeout=200) as r:
                    return json.loads(r.read())
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"  failed: {e}", file=sys.stderr)
                time.sleep(3)
    raise SystemExit(f"all overpass endpoints failed: {last}")


def main():
    data = fetch_coastline()
    lines = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        geom = el.get("geometry") or []
        pts = [(p["lon"], p["lat"]) for p in geom]
        if len(pts) >= 2:
            lines.append(LineString(pts))
    print(f"fetched {len(lines)} coastline ways", file=sys.stderr)
    if not lines:
        raise SystemExit("no coastline ways returned")

    merged = linemerge(unary_union(lines))
    bbox = box(WEST, SOUTH, EAST, NORTH)
    # Polygonize the coastline together with the bbox boundary so open coastline
    # strands close into faces against the frame.
    noded = unary_union([merged, bbox.boundary])
    faces = list(polygonize(noded))
    print(f"polygonized into {len(faces)} faces", file=sys.stderr)

    seeds = [Point(*s) for s in WATER_SEEDS]
    angel = Point(*ANGEL_ISLAND)
    land = []
    n_water = 0
    for f in faces:
        if any(f.contains(s) for s in seeds):
            n_water += 1
            continue
        if f.contains(angel):
            print("  excluded Angel Island land face (stays in play)", file=sys.stderr)
            continue
        land.append(f)
    print(f"classified {n_water} water faces, {len(land)} land faces", file=sys.stderr)

    mask = unary_union(land)
    # Clip to bbox (paranoia) and drop slivers from noding.
    mask = mask.intersection(bbox)
    if mask.geom_type == "Polygon":
        parts = [mask]
    else:
        parts = [g for g in mask.geoms if g.geom_type == "Polygon"]
    parts = [p for p in parts if p.area > 1e-8]
    mask = unary_union(parts)

    out = {"type": "Feature", "properties": {"source": "osm natural=coastline"},
           "geometry": mapping(mask)}
    with open("bay_land.geojson", "w") as fh:
        json.dump(out, fh)
    npts = sum(len(p.exterior.coords) for p in
               (mask.geoms if mask.geom_type == "MultiPolygon" else [mask]))
    print(f"wrote bay_land.geojson: {mask.geom_type}, "
          f"{len(getattr(mask,'geoms',[1]))} parts, {npts} pts, "
          f"bounds {[round(b,3) for b in mask.bounds]}")


if __name__ == "__main__":
    main()
