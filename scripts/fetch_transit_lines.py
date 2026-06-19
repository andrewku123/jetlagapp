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


# The Muni Metro lines we draw. The S ("S-Shuttle") is a special/peak shuttle
# that overlays the Embarcadero alongside N/F and is excluded from the station
# data too — keep it out of the overlay so it doesn't double the N's line.
MUNI_LINES = {"F", "J", "K", "L", "M", "N", "T"}


def matches(tags):
    """Return system name if this relation is one we want, else None.

    Classification uses only operator/network — NOT the route name. The name
    can mention another system's station (e.g. Muni Metro N's name ends
    "=> Caltrain" because it terminates at the Caltrain depot), which would
    otherwise misclassify the line and drop it from the overlay."""
    op = (tags.get("operator", "") + " " + tags.get("network", "")).lower()
    name = tags.get("name", "").lower()
    route = tags.get("route", "")
    ref = tags.get("ref", "")
    # exclude cable cars (SF Powell/California lines) from the overlay
    if route == "cable_car" or "cable car" in name or "cable_car" in name:
        return None
    if "caltrain" in op or "peninsula corridor" in op:
        return "Caltrain"
    # BART includes eBART (Pittsburg/Bay Point–Antioch), which OSM tags as
    # route=light_rail, so accept both subway and light_rail for BART.
    if route in ("subway", "light_rail") and ("bart" in op or "bay area rapid" in op):
        return "BART"
    if route in ("light_rail", "tram") and ("muni" in op or "san francisco municipal" in op or "sfmta" in op):
        return "Muni" if ref in MUNI_LINES else None
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


# reference latitude for the metres-per-degree conversion (Bay Area)
_MX = 111320.0 * math.cos(math.radians(37.7))
_MY = 110540.0


def _dist_m(a, b):
    return math.hypot((a[0] - b[0]) * _MX, (a[1] - b[1]) * _MY)


