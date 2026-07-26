#!/usr/bin/env python3
"""Build a region's three Census-derived boundary layers from its play area:

  counties  county (and county-equivalent) polygons — the Matching -> county
            question, countyAt(), and the county-border measure feature. Every
            county the play area touches, plus its neighbours whole, so a border
            sliver and the nearest-border math resolve outside the map too.
  places    Census places clipped to the play area — the Matching -> city
            question and cityAt(); land in no place reads "unincorporated".
  zctas     ZIP-code areas clipped to the play area — the Measuring -> ZIP
            question (US-only: ZIPs are ordinal, so "smaller/larger" works).
  states    (only for a map spanning more than one state) state polygons around
            the play area, the source build_measure_features.py turns into the
            state-border measure feature. The bundled measure_src/us-states
            file is far too coarse where the border matters — DC's runs down the
            Potomac shoreline.

Adding a city is one entry in poi_geo.REGIONS (`states`, `play`, `countiesGeo`,
`places`, `zctas`):

    python3 scripts/build_region_geo.py --region dc

The Bay Area and LA predate this script (build_city_places.py / build_la_*.py,
each with a water mask that clips legal limits back to the real shore); it is
the general path every later map uses.

Sources: Census TIGER/Line 2023 places per state + national ZCTA5, and the
cb_2023_us_county_500k cartographic county file.
"""
import argparse
import io
import json
import os
import sys
import urllib.request
import zipfile

from shapely.geometry import (shape, mapping, box, Polygon, MultiPolygon,
                              GeometryCollection)
from shapely.ops import transform, unary_union

import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_census_place")
ZCTA_CACHE = os.path.join(HERE, "_census_zcta")

PLACE_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_{fips}_place.zip"
COUNTY_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
COUNTY_STEM = "cb_2023_us_county_500k"
ZCTA_URL = "https://www2.census.gov/geo/tiger/TIGER2023/ZCTA520/tl_2023_us_zcta520.zip"
ZCTA_STEM = "tl_2023_us_zcta520"
STATE_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip"
STATE_STEM = "cb_2023_us_state_500k"
MEASURE_SRC = os.path.join(HERE, "measure_src")

SIMPLIFY_DEG = 0.0002   # ~22 m; plenty for point-in-polygon + shading
MIN_AREA_DEG2 = 1e-7    # drop sliver clip artifacts (~1000 m^2)
NEIGHBOR_TOL_DEG = 0.002  # counties within ~200 m of an in-play one are neighbours


def polygonal(g):
    """Keep only the (multi)polygon part — a clip can yield a GeometryCollection
    with stray boundary lines/points."""
    if g.is_empty or isinstance(g, (Polygon, MultiPolygon)):
        return g
    if isinstance(g, GeometryCollection):
        parts = [p for p in g.geoms if isinstance(p, (Polygon, MultiPolygon))]
        return unary_union(parts) if parts else Polygon()
    return Polygon()


def valid(g):
    return g if g.is_valid else g.buffer(0)


def rounded(g, nd=6):
    """~10 cm coordinate precision — halves the file size, and rounding is
    deterministic so neighbouring polygons keep sharing their exact edge."""
    return transform(lambda x, y, z=None: (round(x, nd), round(y, nd)), g)


def ensure_shapefile(url, stem, cache=CACHE, note=""):
    shp = os.path.join(cache, stem + ".shp")
    if os.path.exists(shp):
        return shp
    os.makedirs(cache, exist_ok=True)
    print(f"downloading {url} {note}...", file=sys.stderr)
    data = urllib.request.urlopen(url, timeout=900).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(cache)
    return shp


def load_play(region):
    fc = json.load(open(poi_geo.repo_path(region, "play")))
    return valid(shape(fc["features"][0]["geometry"]))


def write(dest, features, what):
    out = {"type": "FeatureCollection", "features": features}
    with open(dest, "w") as f:
        json.dump(out, f)
    print(f"wrote {dest} — {len(features)} {what}, {os.path.getsize(dest)} bytes")


def county_label(rec):
    """The name the station records carry: Census NAME, except a county
    equivalent that is not a county (a VA independent city, DC), where the LSAD
    is part of the name — "Fairfax" the county vs "Fairfax city"."""
    return rec["NAME"] if rec["LSAD"] == "06" else rec["NAMELSAD"]


