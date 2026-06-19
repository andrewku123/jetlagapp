#!/usr/bin/env python3
"""Fetch rail transit line geometry (BART, Muni Metro, VTA, Caltrain) from OSM
Overpass and emit a trimmed GeoJSON FeatureCollection for the map overlay.

Each feature is a LineString with properties {system, color}. Caltrain is
collapsed to a single line/color. Other systems use the route's official
`colour` tag (Google-Maps-style), with sensible fallbacks.
"""
import json
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


def matches(tags):
    """Return system name if this relation is one we want, else None."""
    op = (tags.get("operator", "") + " " + tags.get("network", "") + " " + tags.get("name", "")).lower()
    route = tags.get("route", "")
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


def main():
    raw = fetch()
    # Process BART/VTA/Muni before Caltrain so colored branch ways win shared
    # track; dedupe each physical way (by OSM id) so shared track is drawn once.
    order = {"BART": 0, "VTA": 1, "Muni": 2, "Caltrain": 3}
    rels = []
    for el in raw.get("elements", []):
        if el.get("type") != "relation":
            continue
        system = matches(el.get("tags", {}))
        if system:
            rels.append((order[system], system, el))
    rels.sort(key=lambda t: t[0])

    feats = []
    seen_systems = {}
    seen_ways = set()
    for _, system, el in rels:
        tags = el.get("tags", {})
        if system == "Caltrain":
            color = CALTRAIN_COLOR
        else:
            color = tags.get("colour") or tags.get("color") or FALLBACK.get(system, "#666")
            if not color.startswith("#"):
                color = "#" + color
        seen_systems[system] = seen_systems.get(system, 0) + 1
        for m in el.get("members", []):
            if m.get("type") != "way":
                continue
            way_id = m.get("ref")
            if way_id in seen_ways:
                continue
            geom = m.get("geometry")
            if not geom:
                continue
            line = round_coords([(p["lon"], p["lat"]) for p in geom])
            if len(line) < 2:
                continue
            seen_ways.add(way_id)
            feats.append({
                "type": "Feature",
                "properties": {"system": system, "color": color},
                "geometry": {"type": "LineString", "coordinates": line},
            })
    out = {"type": "FeatureCollection", "features": feats}
    path = "src/data/transit-lines.geojson.json"
    with open(path, "w") as f:
        json.dump(out, f)
    print(f"systems: {seen_systems}")
    print(f"features: {len(feats)} -> {path}")


if __name__ == "__main__":
    import urllib.parse
    main()
