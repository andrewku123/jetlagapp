#!/usr/bin/env python3
"""Fetch rail transit line geometry (BART, Muni Metro, VTA, Caltrain) from OSM
Overpass and emit a trimmed GeoJSON FeatureCollection for the map overlay.

Each feature is a LineString with properties {system, color}. Caltrain is
collapsed to a single line/color. Other systems use the route's official
`colour` tag (Google-Maps-style), with sensible fallbacks.
"""
import json
import math
import sys
import time
import urllib.request

OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = "36.9,-122.7,38.25,-121.4"

QUERY = f"""
[out:json][timeout:240];
(
  relation["route"~"subway|light_rail|tram|train"]({BBOX});
);
out geom;
"""

# Google-Maps-style fallbacks per system when a route has no colour tag.
FALLBACK = {
    "BART": "#0099d8",
    "Muni": "#b41f24",
    "VTA": "#1a73e8",
}
CALTRAIN_COLOR = "#9b1b30"
# BART Oakland Airport Connector (Coliseum–OAK) — the "Silver" line.
SILVER_COLOR = "#8a9099"

# Per-system color overrides. VTA's orange (#f79729) is too close to BART's
# orange (#faa61a); shift it to a distinct, brighter orange.
COLOR_REMAP = {
    "VTA": {"#f79729": "#ea580c"},
}


def matches(tags):
    """Return system name if this relation is one we want, else None."""
    op = (tags.get("operator", "") + " " + tags.get("network", "") + " " + tags.get("name", "")).lower()
    route = tags.get("route", "")
    # exclude cable cars (SF Powell/California lines) from the overlay
    if route == "cable_car" or "cable car" in op or "cable_car" in op:
        return None
    if "caltrain" in op or "peninsula corridor" in op:
        return "Caltrain"
    if route == "subway" and ("bart" in op or "bay area rapid" in op):
        return "BART"
    if route in ("light_rail", "tram") and ("muni" in op or "san francisco municipal" in op or "sfmta" in op):
        return "Muni"
    if route == "light_rail" and ("vta" in op or "santa clara valley" in op):
        return "VTA"
    return None


def fetch():
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request(OVERPASS, data=data, headers={"User-Agent": "bayarea-hideandseek/1.0 (transit-overlay)"})
            with urllib.request.urlopen(req, timeout=260) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            print(f"  attempt {attempt+1} failed: {e}", file=sys.stderr)
            time.sleep(5)
    raise SystemExit("Overpass fetch failed")


def round_coords(coords):
    return [[round(x, 5), round(y, 5)] for x, y in coords]


def color_of(system, tags):
    if system == "Caltrain":
        return CALTRAIN_COLOR
    color = tags.get("colour") or tags.get("color") or FALLBACK.get(system, "#666")
    color = color if color.startswith("#") else "#" + color
    return COLOR_REMAP.get(system, {}).get(color.lower(), color)


# Two tracks within this many metres of each other along their shared extent are
# treated as the same corridor (the two ~13m-apart direction tracks, stacked
# BART/Muni tunnels, or a short way lying on top of a longer one).
MERGE_TOL_M = 35.0
# reference latitude for the metres-per-degree conversion (Bay Area)
_MX = 111320.0 * math.cos(math.radians(37.7))
_MY = 110540.0


def resample(coords, n):
    """Return n points evenly spaced (by arc length) along a polyline."""
    if len(coords) <= 1:
        return coords
    seg = [math.dist(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]
    total = sum(seg) or 1.0
    out = [coords[0]]
    for k in range(1, n):
        target = total * k / (n - 1)
        acc = 0.0
        for i, d in enumerate(seg):
            if acc + d >= target:
                t = (target - acc) / (d or 1.0)
                ax, ay = coords[i]
                bx, by = coords[i + 1]
                out.append([ax + (bx - ax) * t, ay + (by - ay) * t])
                break
            acc += d
        else:
            out.append(coords[-1])
    return out


def _pt_seg_m(p, a, b):
    """Distance (metres) from point p to segment a-b, in lon/lat degrees."""
    px, py = (p[0] - a[0]) * _MX, (p[1] - a[1]) * _MY
    bx, by = (b[0] - a[0]) * _MX, (b[1] - a[1]) * _MY
    d2 = bx * bx + by * by
    t = 0.0 if d2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / d2))
    return math.hypot(px - bx * t, py - by * t)


