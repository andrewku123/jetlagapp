#!/usr/bin/env python3
"""Cross-check a curated category against an authoritative registry.

`authoritative_candidates.py` uses registries at *build* time to widen recall.
This is the other direction, run *after* the manual pass: take the official list
of every X in the play area and ask "where did each one end up on our map?".
It answers the only question a human can't eyeball off a 250-pin map — **what is
missing** — and, more usefully, *why*:

    covered   a visible pin sits on it                      -> nothing to do
    merged    only merged-away pins are there                -> check the rep is sane
    dropped   we deleted it (reason from the ledger)         -> was that right?
    missing   no pin, no ledger record: never discovered     -> see below

A `missing` verdict is NOT automatically a bug. Discovery asks Google for places
whose `types` include the category, so a facility Google files under another type
is invisible to us by construction -- and correctly so, because the game's rule is
"what a seeker sees on Google Maps". Verify each one on Google Maps before acting:
if it carries the category icon, it is a real recall hole (fix by adding it as an
`auth_lists/` candidate and re-running the icon-check); if it doesn't, the registry
and Google simply disagree, and Google wins.

    python3 registry_audit.py --region la --cat hospital --source chhs
    python3 registry_audit.py --region bay --cat mountain --source geonames
    python3 registry_audit.py --region la --cat museum --csv auth_lists/museum.csv

Sources: `--csv` takes any file with columns `name[,lat,lon][,city]` (the same
shape `auth_lists/` uses); `--source` runs a built-in fetcher. See gather-poi
SKILL.md for the per-category registry table.
"""
import argparse
import csv
import json
import math
import os
import re
import unicodedata
import urllib.request
import zipfile

import poi_ledger as L

HERE = os.path.dirname(os.path.abspath(__file__))
NEAR_M = 500          # a registry address and a Google pin rarely agree closer
NAME_KM = 2.0         # name match is allowed to be looser than the coord match
SAME_SPOT_M = 150     # close enough to be the same place whatever it is called


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").casefold().replace("&", " and ")
    return " ".join(re.sub(r"[^\w\s]", " ", s).split())


def metres(a, b):
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def related(a, b):
    """Same place by name? One name's words contain the other's, >=2 words each --
    the 2-word floor stops a pin called just "Tarzana" swallowing every registry
    entry with Tarzana in its name."""
    x, y = set(norm(a).split()), set(norm(b).split())
    return min(len(x), len(y)) >= 2 and (x <= y or y <= x)


# ------------------------------------------------------------ registry sources

def from_csv(path):
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            lat, lon = row.get("lat"), row.get("lon")
            out.append({"name": name, "city": (row.get("city") or "").strip(),
                        "lat": float(lat) if lat else None,
                        "lon": float(lon) if lon else None})
    return out


def from_cms():
    """CMS Hospital General Information — every Medicare-certified US hospital."""
    base = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"
    out, off = [], 0
    while True:
        with urllib.request.urlopen(f"{base}?limit=500&offset={off}", timeout=60) as r:
            rows = json.load(r).get("results", [])
        if not rows:
            return out
        for x in rows:
            out.append({"name": (x.get("facility_name") or "").title(),
                        "city": (x.get("citytown") or "").title(),
                        "lat": None, "lon": None})
        off += 500


CHHS_CSV = ("https://data.chhs.ca.gov/dataset/3b5b80e8-6b8d-4715-b3c0-2699af6e72e5/"
            "resource/f0ae5731-fef8-417f-839d-54a0ed3a126e/download/"
            "health_facility_locations.csv")
CHHS_TYPES = ("GENERAL ACUTE CARE HOSPITAL", "ACUTE PSYCHIATRIC HOSPITAL")


def from_chhs():
    """California licensed hospitals (CHHS) — has coordinates, and unlike CMS it
    carries the psychiatric/rehab hospitals Medicare certification leaves out."""
    cache = os.path.join(HERE, "chhs_health_facilities.csv")
    if not os.path.exists(cache):
        urllib.request.urlretrieve(CHHS_CSV, cache)
    out = []
    with open(cache, encoding="utf-8-sig", errors="replace") as f:
        for x in csv.DictReader(f):
            if (x.get("FAC_FDR") in CHHS_TYPES
                    and x.get("FAC_STATUS_TYPE_CODE") == "OPEN"
                    and x.get("LATITUDE")):
                out.append({"name": (x.get("FACNAME") or "").title(),
                            "city": (x.get("CITY") or "").title(),
                            "lat": float(x["LATITUDE"]),
                            "lon": float(x["LONGITUDE"])})
    return out


