#!/usr/bin/env python3
"""Build the NYC map's geometry: play area, landmasses and measure features.

Play area: the five boroughs, shoreline-clipped (NYC Open Data "Borough
Boundaries", water areas excluded — far finer than Census cartographic files).
An island stays in play when it has a station or a public bridge you can walk
across (Randalls/Wards, City Island; KEEP_ISLANDS). Boat-only or closed islands
(Governors, Liberty, Ellis, Rikers, North/South Brother, Hart, the Jamaica Bay
marshes) are dropped, so nothing on them exists for questions.

Landmasses (the Matching -> landmass question): connected pieces of land, where
bridges and tunnels never join two pieces. The Rockaway peninsula has no land
link to the rest of Queens inside the city, but it is joined to Long Island
through Nassau County, so it is part of Long Island (LANDMASSES lists more than
one seed for a landmass in that case). Marble Hill is on the mainland.

Measure features (src/data/nyc.measure-features.geojson.json):
  coastline     the shore of salt water at least COAST_MIN_MI across, plus the
                Hudson (Andrew's call: it is tidal harbor water and Manhattan's
                west side reads as "the coast"). The East River, Harlem River,
                Kill Van Kull, Arthur Kill, Newtown Creek and Gowanus are under
                a mile across, so their banks are not coast.
  county-border borough lines, including the ones that run through water
                (TIGER county polygons, which extend over water), and the city
                limit with Nassau, Westchester and the New Jersey counties.
  state-border  the New York / New Jersey line (Hudson, Kill Van Kull, Arthur
                Kill) inside the city limit.
  hsr           Amtrak's Acela route (Andrew's call: Acela counts as high-speed
                rail), from Amtrak's GTFS shapes, clipped to the city limit:
                Penn Station, the Hudson and East River tunnels, Sunnyside, the
                Hell Gate Bridge and the east Bronx.

    python3 scripts/build_nyc_geo.py          # after build_nyc_stations.py
"""
import csv
import io
import json
import os
import urllib.request
import zipfile

import shapefile
import shapely
from shapely.geometry import (LineString, MultiLineString, Point, Polygon, box,
                              mapping, shape)
from shapely.ops import linemerge, transform, unary_union
from shapely.prepared import prep

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "src", "data")
CENSUS = os.path.join(HERE, "_census_place")
GTFS = os.path.join(HERE, "_gtfs_nyc")
BOROUGHS = os.path.join(HERE, "measure_src", "nyc_boroughs.geojson")
BOROUGHS_URL = "https://data.cityofnewyork.us/resource/gthc-hcne.geojson"
STATIONS = os.path.join(HERE, "stations.nyc.json")
TIGER_COUNTY = ("https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip",
                "tl_2023_us_county")
CB_COUNTY = ("https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip",
             "cb_2023_us_county_500k")
AMTRAK_URL = "https://content.amtrak.com/content/gtfs/GTFS.zip"

NYC_FIPS = {"36005": "Bronx", "36047": "Kings", "36061": "New York",
            "36081": "Queens", "36085": "Richmond"}
NEIGHBOR_FIPS = {"36059", "36119", "34003", "34013", "34017", "34023", "34025",
                 "34039", "09001"}
# NYC Open Data borough name -> the name the app shows; stations take the same
# names (`countyFromGeo` in poi_geo.REGIONS["nyc"]).
BOROUGH_NAME = {"Manhattan": "Manhattan", "Bronx": "Bronx", "Brooklyn": "Brooklyn",
                "Queens": "Queens", "Staten Island": "Staten Island"}
BBOX = (-74.45, 40.35, -73.55, 41.05)
M_PER_MI = 1609.344
COAST_MIN_MI = 1.0
LAT0 = 40.7
SIMPLIFY_M = 8

# Walkable islands without a station that stay in play: (name, lat, lon).
KEEP_ISLANDS = [("Randalls and Wards Island", 40.7935, -73.9230),
                ("City Island", 40.8468, -73.7867)]
# Landmass name -> seed points (lat, lon). Every kept piece of land must hold a
# seed; a landmass with two seeds joins land connected outside the play area.
LANDMASSES = {
    "Manhattan": [(40.7831, -73.9712)],
    "Mainland (Bronx)": [(40.8448, -73.8648)],
    "Long Island (Brooklyn, Queens)": [(40.6782, -73.9442), (40.5860, -73.8200)],
    "Staten Island": [(40.5795, -74.1502)],
    "Roosevelt Island": [(40.7620, -73.9500)],
    "Broad Channel": [(40.6080, -73.8180)],
    "Randalls and Wards Island": [(40.7935, -73.9230)],
    "City Island": [(40.8468, -73.7867)],
}
# Jamaica Bay is open salt water but crowded with marsh islands, so a mile-wide
# disk never fits between them; inside this box the narrow-channel test uses
# JAMAICA_MIN_MI instead (its basins and creeks still drop out).
JAMAICA = (-73.935, 40.575, -73.735, 40.67)
JAMAICA_MIN_MI = 0.25
# Shore this close to water that passes the width test still counts: piers,
# slips and coves along a wide bay.
COAST_REACH_M = 500
# The East River, Battery to Throgs Neck (with Flushing Bay and the Bronx
# creeks off it): never coast, even where it widens past a mile around Rikers.
# Edged on land at both ends of the city's shoreline it bounds.
EAST_RIVER = [(-74.0105, 40.7025), (-73.990, 40.750), (-73.950, 40.800), (-73.930, 40.840),
              (-73.830, 40.840), (-73.800, 40.810), (-73.785, 40.795), (-73.785, 40.775),
              (-73.950, 40.740), (-73.999, 40.692)]