def chain_len_m(coords):
    return sum(_dist_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


# ways whose endpoints are within this distance are treated as joined (also
# bridges the small gaps OSM sometimes leaves between consecutive ways)
STITCH_TOL_M = 25.0
# after stitching, chains of the same line whose endpoints are within this gap
# are joined (closes small breaks where a connecting way was missing/dropped)
BRIDGE_TOL_M = 350.0
# stitched chains shorter than this are dropped as strays (yards, crossovers,
# station passing tracks); real branches are far longer
STRAY_MIN_M = 800.0


def _heading(a, b):
    return math.atan2((b[1] - a[1]) * _MY, (b[0] - a[0]) * _MX)


def _angdiff(h1, h2):
    d = (h1 - h2 + math.pi) % (2 * math.pi) - math.pi
    return abs(d)


def stitch_ways(geoms):
    """Join polylines that meet end-to-end into maximal continuous chains.

    At a junction (where more than one way meets the chain's current end) the
    *straightest* continuation is chosen, so the mainline stays together and a
    short spur/siding is left as its own (later dropped) chain rather than
    derailing the line."""
    remaining = [list(g) for g in geoms if len(g) >= 2]
    chains = []
    while remaining:
        chain = remaining.pop(0)
        while True:
            # try to extend the tail, then the head; pick straightest each time
            tail_h = _heading(chain[-2], chain[-1])
            cands = []
            for i, w in enumerate(remaining):
                if _dist_m(chain[-1], w[0]) <= STITCH_TOL_M:
                    cands.append((_angdiff(tail_h, _heading(w[0], w[1])), i, w[1:]))
                if _dist_m(chain[-1], w[-1]) <= STITCH_TOL_M:
                    rw = list(reversed(w))
                    cands.append((_angdiff(tail_h, _heading(rw[0], rw[1])), i, rw[1:]))
            if cands:
                _, i, tail = min(cands, key=lambda c: c[0])
                chain = chain + tail
                remaining.pop(i)
                continue
            head_h = _heading(chain[1], chain[0])
            cands = []
            for i, w in enumerate(remaining):
                if _dist_m(chain[0], w[-1]) <= STITCH_TOL_M:
                    cands.append((_angdiff(head_h, _heading(w[-1], w[-2])), i, w[:-1]))
                if _dist_m(chain[0], w[0]) <= STITCH_TOL_M:
                    rw = list(reversed(w))
                    cands.append((_angdiff(head_h, _heading(rw[-1], rw[-2])), i, rw[:-1]))
            if cands:
                _, i, head = min(cands, key=lambda c: c[0])
                chain = head + chain
                remaining.pop(i)
                continue
            break
        chains.append(chain)
    return chains


def bridge_chains(chains, tol):
    """Join chains whose nearest endpoints are within `tol`, closing small
    breaks (a missing/dropped connecting way) so a line reads continuous.

    Each pass joins the **globally closest** pair under `tol` (not just the first
    found), so raising `tol` doesn't cause a near pair to be skipped in favor of
    a worse early match — which would otherwise leave stray stubs behind."""
    chains = [list(c) for c in chains]
    while len(chains) > 1:
        best = None  # (gap, i, j, joined)
        for i in range(len(chains)):
            for j in range(i + 1, len(chains)):
                a, b = chains[i], chains[j]
                opts = [
                    (_dist_m(a[-1], b[0]), a + b),
                    (_dist_m(a[-1], b[-1]), a + list(reversed(b))),
                    (_dist_m(a[0], b[0]), list(reversed(b)) + a),
                    (_dist_m(a[0], b[-1]), b + a),
                ]
                gap, joined = min(opts, key=lambda o: o[0])
                if best is None or gap < best[0]:
                    best = (gap, i, j, joined)
        if best is None or best[0] > tol:
            break
        _, i, j, joined = best
        chains[i] = joined
        chains.pop(j)
    return chains


# a candidate branch counts as "already drawn" when most of its sampled points
# lie within this distance of an existing chain for the same line
COVER_TOL_M = 140.0
# final same-line bridge: chains here all belong to ONE line/color, so a larger
# gap can be closed safely (e.g. the F's Market/Embarcadero pieces, where the
# chosen direction relation drops a connecting way at a junction or loop).
LINE_BRIDGE_TOL_M = 650.0


def _min_dist_to_chains(p, chains):
    best = float("inf")
    for ch in chains:
        for q in ch:
            d = _dist_m(p, q)
            if d < best:
                best = d
    return best


def _covered(chain, chains, samples=24):
    """True if most of `chain` overlaps an existing chain (e.g. the opposite
    direction of the same line). Used to add genuine extensions/branches (eBART)
    while skipping reverse-direction duplicates that would just double the line."""
    if not chains:
        return False
    n = len(chain)
    idxs = {int(i * (n - 1) / (samples - 1)) for i in range(samples)}
    pts = [chain[i] for i in sorted(idxs)]
    near = sum(1 for p in pts if _min_dist_to_chains(p, chains) <= COVER_TOL_M)
    return near >= 0.6 * len(pts)


def build_line(rel_ways_list):
    """Build the continuous chains for one (system, color) from all its route
    relations. Start from the most-complete relation (a single direction, so no
    parallel doubling), then add chains from the other relations only where they
    cover ground the base doesn't (branches/extensions like eBART). Finally
    bridge so an extension joins the mainline."""
    rel_ways_list = sorted(rel_ways_list, key=lambda ws: -sum(chain_len_m(g) for g in ws))
    # Start from the most-complete relation's single longest continuous chain.
    # Add that relation's OTHER pieces only where they reach ground the mainline
    # doesn't (`_covered` skip). A line's relation often carries the running track
    # AND a parallel string of short stop/platform ways on the same alignment; if
    # we bridged those in, we'd draw a second straight-chord copy that cuts across
    # blocks instead of following the track (the F's Embarcadero "straight line"
    # bug). Dropping the covered pieces keeps only the real, road-following track.
    base = sorted(stitch_ways(rel_ways_list[0]), key=chain_len_m, reverse=True)
    chains = [base[0]]
    for ch in base[1:]:
        if not _covered(ch, chains):
            chains.append(ch)
    # Add genuine branches/extensions from the other relations (other direction,
    # short-turns, eBART) — again only where they aren't already drawn.
    for ways in rel_ways_list[1:]:
        for ch in bridge_chains(stitch_ways(ways), BRIDGE_TOL_M):
            if chain_len_m(ch) >= STRAY_MIN_M and not _covered(ch, chains):
                chains.append(ch)
    # Close genuine breaks (a dropped connecting way). Drop strays BEFORE the
    # generous same-line bridge so they can't daisy-chain into surviving junk;
    # the larger tolerance then only joins real same-line pieces.
    chains = bridge_chains(chains, BRIDGE_TOL_M)
    real = [c for c in chains if chain_len_m(c) >= STRAY_MIN_M]
    return bridge_chains(real, LINE_BRIDGE_TOL_M)


def main():
    raw = fetch()
    rels = []
    for el in raw.get("elements", []):
        if el.get("type") != "relation":
            continue
        system = matches(el.get("tags", {}))
        if system:
            rels.append((system, el))

    # Group by LINE = (system, color). A line has several route relations: one
    # per direction plus service variants/extensions (short-turns, eBART). Each
    # relation is a single linear direction whose member ways run in order and
    # share end nodes — perfect for stitching with no parallel doubling. We build
    # from the most-complete relation, then add only the parts other relations
    # cover that it doesn't (branches/extensions, e.g. eBART to Antioch). See
    # build_line(). Caltrain (single color) naturally forms one line.
    def rel_ways(el):
        out = []
        for m in el.get("members", []):
            if m.get("type") != "way" or not m.get("geometry"):
                continue
            geom = [[p["lon"], p["lat"]] for p in m["geometry"]]
            if len(geom) >= 2:
                out.append(geom)
        return out

    lines = {}
    seen_systems = {}
    for system, el in rels:
        seen_systems[system] = seen_systems.get(system, 0) + 1
        color = color_of(system, el.get("tags", {}))
        lines.setdefault((system, color), []).append(rel_ways(el))

    # Build each line's continuous chains; drop tiny stray fragments (a relation
    # can include a short non-revenue spur).
    merged = []
    for (system, color), rel_ways_list in lines.items():
        for chain in build_line(rel_ways_list):
            if chain_len_m(chain) >= STRAY_MIN_M:
                merged.append({"geom": chain, "system": system, "colors": [color]})

    # One feature per continuous line chain.
    feats = []
    for entry in merged:
        feats.append({
            "type": "Feature",
            "properties": {"system": entry["system"], "colors": entry["colors"]},
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