def from_geonames(country="US"):
    """GeoNames named peaks (feature class T, codes PK/MT)."""
    cache = os.path.join(HERE, f"geonames_{country}.zip")
    if not os.path.exists(cache):
        urllib.request.urlretrieve(
            f"https://download.geonames.org/export/dump/{country}.zip", cache)
    with zipfile.ZipFile(cache) as z:
        txt = z.read(f"{country}.txt").decode("utf-8", "replace")
    out = []
    for line in txt.splitlines():
        f = line.split("\t")
        if len(f) > 8 and f[6] == "T" and f[7] in ("PK", "MT"):
            out.append({"name": f[1], "city": "",
                        "lat": float(f[4]), "lon": float(f[5])})
    return out


SOURCES = {"chhs": from_chhs, "cms": from_cms, "geonames": from_geonames}


# ------------------------------------------------------------------- the audit

def audit(region, cat, entries):
    obj = L.load_viz(region)
    if cat not in obj:
        raise SystemExit(f"no category '{cat}' in the {region} review map")
    play = json.load(open(os.path.join(L.ROOT, L.REGIONS[region]["play"])))
    rings = []
    for feat in play["features"]:
        geom = feat["geometry"]
        polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                 else [geom["coordinates"]])
        rings += [p[0] for p in polys]

    def in_play(lat, lon):
        inside = False
        for ring in rings:
            c = False
            for i in range(len(ring) - 1):
                (x1, y1), (x2, y2) = ring[i], ring[i + 1]
                if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) / (y2 - y1) * (x2 - x1):
                    c = not c
            inside ^= c
        return inside

    c = obj[cat]
    visible = [g["rep"] for g in c["groups"]] + c["singles"]
    hidden = [k for g in c["groups"] for k in g["kids"]]
    reps = {id(k): g["rep"]["n"] for g in c["groups"] for k in g["kids"]}
    led = L.load_ledger(region)
    drops = [r for r in led["places"].values()
             if r["decision"] == "drop" and r.get("cat") == cat and r.get("lat")]

    def hits(pins, pt, name):
        by_dist = [p for p in pins if metres(pt, (p["lat"], p["lon"])) < NEAR_M] if pt else []
        if by_dist:
            return by_dist
        return [p for p in pins
                if (not pt or metres(pt, (p["lat"], p["lon"])) < NAME_KM * 1000)
                and related(name, p["n"])]

    buckets = {"covered": [], "merged": [], "dropped": [], "missing": [], "out": []}
    for e in entries:
        pt = (e["lat"], e["lon"]) if e["lat"] is not None else None
        if pt and not in_play(*pt):
            buckets["out"].append(e)
            continue
        if hits(visible, pt, e["name"]):
            buckets["covered"].append(e)
        elif (h := hits(hidden, pt, e["name"])):
            buckets["merged"].append((e, [reps[id(p)] for p in h][:1]))
        elif pt and (d := [(metres(pt, (r["lat"], r["lon"])), r) for r in drops
                           if metres(pt, (r["lat"], r["lon"])) < NEAR_M
                           and (metres(pt, (r["lat"], r["lon"])) < SAME_SPOT_M
                                or related(e["name"], r["name"]))]):
            buckets["dropped"].append((e, [r for _, r in sorted(d)]))
        else:
            buckets["missing"].append(e)
    return buckets


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", required=True, choices=sorted(L.REGIONS))
    ap.add_argument("--cat", required=True)
    ap.add_argument("--csv", help="registry file: name[,lat,lon][,city]")
    ap.add_argument("--source", choices=sorted(SOURCES), help="built-in registry")
    a = ap.parse_args()
    if not (a.csv or a.source):
        raise SystemExit("give --csv or --source")

    entries = from_csv(a.csv) if a.csv else SOURCES[a.source]()
    b = audit(a.region, a.cat, entries)
    scanned = sum(len(v) for k, v in b.items() if k != "out")
    print(f"{a.cat}: {len(entries)} registry entries, {len(b['out'])} outside the "
          f"play area / unplaceable, {scanned} checked")
    print(f"  covered {len(b['covered'])}  merged {len(b['merged'])}  "
          f"dropped {len(b['dropped'])}  missing {len(b['missing'])}\n")
    for e, reps in b["merged"]:
        print(f"MERGED   {e['name']} — under {reps[0] if reps else '?'}")
    for e, recs in b["dropped"]:
        why = ", ".join(f"{r['name']} ({r.get('reason')})" for r in recs[:3])
        print(f"DROPPED  {e['name']} — we deleted: {why}")
    for e in b["missing"]:
        where = f" — {e['city']}" if e["city"] else ""
        pin = (f"  https://www.google.com/maps/search/?api=1&query="
               f"{e['lat']:.5f},{e['lon']:.5f}" if e["lat"] is not None else "")
        print(f"MISSING  {e['name']}{where}{pin}")
    if b["missing"] or b["dropped"]:
        print("\nCheck each on Google Maps: keeps only what carries the "
              f"'{a.cat}' icon — a registry entry Google files under another "
              "type is correctly absent.")


if __name__ == "__main__":
    main()