def build_counties(region, play):
    import shapefile
    r = shapefile.Reader(ensure_shapefile(COUNTY_URL, COUNTY_STEM))
    flds = [f[0] for f in r.fields[1:]]
    inplay, rest = {}, {}
    for sh, rec in zip(r.shapes(), r.records()):
        d = dict(zip(flds, rec))
        bx0, by0, bx1, by1 = sh.bbox
        minx, miny, maxx, maxy = play.bounds
        if bx1 < minx - 1 or bx0 > maxx + 1 or by1 < miny - 1 or by0 > maxy + 1:
            continue
        g = valid(shape(sh.__geo_interface__))
        (inplay if g.intersects(play) else rest)[county_label(d)] = g

    # Neighbours: whole polygons, so a station near the edge still has a real
    # county line to measure to and a click just outside resolves to a name.
    edge = unary_union(list(inplay.values())).buffer(NEIGHBOR_TOL_DEG)
    keep = dict(inplay)
    keep.update({n: g for n, g in rest.items() if g.intersects(edge)})

    # NOT simplified: adjacent counties in the cartographic file share exact
    # vertices, and the county-border measure feature is their pairwise boundary
    # intersection. Simplifying each polygon on its own pulls those shared edges
    # apart, and the "border" degenerates into hundreds of 2-point slivers.
    feats = []
    for name in sorted(keep):
        g = rounded(polygonal(keep[name]))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        feats.append({"type": "Feature", "properties": {"name": name},
                      "geometry": mapping(g)})
    print("  in play:", ", ".join(sorted(inplay)))
    write(poi_geo.repo_path(region, "countiesGeo"), feats, "counties")


def build_places(region, play):
    import shapefile
    clipped = {}
    for fips, _ in poi_geo.REGIONS[region]["states"]:
        stem = f"tl_2023_{fips}_place"
        r = shapefile.Reader(ensure_shapefile(PLACE_URL.format(fips=fips), stem))
        flds = [f[0] for f in r.fields[1:]]
        for sh, rec in zip(r.shapes(), r.records()):
            d = dict(zip(flds, rec))
            g = valid(shape(sh.__geo_interface__))
            if not g.intersects(play):
                continue
            g = valid(polygonal(g.intersection(play)))
            if g.is_empty or g.area < MIN_AREA_DEG2:
                continue
            if d["NAMELSAD"] in clipped:  # same name in two states
                g = unary_union([clipped[d["NAMELSAD"]], g])
            clipped[d["NAMELSAD"]] = g

    feats = []
    for name in sorted(clipped):
        g = rounded(polygonal(clipped[name].simplify(SIMPLIFY_DEG, preserve_topology=True)))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        feats.append({"type": "Feature", "properties": {"name": name},
                      "geometry": mapping(g)})
    write(poi_geo.repo_path(region, "places"), feats, "places")


def build_zctas(region, play):
    import shapefile
    minx, miny, maxx, maxy = play.bounds
    r = shapefile.Reader(ensure_shapefile(ZCTA_URL, ZCTA_STEM, ZCTA_CACHE, "(~530 MB) "))
    flds = [f[0] for f in r.fields[1:]]
    zip_field = "ZCTA5CE20" if "ZCTA5CE20" in flds else "ZCTA5CE10"

    clipped = {}
    for sh, rec in zip(r.iterShapes(), r.iterRecords()):
        bx0, by0, bx1, by1 = sh.bbox  # cheap reject before building geometry
        if bx1 < minx or bx0 > maxx or by1 < miny or by0 > maxy:
            continue
        d = dict(zip(flds, rec))
        g = valid(shape(sh.__geo_interface__))
        if not g.intersects(play):
            continue
        g = valid(polygonal(g.intersection(play)))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        clipped[str(d[zip_field])] = g

    feats = []
    for zc in sorted(clipped):
        g = rounded(polygonal(clipped[zc].simplify(SIMPLIFY_DEG, preserve_topology=True)))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        feats.append({"type": "Feature", "properties": {"name": zc},
                      "geometry": mapping(g)})
    write(poi_geo.repo_path(region, "zctas"), feats, "ZCTAs")


def build_states(region, play):
    """State polygons near the play area (a multi-state map only), at the same
    cartographic resolution as the counties so a state line and the county line
    that follows it agree."""
    import shapefile
    minx, miny, maxx, maxy = play.bounds
    clip = box(minx - 0.5, miny - 0.5, maxx + 0.5, maxy + 0.5)
    r = shapefile.Reader(ensure_shapefile(STATE_URL, STATE_STEM))
    flds = [f[0] for f in r.fields[1:]]
    feats = []
    for sh, rec in zip(r.shapes(), r.records()):
        d = dict(zip(flds, rec))
        bx0, by0, bx1, by1 = sh.bbox
        if bx1 < clip.bounds[0] or bx0 > clip.bounds[2] or by1 < clip.bounds[1] or by0 > clip.bounds[3]:
            continue
        g = rounded(polygonal(valid(shape(sh.__geo_interface__)).intersection(clip)))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        feats.append({"type": "Feature", "properties": {"name": d["NAME"]},
                      "geometry": mapping(g)})
    os.makedirs(MEASURE_SRC, exist_ok=True)
    write(os.path.join(MEASURE_SRC, f"states.{region}.geojson"), feats, "states")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    poi_geo.add_region_arg(ap)
    ap.add_argument("--what", default="counties,places,zctas",
                    help="comma-separated subset of counties,places,zctas,states")
    a = ap.parse_args()
    play = load_play(a.region)
    for what in a.what.split(","):
        {"counties": build_counties, "places": build_places, "states": build_states,
         "zctas": build_zctas}[what.strip()](a.region, play)


if __name__ == "__main__":
    main()
