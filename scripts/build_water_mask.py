#!/usr/bin/env python3
"""Build a dense bay+ocean water mask (bay_water_mask.geojson) from Census
TIGER/Line AREAWATER for the transit counties.

build_play_area.py uses full-resolution TIGER/Line PLACE boundaries (dense
coastline nodes), but those are *legal* limits that extend far out into the bay.
This mask is subtracted from each place so the in-play land is clipped back to
the real shoreline at TIGER resolution. AREAWATER is authoritative and dense, so
the resulting coast has far more segments than the old 1:500k cartographic
generalisation.

Only large open-water bodies are kept (connected components above
MIN_WATER_KM2), so the bay / San Pablo Bay / Carquinez Strait / Pacific are
removed but inland reservoirs, ponds and creeks are left alone (they must NOT
punch holes in the in-play cities). The same mask is reusable for the future
coastline question (distance-to-coast / Bay-vs-Pacific).
"""
import io
import json
import math
import os
import sys
import urllib.request
import zipfile

import shapefile
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_cache")

# Census county FIPS for the five transit-served counties.
COUNTY_FIPS = {
    "Alameda": "001",
    "Contra Costa": "013",
    "San Francisco": "075",
    "San Mateo": "081",
    "Santa Clara": "085",
}
AREAWATER_URL = "https://www2.census.gov/geo/tiger/TIGER2023/AREAWATER/tl_2023_06{fips}_areawater.zip"
MIN_WATER_KM2 = 15.0   # keep only big open water (bay/ocean); drop reservoirs/ponds
M = 111320.0
LAT0 = 37.7


def _proj():
    cos0 = math.cos(math.radians(LAT0))
    def to_m(x, y, z=None):
        return (x * M * cos0, y * M)
    return to_m


def ensure(url, stem):
    shp = os.path.join(CACHE, stem + ".shp")
    if os.path.exists(shp):
        return shp
    os.makedirs(CACHE, exist_ok=True)
    print(f"downloading {url}", file=sys.stderr)
    data = urllib.request.urlopen(url, timeout=300).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(CACHE)
    return shp


def main():
    polys = []
    for name, fips in COUNTY_FIPS.items():
        stem = f"tl_2023_06{fips}_areawater"
        shp = ensure(AREAWATER_URL.format(fips=fips), stem)
        r = shapefile.Reader(shp)
        n = 0
        for sh in r.shapes():
            g = shape(sh.__geo_interface__)
            if not g.is_valid:
                g = g.buffer(0)
            if not g.is_empty:
                polys.append(g)
                n += 1
        print(f"  {name}: {n} water polygons", file=sys.stderr)

    merged = unary_union(polys)
    parts = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    to_m = _proj()
    big = []
    for p in parts:
        km2 = transform(to_m, p).area / 1e6
        if km2 >= MIN_WATER_KM2:
            big.append(p)
    big.sort(key=lambda p: transform(to_m, p).area, reverse=True)
    print(f"kept {len(big)} open-water bodies >= {MIN_WATER_KM2} km2 "
          f"(largest {transform(to_m, big[0]).area/1e6:.0f} km2)" if big else "none",
          file=sys.stderr)
    mask = unary_union(big)

    out = {"type": "Feature",
           "properties": {"source": "census tiger AREAWATER",
                          "min_km2": MIN_WATER_KM2},
           "geometry": mapping(mask)}
    with open(os.path.join(HERE, "bay_water_mask.geojson"), "w") as fh:
        json.dump(out, fh)
    npts = sum(len(p.exterior.coords) for p in
               (mask.geoms if mask.geom_type == "MultiPolygon" else [mask]))
    print(f"wrote bay_water_mask.geojson: {mask.geom_type}, "
          f"{len(getattr(mask,'geoms',[1]))} parts, {npts} pts, "
          f"bounds {[round(b,3) for b in mask.bounds]}")


if __name__ == "__main__":
    main()
