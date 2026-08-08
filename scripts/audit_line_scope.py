#!/usr/bin/env python3
"""Audit candidate transit lines against the play area before adopting them.

For every OSM route relation matching the filter, reports how many of its stops
fall inside a region's play area, and which of those stops merely duplicate a
station the map already has. See the add-transit-city skill's line-inclusion
gates: a line belongs on a map only if a MAJORITY of its stops are in play (the
other two gates — walk-up fares and hourly-every-day service — are judgement and
GTFS, not geometry).

    python3 scripts/audit_line_scope.py --region dc --route train \
        --filter 'MARC|Virginia Railway Express|Amtrak'
"""
import argparse
import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OVERPASS = "https://overpass-api.de/api/interpreter"
UA = {"User-Agent": "jetlagapp-line-scope/1.0"}
DUP_M = 250  # a candidate stop this close to an existing station is not a new suspect


def overpass(query, tries=6):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                OVERPASS, data=urllib.parse.urlencode({"data": query}).encode(), headers=UA
            )
            return json.loads(urllib.request.urlopen(req, timeout=300).read())
        except Exception as exc:  # 429/504 are routine on the public instance
            if attempt == tries - 1:
                raise
            print(f"  overpass retry ({exc})")
            time.sleep(25)


def play_rings(region):
    slug = "" if region == "bay" else f"{region}."
    gj = json.loads((ROOT / "src/data" / f"{slug}play-area.geojson.json").read_text())
    rings = []
    for feat in gj.get("features", [gj]):
        geom = feat.get("geometry", feat)
        coords = geom["coordinates"]
        rings += [coords[0]] if geom["type"] == "Polygon" else [p[0] for p in coords]
    return rings


def inside(rings, lat, lon):
    hit = False
    for ring in rings:
        for i in range(len(ring) - 1):
            x1, y1 = ring[i]
            x2, y2 = ring[i + 1]
            if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                hit = not hit
    return hit


def metres(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return 6371000 * math.hypot(dlat, dlon)


def stops(rel, nodes):
    """Unique named stop/platform members, in relation order."""
    seen, out = set(), []
    for m in rel.get("members", []):
        if m["type"] != "node" or not m.get("role", "").startswith(("stop", "platform")):
            continue
        node = nodes.get(m["ref"])
        if not node:
            continue
        name = (node.get("tags") or {}).get("name", f"{node['lat']:.4f},{node['lon']:.4f}")
        if name in seen:
            continue
        seen.add(name)
        out.append((name, node["lat"], node["lon"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    ap.add_argument("--route", default="train", help="OSM route value (train, subway, tram…)")
    ap.add_argument("--filter", default=".", help="regex over the relation name")
    ap.add_argument("--bbox", help="south,west,north,east (default: play-area bounds + 1°)")
    args = ap.parse_args()

    rings = play_rings(args.region)
    slug = "" if args.region == "bay" else f"{args.region}."
    have = json.loads((ROOT / "src/data" / f"{slug}stations.json").read_text())

    if args.bbox:
        bbox = args.bbox
    else:
        xs = [p[0] for r in rings for p in r]
        ys = [p[1] for r in rings for p in r]
        bbox = f"{min(ys)-1},{min(xs)-1},{max(ys)+1},{max(xs)+1}"

    found = overpass(f'[out:json][timeout:180];relation["route"="{args.route}"]({bbox});out tags;')
    pat = re.compile(args.filter, re.I)
    rels = [e for e in found["elements"] if pat.search(e.get("tags", {}).get("name", ""))]
    # one relation per line+direction pair is enough; keep the longest name variant
    byline = {}
    for rel in rels:
        line = rel["tags"]["name"].split(":")[0].strip()
        byline.setdefault(line, rel)
    print(f"{len(byline)} line(s) matching /{args.filter}/\n")

    for line, rel in sorted(byline.items()):
        data = overpass(f"[out:json][timeout:180];relation({rel['id']});out body;node(r);out;")
        nodes = {e["id"]: e for e in data["elements"] if e["type"] == "node" and "lat" in e}
        full = stops([e for e in data["elements"] if e["type"] == "relation"][0], nodes)
        if not full:
            print(f"{line}: no stop members in OSM")
            continue
        ins = [s for s in full if inside(rings, s[1], s[2])]
        share = 100 * len(ins) / len(full)
        new = [
            s for s in ins
            if not have or min(metres(s[1], s[2], h["lat"], h["lon"]) for h in have) > DUP_M
        ]
        verdict = "MAJORITY IN PLAY" if share > 50 else "minority — reject"
        print(f"{line}\n  {len(full)} stops · {len(ins)} in play ({share:.0f}%) — {verdict}")
        print(f"  would add {len(new)} new station(s): {', '.join(n[0] for n in new) or '—'}")
        time.sleep(20)


if __name__ == "__main__":
    main()
