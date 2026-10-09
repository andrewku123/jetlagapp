#!/usr/bin/env python3
"""Build the county lines that run over water (bays, harbors, rivers) for the
"Measuring — county border" question.

The app's county polygons (src/data/<prefix>counties.geojson.json) are land-only,
so a pairwise shared-boundary build of them only finds land borders. Real county
lines also cross water (e.g. SF / Alameda / San Mateo down the middle of SF Bay).
This takes the full-resolution Census TIGER/Line county polygons (which include
water), finds every boundary shared by two counties, keeps only the parts that
lie over water (outside the land polygons) AND inside the game's play-area
polygon — a border outside the play area doesn't exist for the game, which drops
the open-Pacific extensions — and writes them to
scripts/measure_src/county_water_borders.<city>.geojson.
build_measure_features.py unions that file into the county border.

Usage:
  CITY=bayarea python3 scripts/build_county_water_borders.py
  # TIGER_COUNTY_SHP=/path/tl_2023_us_county.shp to skip the ~83 MB download
"""
import json
import os
import urllib.request
import zipfile

import shapefile
from shapely.geometry import shape, mapping, box
from shapely.ops import linemerge, unary_union

import build_measure_features as bmf

TIGER_URL = "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip"
CACHE = os.path.expanduser("~/.cache/jetlag-tiger")
# Drop slivers where the land polygon and TIGER disagree along a shore (~0.2 mi).
MIN_PIECE_DEG = 0.003


def tiger_shp():
    if os.environ.get("TIGER_COUNTY_SHP"):
        return os.environ["TIGER_COUNTY_SHP"]
    shp = os.path.join(CACHE, "tl_2023_us_county.shp")
    if not os.path.exists(shp):
        os.makedirs(CACHE, exist_ok=True)
        z = os.path.join(CACHE, "tl_2023_us_county.zip")
        print("downloading", TIGER_URL)
        urllib.request.urlretrieve(TIGER_URL, z)
        zipfile.ZipFile(z).extractall(CACHE)
    return shp


def pieces(g):
    if g.is_empty:
        return []
    if g.geom_type == "LineString":
        return [g]
    if hasattr(g, "geoms"):
        return [p for sub in g.geoms for p in pieces(sub)]
    return []


def main():
    slug = os.environ.get("CITY", "bayarea")
    cfg = bmf.CITIES[slug]
    prefix = "" if slug == "bayarea" else f"{slug}."
    clip = box(*cfg["play_bbox"])
    play = unary_union([g.buffer(0) for g in bmf.feats(bmf.load(
        bmf.src(cfg.get("play") or f"data:{prefix}play-area.geojson.json")))])
    land = unary_union([g.buffer(0) for g in bmf.feats(bmf.load(bmf.src(cfg["counties"])))])

    counties = []
    for sr in shapefile.Reader(tiger_shp()).iterShapeRecords():
        g = shape(sr.shape.__geo_interface__)
        if g.intersects(clip):
            counties.append(g.buffer(0))
    print(f"{slug}: {len(counties)} TIGER counties in the play bbox")

    shared = bmf.build_county_border(counties, clip)
    water = shared.difference(land).intersection(play)
    merged = pieces(water)
    if merged:
        merged = pieces(linemerge(merged))
    keep = [p for p in merged if p.length >= MIN_PIECE_DEG]
    print(f"  water county lines in play: {len(keep)} pieces, "
          f"{sum(p.length for p in keep) * 69:.1f} mi (approx); dropped "
          f"{sum(p.length for p in merged if p.length < MIN_PIECE_DEG) * 69:.2f} mi of slivers")

    dest = os.path.join(bmf.HERE, "measure_src", f"county_water_borders.{slug}.geojson")
    if not keep:
        if os.path.exists(dest):
            os.remove(dest)
        print("  none — no file written")
        return
    out = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": mapping(p)} for p in keep]}
    with open(dest, "w") as f:
        json.dump(out, f)
    print("wrote", dest, os.path.getsize(dest), "bytes")


if __name__ == "__main__":
    main()
