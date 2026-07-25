#!/usr/bin/env python3
"""Build the compact POI data file the app's POI tab loads.

Every region has the same output shape — `REGIONS[region]["poi"]`, keyed by
category, each a list of `{n: name, lat, lon, t: primaryType, r: userRatingCount}`
with coordinates rounded to 6 dp (labels/colors live in `src/lib/poi.ts`):

    python3 build_poi_data.py --region la
    python3 build_poi_data.py --region bay            # its registry source: deduped
    python3 build_poi_data.py --region la --source deduped

This is the "apply to the app" step of a city whose manual pass is done. The
default source is the **review map** (`REGIONS[region]["viz"]`), the authoritative
record of that pass — every delete, merge and representative swap is already
applied to it — and we keep exactly what a reviewer sees on it: group
representatives and un-grouped singles, never merged-away children (one campus =
one POI, at the representative's own pin, so "nearest hospital" can't be answered
by a lab door).

A region whose review map predates review counts sets `"applyFrom": "deduped"`
instead (the Bay Area: its map carries no per-place `primaryType`, so its
`poi_deduped.json` keeps the real `t` values). Both sources are validated the same
way, and
`--region bay --source viz` reproduces the committed Bay place set exactly, which
is what validates the review-map path.

A review map deployed only as a preview site (not merged) can be pointed at with
`--viz`.
"""
import argparse
import json
import math
import os
import sys

import poi_geo
import poi_ledger as L

HERE = os.path.dirname(os.path.abspath(__file__))

# The LA/SF Muni-style cheap pull stores no per-place `primaryType`, so a region
# built from the review map records the category's canonical Google type instead
# of inventing a specific one. Neither `t` nor `r` drives gameplay; they are kept
# for provenance and for the POI tab.
CANON_TYPE = {"consulate": "embassy", "mountain": "mountain_peak"}

# How far outside the play polygon a POI may sit and still count as in play. The
# boundary is a simplified city union, so a waterfront pier or a park on the line
# can land a few metres outside it; the discovery pass uses the same 150 m buffer.
EDGE_TOLERANCE_M = 150


def from_deduped(path):
    """The de-dup survivors (`poi_deduped.json`), with their real Google types.

    Note this is the *deduped* file, not the curated one: curation is pre-clip and
    pre-merge, so building from it would ship out-of-play pins and every campus
    fragment.
    """
    curated = json.load(open(path))
    return {key: [{"n": p["name"], "lat": p["lat"], "lon": p["lon"],
                   "t": p.get("primaryType"), "r": p.get("userRatingCount") or 0}
                  for p in blk["places"]]
            for key, blk in curated.items()}


def from_viz(obj):
    """A finished manual pass: the review map's visible pins, category by category."""
    out = {}
    for cat, c in obj.items():
        if not isinstance(c, dict) or "groups" not in c:
            continue
        visible = [g["rep"] for g in c["groups"]] + c["singles"]
        out[cat] = [{"n": p["n"], "lat": p["lat"], "lon": p["lon"],
                     "t": CANON_TYPE.get(cat, cat), "r": p.get("r") or 0}
                    for p in visible]
    return out


def build(region, source=None, viz=None, deduped=None):
    """The region's app POI data, validated. Raises SystemExit on a bad dataset."""
    source = source or L.REGIONS[region].get("applyFrom", "viz")
    if source == "viz":
        with open(viz or L.viz_path(region), encoding="utf-8") as f:
            out = from_viz(L.parse_viz(f.read()))
    else:
        out = from_deduped(deduped or poi_geo.work(region, "poi_deduped.json"))
    in_play = poi_geo.make_in_play(
        poi_geo.load_play(region, path=poi_geo.repo_path(region, "play")),
        tolerance_m=EDGE_TOLERANCE_M)

    for cat, places in out.items():
        for p in places:
            p["lat"], p["lon"] = round(p["lat"], 6), round(p["lon"], 6)
        places.sort(key=lambda x: x["n"].lower())
        # A duplicate is a de-dup failure, and out-of-play POIs make "nearest X"
        # unanswerable — fail the build rather than ship either.
        spots = [(p["n"], p["lat"], p["lon"]) for p in places]
        if len(set(spots)) != len(spots):
            dupe = next(s for s in spots if spots.count(s) > 1)
            sys.exit(f"{cat}: duplicate POI {dupe}")
        stray = [p for p in places if not in_play(p["lon"], p["lat"])]
        if stray:
            sys.exit(f"{cat}: {len(stray)} POI outside the play area, "
                     f"e.g. {stray[0]['n']} at {stray[0]['lat']},{stray[0]['lon']}")
    return out


def main():
    ap = poi_geo.add_region_arg(
        argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter))
    ap.add_argument("--source", choices=("viz", "deduped"),
                    help="override the region's `applyFrom`")
    ap.add_argument("--viz", help="review map path, if not the region's default")
    ap.add_argument("--deduped", help="deduped JSON, if not the region's default")
    ap.add_argument("--out", help="output path, if not the region's default")
    a = ap.parse_args()
    out = build(a.region, a.source, a.viz, a.deduped)
    dest = a.out or poi_geo.repo_path(a.region, "poi")

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    total = sum(len(v) for v in out.values())
    print(f"wrote {os.path.normpath(dest)}: {total} POIs across {len(out)} categories")
    for k, v in out.items():
        print(f"  {k:15s} {len(v)}")


if __name__ == "__main__":
    main()
