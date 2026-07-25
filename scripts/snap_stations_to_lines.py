#!/usr/bin/env python3
"""Snap each LA station coordinate to the closest point on the transit line(s) it
serves, so the dot sits exactly on the drawn line. The station coordinate is the
single source of truth for BOTH the rendered dot and the game logic, so snapping
it moves both together (the user's "snap both to the line").

Coordinate-derived baked fields are re-derived from the snapped point so the game
stays consistent with where the dot now sits:
  - airportDist / nearestAirport : pure haversine (R = 6,371,000 m, matches build)
  - county / city                : local point-in-polygon on the bundled geojson
Fields resolved from the coordinate at runtime (match-city via cityAt, measure-zip
via zipAt) need no baking. Elevation moves sub-metre for these tiny snaps and is
left as-is (no offline DEM). Run from repo root: python3 scripts/snap_stations_to_lines.py
"""
import json
import math
import os

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "src", "data")

R = 6371000.0
AIRPORTS = {"LAX": (33.94256, -118.40853), "LGB": (33.81765, -118.15227)}
CITY_SNAP_M = 150.0  # mirror cityAt()'s boundary-erosion snap

# transit-line feature colour -> line name (empirically derived, see session)
CMAP = {
    "#0072bc": "A Line", "#e3131b": "B Line", "#58a738": "C Line",
    "#a05da5": "D Line", "#f7b618": "E Line", "#fc4c02": "G Line",
    "#adb8bf": "J Line", "#e96bb0": "K Line",
}


def load(name):
    with open(os.path.join(DATA, name)) as fh:
        return json.load(fh)


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dla, dlo = la2 - la1, lo2 - lo1
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def line_parts(feat):
    g = feat["geometry"]
    return [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]


def snap(lat, lon, lines, byline):
    """Nearest point (lat, lon) on the union of the station's own lines."""
    cr = math.cos(math.radians(lat))
    px, py = lon * cr, lat
    best = (float("inf"), lat, lon)
    for ln in lines:
        for part in byline.get(ln, []):
            for i in range(len(part) - 1):
                ax, ay = part[i][0] * cr, part[i][1]
                bx, by = part[i + 1][0] * cr, part[i + 1][1]
                dx, dy = bx - ax, by - ay
                if dx == 0 and dy == 0:
                    t = 0.0
                else:
                    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
                qx, qy = ax + t * dx, ay + t * dy
                d = math.hypot(px - qx, py - qy)
                if d < best[0]:
                    best = (d, qy, qx / cr)
    return best[1], best[2]


def ring_contains(lat, lon, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def polys_of(feat):
    g = feat["geometry"]
    if g["type"] == "Polygon":
        return [g["coordinates"]]
    if g["type"] == "MultiPolygon":
        return g["coordinates"]
    return []


def contains(lat, lon, feat):
    for poly in polys_of(feat):
        if not ring_contains(lat, lon, poly[0]):
            continue
        if not any(ring_contains(lat, lon, poly[h]) for h in range(1, len(poly))):
            return True
    return False


def dist_to_feat_m(lat, lon, feat):
    cr = math.cos(math.radians(lat))
    px, py = lon * cr, lat
    best = float("inf")
    for poly in polys_of(feat):
        for ring in poly:
            for i in range(len(ring) - 1):
                ax, ay = ring[i][0] * cr, ring[i][1]
                bx, by = ring[i + 1][0] * cr, ring[i + 1][1]
                dx, dy = bx - ax, by - ay
                if dx == 0 and dy == 0:
                    t = 0.0
                else:
                    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
                d = math.hypot(px - (ax + t * dx), py - (ay + t * dy)) * 111320.0
                if d < best:
                    best = d
    return best


def place_at(lat, lon, places, fallback):
    for f in places["features"]:
        if contains(lat, lon, f):
            return f["properties"]["name"]
    best, best_d = fallback, CITY_SNAP_M
    for f in places["features"]:
        d = dist_to_feat_m(lat, lon, f)
        if d < best_d:
            best_d, best = d, f["properties"]["name"]
    return best


def county_at(lat, lon, counties, fallback):
    for f in counties["features"]:
        if contains(lat, lon, f):
            return f["properties"]["name"]
    return fallback


def main():
    sts = load("la.stations.json")
    tl = load("la.transit-lines.geojson.json")
    places = load("la.places.geojson.json")
    counties = load("la.counties.geojson.json")
    byline = {CMAP[f["properties"]["colors"][0]]: line_parts(f) for f in tl["features"]}

    moved = 0
    for s in sts:
        nlat, nlon = snap(s["lat"], s["lon"], s["lines"], byline)
        d = hav((s["lat"], s["lon"]), (nlat, nlon))
        if d > 0.5:
            moved += 1
        s["lat"] = round(nlat, 6)
        s["lon"] = round(nlon, 6)
        s["airportDist"] = {k: round(hav((nlat, nlon), v), 1) for k, v in AIRPORTS.items()}
        s["nearestAirport"] = min(AIRPORTS, key=lambda k: s["airportDist"][k])
        s["county"] = county_at(nlat, nlon, counties, s.get("county"))
        s["city"] = place_at(nlat, nlon, places, s.get("city"))

    with open(os.path.join(DATA, "la.stations.json"), "w") as fh:
        json.dump(sts, fh, ensure_ascii=False)
    print(f"snapped {moved}/{len(sts)} stations (>0.5 m); rebaked airport/city/county")


if __name__ == "__main__":
    main()