# A corridor over the Hudson from the Battery to the Yonkers line, edged on
# Manhattan / Bronx land so it can't spill into the Harlem or East River. Water
# inside it is coast whatever its width.
HUDSON = [(-74.07, 40.69), (-74.018, 40.69), (-74.018, 40.700), (-73.990, 40.760),
          (-73.950, 40.830), (-73.935, 40.860), (-73.940, 40.875), (-73.905, 40.900),
          (-73.900, 40.916), (-73.930, 40.916), (-73.975, 40.860), (-74.035, 40.770),
          (-74.07, 40.70)]


def proj():
    """Local equirectangular metres around LAT0 (vectorized; plenty for a city)."""
    import math
    import numpy as np
    k = np.array([111320 * math.cos(math.radians(LAT0)), 110574])
    return (lambda g: shapely.transform(g, lambda a: a * k)), (lambda g: shapely.transform(g, lambda a: a / k))


TO_M, TO_LL = proj()


def fetch(url, dest):
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "jetlagapp-build"})
        with urllib.request.urlopen(req, timeout=600) as r:
            open(dest, "wb").write(r.read())
    return dest


def shp_records(spec, keep):
    url, stem = spec
    z = zipfile.ZipFile(fetch(url, os.path.join(CENSUS, stem + ".zip")))
    r = shapefile.Reader(shp=io.BytesIO(z.read(stem + ".shp")),
                         dbf=io.BytesIO(z.read(stem + ".dbf")))
    fields = [f[0] for f in r.fields[1:]]
    for sr in r.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        if keep(rec):
            yield rec, shape(sr.shape.__geo_interface__).buffer(0)


def feature(geom, **props):
    return {"type": "Feature", "properties": props, "geometry": mapping(geom)}


def rounded(g, nd=6):
    return shapely.set_precision(g, 10 ** -nd)


def write(name, features):
    p = os.path.join(DATA, name)
    json.dump({"type": "FeatureCollection", "features": features}, open(p, "w"),
              separators=(",", ":"))
    print(f"wrote {p} ({os.path.getsize(p) // 1024} KB)")


def parts(g):
    return list(g.geoms) if hasattr(g, "geoms") else [g]


def lines_of(g):
    out = []
    for p in parts(g):
        if p.geom_type == "LineString":
            out.append(p)
        elif p.geom_type == "MultiLineString":
            out.extend(p.geoms)
        elif hasattr(p, "geoms"):
            out.extend(lines_of(p))
    return [l for l in out if l.length > 0]


def multiline(lines, min_m=30):
    merged = linemerge(unary_union(lines)) if lines else MultiLineString()
    keep = [l for l in lines_of(merged) if l.length >= min_m]
    keep = [l.simplify(SIMPLIFY_M) for l in keep]
    return rounded(TO_LL(MultiLineString(keep)))