def _covered_by(sample, poly):
    """True if every point of `sample` lies within MERGE_TOL_M of polyline `poly`."""
    for p in sample:
        best = min(_pt_seg_m(p, poly[i], poly[i + 1]) for i in range(len(poly) - 1))
        if best > MERGE_TOL_M:
            return False
    return True


def merge_colocated(entries):
    """Collapse co-located tracks (NB/SB direction pairs, stacked tunnels, and
    sub-segments lying on a longer way) into a single representative centerline,
    unioning the colors that run along it."""
    # longest first so shorter overlapping ways fold into the full corridor
    entries = sorted(entries, key=lambda e: -len(e["geom"]))
    samples = [resample(e["geom"], 8) for e in entries]
    out = []
    reps = []  # (geom, sample) for each kept group
    for e, s in zip(entries, samples):
        merged = False
        for g, (gg, gs) in zip(out, reps):
            if _covered_by(s, gg) or _covered_by(gs, e["geom"]):
                for c in e["colors"]:
                    if c not in g["colors"]:
                        g["colors"].append(c)
                merged = True
                break
        if not merged:
            grp = {"geom": e["geom"], "system": e["system"], "colors": list(e["colors"])}
            out.append(grp)
            reps.append((e["geom"], s))
    return out


def main():
    raw = fetch()
    rels = []
    for el in raw.get("elements", []):
        if el.get("type") != "relation":
            continue
        system = matches(el.get("tags", {}))
        if system:
            rels.append((system, el))

    # Group by physical OSM way: way_id -> { geometry, system, colors:set }.
    # Multiple line colors on one way means those lines interline (share track).
    # Caltrain is grouped on its own so it never merges with another system's
    # tracks and always renders as a single line.
    ways = {}
    caltrain = {}
    seen_systems = {}
    for system, el in rels:
        seen_systems[system] = seen_systems.get(system, 0) + 1
        color = color_of(system, el.get("tags", {}))
        bucket = caltrain if system == "Caltrain" else ways
        for m in el.get("members", []):
            if m.get("type") != "way" or not m.get("geometry"):
                continue
            way_id = m.get("ref")
            entry = bucket.get(way_id)
            if entry is None:
                line = [[p["lon"], p["lat"]] for p in m["geometry"]]
                if len(line) < 2:
                    continue
                entry = bucket[way_id] = {"geom": line, "system": system, "colors": []}
            if color not in entry["colors"]:
                entry["colors"].append(color)

    # Collapse the two direction tracks (and stacked tunnels) of each corridor
    # into a single representative centerline so a route shows as one line.
    merged = merge_colocated(list(ways.values())) + merge_colocated(list(caltrain.values()))

    # One feature per merged track, carrying the base geometry and the list of
    # line colors that run on it. The app computes parallel offsets at render
    # time (so interlining can be toggled on/off instantly).
    feats = []
    for entry in merged:
        feats.append({
            "type": "Feature",
            "properties": {"system": entry["system"], "colors": sorted(entry["colors"])},
            "geometry": {"type": "LineString", "coordinates": round_coords(entry["geom"])},
        })
    # OAK Airport Connector (Coliseum -> OAK): an automated guideway that is not
    # part of the rail route relations above, so add it explicitly as the Silver
    # line using the saved alignment.
    try:
        with open("scripts/oak_connector.json") as f:
            oak = json.load(f)
        if len(oak) >= 2:
            feats.append({
                "type": "Feature",
                "properties": {"system": "BART", "colors": [SILVER_COLOR]},
                "geometry": {"type": "LineString", "coordinates": round_coords(oak)},
            })
    except FileNotFoundError:
        pass

    out = {"type": "FeatureCollection", "features": feats}
    path = "src/data/transit-lines.geojson.json"
    with open(path, "w") as f:
        json.dump(out, f)
    print(f"systems: {seen_systems}")
    print(f"features: {len(feats)} -> {path}")


if __name__ == "__main__":
    import urllib.parse
    main()