def main():
    fetch(BOROUGHS_URL, BOROUGHS)
    stations = json.load(open(STATIONS))
    st_pts = [TO_M(Point(s["lon"], s["lat"])) for s in stations]

    # --- play area: borough land, minus islands with neither a station nor a bridge
    boro = {f["properties"]["boroname"]: TO_M(shape(f["geometry"]).buffer(0))
            for f in json.load(open(BOROUGHS))["features"]}
    land = unary_union([g.buffer(0.5) for g in boro.values()]).buffer(-0.5)
    keep_pts = st_pts + [TO_M(Point(lon, lat)) for _, lat, lon in KEEP_ISLANDS]
    kept, dropped = [], []
    for p in parts(land):
        near = prep(p.buffer(30))
        (kept if any(near.contains(q) for q in keep_pts) else dropped).append(p)
    big_drops = sorted((p for p in dropped if p.area > 2e5), key=lambda p: -p.area)
    for p in big_drops:
        c = TO_LL(p.representative_point())
        print(f"  dropped island {p.area / 1e6:.2f} km2 at {c.y:.4f},{c.x:.4f}")
    play_m = unary_union(kept)
    play_ll = rounded(TO_LL(play_m.simplify(SIMPLIFY_M)))
    write("nyc.play-area.geojson.json", [feature(play_ll, name="New York City")])

    # --- boroughs (county Matching) and the one Census place (city Matching)
    write("nyc.counties.geojson.json", [
        feature(rounded(TO_LL(g.intersection(play_m).simplify(SIMPLIFY_M))), name=BOROUGH_NAME[n])
        for n, g in sorted(boro.items())])
    write("nyc.places.geojson.json", [feature(play_ll, name="New York city")])

    # --- landmasses
    seeds = {name: [TO_M(Point(lon, lat)) for lat, lon in pts] for name, pts in LANDMASSES.items()}
    groups = {name: [] for name in LANDMASSES}
    for p in kept:
        near = prep(p.buffer(30))
        hit = [n for n, pts in seeds.items() if any(near.contains(q) for q in pts)]
        if len(hit) != 1:
            c = TO_LL(p.representative_point())
            raise SystemExit(f"land piece at {c.y:.4f},{c.x:.4f} matches landmasses {hit}")
        groups[hit[0]].append(p)
    lm = []
    for name, ps in groups.items():
        if not ps:
            raise SystemExit(f"landmass {name}: no land at its seed")
        g = rounded(TO_LL(unary_union(ps).simplify(SIMPLIFY_M)))
        near = prep(unary_union(ps).buffer(30))
        n_st = sum(1 for q in st_pts if near.contains(q))
        print(f"  landmass {name}: {sum(p.area for p in ps) / 1e6:.1f} km2, {n_st} stations")
        lm.append(feature(g, name=name))
    write("nyc.landmasses.geojson.json", lm)

    # --- coastline
    others = [g for rec, g in shp_records(CB_COUNTY, lambda r: (r["STATEFP"] + r["COUNTYFP"]) in NEIGHBOR_FIPS)]
    frame = TO_M(box(*BBOX))
    all_land = unary_union([TO_M(g) for g in others] + [land]).intersection(frame)
    water = frame.difference(all_land)
    r = COAST_MIN_MI * M_PER_MI / 2
    wide = water.buffer(-r).buffer(r + COAST_REACH_M)
    jam = water.intersection(TO_M(box(*JAMAICA)))
    rj = JAMAICA_MIN_MI * M_PER_MI / 2
    jam_wide = jam.buffer(-rj).buffer(rj + COAST_REACH_M / 2)
    coastal = unary_union([wide, jam_wide, water.intersection(TO_M(Polygon(HUDSON)))])
    shore = unary_union([LineString(ring.coords) for p in parts(play_m)
                         for ring in [p.exterior]])
    coast = shore.intersection(coastal.buffer(40)).difference(TO_M(Polygon(EAST_RIVER)))
    feats = [feature(multiline(lines_of(coast), 50), key="coastline")]

    # --- county / state borders from TIGER (polygons extend over water)
    tiger = {rec["GEOID"]: TO_M(g) for rec, g in shp_records(
        TIGER_COUNTY, lambda r: r["GEOID"] in NYC_FIPS or r["GEOID"] in NEIGHBOR_FIPS)}
    city_limit = unary_union([tiger[f] for f in NYC_FIPS])
    county_lines, state_lines = [], []
    ids = sorted(tiger)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if a not in NYC_FIPS and b not in NYC_FIPS:
                continue
            shared = tiger[a].boundary.intersection(tiger[b].boundary.buffer(1))
            ls = lines_of(shared)
            county_lines += ls
            if a[:2] != b[:2]:
                state_lines += ls
    # Borders around islands that are out of play (the NY enclave of Liberty
    # Island, Ellis) don't exist for the game.
    clip = city_limit.buffer(5).difference(unary_union(dropped).buffer(300))
    feats.append(feature(multiline(lines_of(unary_union(county_lines).intersection(clip))),
                         key="county-border"))
    feats.append(feature(multiline(lines_of(unary_union(state_lines).intersection(clip))),
                         key="state-border"))

    # --- high-speed rail: Acela shapes
    amtrak = os.path.join(GTFS, "amtrak")
    if not os.path.isdir(amtrak):
        zipfile.ZipFile(fetch(AMTRAK_URL, os.path.join(GTFS, "amtrak.zip"))).extractall(amtrak)
    with open(os.path.join(amtrak, "routes.txt"), encoding="utf-8-sig") as fh:
        acela = {r["route_id"] for r in csv.DictReader(fh) if r["route_long_name"] == "Acela"}
    with open(os.path.join(amtrak, "trips.txt"), encoding="utf-8-sig") as fh:
        shape_ids = {t["shape_id"] for t in csv.DictReader(fh) if t["route_id"] in acela and t["shape_id"]}
    pts = {}
    with open(os.path.join(amtrak, "shapes.txt"), encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["shape_id"] in shape_ids:
                pts.setdefault(r["shape_id"], []).append(
                    (int(r["shape_pt_sequence"]), float(r["shape_pt_lon"]), float(r["shape_pt_lat"])))
    hsr = [TO_M(LineString([(x, y) for _, x, y in sorted(v)])) for v in pts.values()]
    hsr_in = unary_union(hsr).intersection(city_limit)
    feats.append(feature(multiline(lines_of(hsr_in)), key="hsr"))
    for f in feats:
        g = TO_M(shape(f["geometry"]))
        print(f"  {f['properties']['key']}: {g.length / M_PER_MI:.1f} mi in {len(g.geoms)} pieces")
    write("nyc.measure-features.geojson.json", feats)


if __name__ == "__main__":
    main()
