#!/usr/bin/env python3
"""Build the NYC map's transit-line overlay from the agencies' GTFS shapes.

One feature per colour on the official MTA map: subway services that share a
trunk share a colour (A/C/E are all 8 Av blue), so they are one feature, named
for the trunk ("8 Av: A C E"). The three shuttles share shuttle grey. Each LIRR
branch in play (re-traced on OSM track, see on_track), each NYC Ferry route,
SIR, the Staten Island Ferry and the Roosevelt Island Tram are their own
features. LIRR geometry is clipped to the
city (plus CLIP_DEG, so the line visibly leaves the map) minus Nassau, plus the
endgame area around every station (ENDGAME_M). An NYC Ferry route is
drawn only between its landings that are stations, so no ferry line runs past
nothing but non-station piers (Rockaway, Soundview, ...).

    python3 scripts/build_nyc_transit_lines.py   # after build_nyc_stations.py
"""
import csv
import heapq
import json
import os

from shapely.geometry import LineString, mapping, shape
from shapely.geometry import Point
from shapely.ops import linemerge, substring, unary_union

import build_nyc_geo as geo
import build_nyc_stations as st
import poi_geo

OUT = poi_geo.repo_path("nyc", "transitLines")
OSM_RAIL = os.path.join(os.path.dirname(__file__), "measure_src", "osm_rail_nyc.geojson")
OSM_WATER = os.path.join(os.path.dirname(__file__), "measure_src", "osm_ferry_tram_nyc.geojson")
# NYC Ferry GTFS route_long_name -> refs of its OSM route relations.
OSM_FERRY_REFS = {"Astoria": {"AST"}, "East River": {"ER"}, "Rockaway-Soundview": {"RWS"},
                  "South Brooklyn": {"SBK"}, "St. George": {"STG"}}
TRACK_NEAR_M = 60  # OSM track this close to a GTFS shape can carry it
GTFS_COST = 4  # cost per metre of falling back to the GTFS line, vs 1 for track
CLIP_DEG = 0.015
# Endgame hiding zone at its largest: 0.25 mi x 1.5^2 (Curse of the Prosperous
# Home drawn once and duplicated). The endgame area is the play area plus this
# around every station.
ENDGAME_M = 0.25 * 1.5 ** 2 * 1609.344
SIMPLIFY_DEG = 0.00008  # ~8 m
LANDING_SNAP_DEG = 0.002  # a station landing within ~200 m of a ferry shape is on it
FADED_OVERLAP_DEG = 0.0008  # a route leg this close to a solid one is the same stretch
LEG_DETOUR = 1.6  # A-B-C replaces a direct A-C leg when at most this much longer


def between_stations(lines, pts):
    """One line per pair of consecutive station landings along the route's shapes,
    so trip variants that drift apart in the river draw as a single line. A leg
    that runs past another landing (A-C next to A-B-C) is dropped in favour of the
    legs through it."""
    legs = {}
    for line in lines:
        on = sorted((line.project(p), i) for i, p in enumerate(pts)
                    if line.distance(p) <= LANDING_SNAP_DEG)
        for (da, a), (db, b) in zip(on, on[1:]):
            if db > da and a != b:
                mid = list(substring(line, da, db).coords)[1:-1]
                leg = LineString([pts[a].coords[0], *mid, pts[b].coords[0]])
                key = frozenset((a, b))
                if key not in legs or leg.length < legs[key].length:
                    legs[key] = leg
    for key in sorted(legs, key=lambda k: -legs[k].length):
        a, c = tuple(key)
        for b in range(len(pts)):
            ab, bc = legs.get(frozenset((a, b))), legs.get(frozenset((b, c)))
            if ab is not None and bc is not None and ab.length + bc.length <= LEG_DETOUR * legs[key].length:
                del legs[key]
                break
    return list(legs.values())

# MTA's published trunk colours.
SUBWAY_TRUNKS = [
    ("8 Av: A C E", "#0039a6", ["A", "C", "E"]),
    ("6 Av: B D F M", "#ff6319", ["B", "D", "F", "FX", "M"]),
    ("Crosstown: G", "#6cbe45", ["G"]),
    ("Nassau St: J Z", "#996633", ["J", "Z"]),
    ("14 St-Canarsie: L", "#a7a9ac", ["L"]),
    ("Broadway: N Q R W", "#fccc0a", ["N", "Q", "R", "W"]),
    ("Shuttles: S", "#808183", ["GS", "FS", "H"]),
    ("Broadway-7 Av: 1 2 3", "#ee352e", ["1", "2", "3"]),
    ("Lexington Av: 4 5 6", "#00933c", ["4", "5", "6", "6X"]),
    ("Flushing: 7", "#b933ad", ["7", "7X"]),
]
SIR = ("Staten Island Railway", "#1d2f6f", ["SI"])


def rows(d, f):
    with open(os.path.join(d, f), encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def route_landings(d):
    """route_id -> [Point] of every stop its trips serve."""
    stops = {r["stop_id"]: Point(float(r["stop_lon"]), float(r["stop_lat"])) for r in rows(d, "stops.txt")}
    route_of = {t["trip_id"]: t["route_id"] for t in rows(d, "trips.txt")}
    ids = {}
    for r in rows(d, "stop_times.txt"):
        ids.setdefault(route_of.get(r["trip_id"]), set()).add(r["stop_id"])
    return {rid: [stops[i] for i in sorted(ss) if i in stops] for rid, ss in ids.items()}


def route_shapes(d):
    """route_id -> [LineString] of every distinct shape its trips run."""
    sids = {}
    for t in rows(d, "trips.txt"):
        if t.get("shape_id"):
            sids.setdefault(t["route_id"], set()).add(t["shape_id"])
    pts = {}
    for r in rows(d, "shapes.txt"):
        pts.setdefault(r["shape_id"], []).append(
            (int(r["shape_pt_sequence"]), float(r["shape_pt_lon"]), float(r["shape_pt_lat"])))
    lines = {sid: LineString([(x, y) for _, x, y in sorted(v)]) for sid, v in pts.items() if len(v) > 1}
    return {rid: [lines[s] for s in ss if s in lines] for rid, ss in sids.items()}


def points_per_km(lines):
    km = sum(geo.TO_M(l).length for l in lines) / 1000
    return sum(len(l.coords) for l in lines) / km if km else 0


def denser(gtfs, osm, landings):
    """Whichever of two drawings of a route has more points per km, so it follows
    the real path; OSM only if it passes every landing."""
    reaches = all(any(l.distance(p) <= LANDING_SNAP_DEG for l in osm) for p in landings)
    return osm if osm and reaches and points_per_km(osm) > points_per_km(gtfs) else gtfs


def osm_lines(f):
    g = linemerge(shape(f["geometry"])) if f["geometry"]["type"] == "MultiLineString" else shape(f["geometry"])
    return list(getattr(g, "geoms", [g]))


def connected_to(g, pts, tol=0.003):
    """The parts of g joined (through each other) to a part within tol of pts."""
    joined = unary_union([p.buffer(1e-5) for p in getattr(g, "geoms", [g])])
    groups = getattr(joined, "geoms", [joined])
    keep = unary_union([grp for grp in groups if any(grp.distance(p) < tol for p in pts)])
    return unary_union([p for p in getattr(g, "geoms", [g]) if p.intersects(keep)])


def on_track(lines, clip, arcs):
    """Each GTFS shape, cut to the clip, re-traced on OSM track (arcs, in metres):
    the cheapest path between its ends over track near it, preferring the
    closest track and track another of the line's shapes already took, so
    variants don't spread over parallel tracks. Where OSM has no usable track
    the path falls back to the GTFS line itself, at a higher cost. LIRR shapes
    only have a point every ~60 m and cut corners; OSM has one every ~30 m."""
    used, extra = set(), []
    for line in lines:
        cut = line.intersection(clip)
        for piece in getattr(cut, "geoms", [cut]):
            if piece.geom_type != "LineString" or piece.length == 0:
                continue
            guide = geo.TO_M(piece)
            adj = {}

            def edge(u, v, w, what):
                adj.setdefault(u, []).append((v, w, what))
                adj.setdefault(v, []).append((u, w, what))
            for i, a in enumerate(arcs):
                if guide.distance(a) > TRACK_NEAR_M:
                    continue
                off = sum(guide.distance(Point(c)) for c in a.coords) / len(a.coords)
                edge(a.coords[0], a.coords[-1],
                     a.length * (1 + off / 15) * (0.3 if i in used else 1), i)
            track_nodes = list(adj)
            gc = list(guide.coords)
            for u, v in zip(gc, gc[1:]):
                edge(u, v, Point(u).distance(Point(v)) * GTFS_COST, LineString([u, v]))
            for u in gc:
                near = [n for n in track_nodes if Point(n).distance(Point(u)) <= TRACK_NEAR_M]
                if near:
                    n = min(near, key=lambda n: Point(n).distance(Point(u)))
                    edge(u, n, Point(n).distance(Point(u)) * GTFS_COST, LineString([u, n]))
            start, goal = gc[0], gc[-1]
            dist, prev, pq = {start: 0}, {}, [(0, 0, start)]
            k = 0
            while pq:
                d, _, u = heapq.heappop(pq)
                if u == goal:
                    break
                if d > dist[u]:
                    continue
                for v, w, what in adj[u]:
                    if d + w < dist.get(v, float("inf")):
                        dist[v], prev[v] = d + w, (u, what)
                        k += 1
                        heapq.heappush(pq, (d + w, k, v))
            u = goal
            while u != start:
                u, what = prev[u]
                if isinstance(what, int):
                    used.add(what)
                else:
                    extra.append(what)
    geoms = [arcs[i] for i in used] + extra
    return [geo.TO_LL(unary_union(geoms))] if geoms else []


def feature(system, color, name, lines, clip=None, stops=None):
    g = unary_union(lines)
    if clip is not None:
        g = g.intersection(clip)
    if stops is not None:
        g = connected_to(g, stops)
    g = linemerge(g) if g.geom_type == "MultiLineString" else g
    g = g.simplify(SIMPLIFY_DEG)
    geom = mapping(g)
    geom["coordinates"] = json.loads(json.dumps(geom["coordinates"]),
                                     parse_float=lambda v: round(float(v), 6))
    return {"type": "Feature", "properties": {"system": system, "colors": [color], "name": name},
            "geometry": geom}


def main():
    city = unary_union([shape(f["geometry"]) for f in json.load(open(st.BOROUGHS))["features"]])
    # Nassau is cut out so the Far Rockaway Branch's loop through Lawrence and
    # Inwood isn't drawn; the buffer only keeps tunnels and bridges into the city.
    nassau = unary_union([g for _, g in geo.shp_records(geo.TIGER_COUNTY, lambda r: r["GEOID"] == "36059")])
    clip = city.buffer(CLIP_DEG).difference(nassau)
    feats = []
    sub = route_shapes(st.feed("gtfs_subway"))
    for name, color, routes in SUBWAY_TRUNKS:
        feats.append(feature("Subway", color, name, [l for r in routes for l in sub.get(r, [])]))
    feats.append(feature("SIR", SIR[1], SIR[0], [l for r in SIR[2] for l in sub[r]]))

    lirr = st.feed("gtfslirr")
    lirr_meta = {r["route_id"]: r for r in rows(lirr, "routes.txt")}
    lirr_sh = route_shapes(lirr)
    arcs = [geo.TO_M(shape(f["geometry"])) for f in json.load(open(OSM_RAIL))["features"]]
    stations = json.load(open(st.OUT))
    endgame = geo.TO_LL(unary_union([geo.TO_M(Point(s["lon"], s["lat"])).buffer(ENDGAME_M)
                                     for s in stations]))
    lirr_clip = clip.union(endgame)
    for rid, name in st.LIRR_BRANCHES.items():
        # A stretch cut off from every station of its branch (Far Rockaway, past
        # Nassau, isn't hourly) isn't drawn.
        stops = [Point(s["lon"], s["lat"]) for s in stations if name in s["lines"]]
        feats.append(feature("LIRR", "#" + lirr_meta[rid]["route_color"].lower(), name,
                             on_track(lirr_sh[rid], lirr_clip, arcs), lirr_clip, stops))

    fer = st.feed("nycferry")
    ferry_lines = {l for s in stations for l in s["lines"] if l.startswith("NYC Ferry ")}
    water = json.load(open(OSM_WATER))["features"]
    landings = route_landings(fer)
    fer_sh = {}
    for rid, lines in route_shapes(fer).items():
        name = next(r["route_long_name"] for r in rows(fer, "routes.txt") if r["route_id"] == rid)
        osm = [l for f in water if f["properties"].get("operator") == "Hornblower Cruises"
               and f["properties"]["ref"] in OSM_FERRY_REFS.get(name, ()) for l in osm_lines(f)]
        fer_sh[rid] = denser(lines, osm, landings[rid])
    for r in rows(fer, "routes.txt"):
        name = "NYC Ferry " + r["route_long_name"]
        if r["route_type"] == "4" and name in ferry_lines:
            color = "#" + r["route_color"].lower()
            pts = [Point(s["lon"], s["lat"]) for s in stations if name in s["lines"]]
            cut = between_stations(fer_sh[r["route_id"]], pts)
            if cut:
                feats.append(feature("NYC Ferry", color, name, cut))
            # The rest of the route, past its counting stations, drawn faded so
            # a station's ferry visibly goes somewhere (no dots at those landings).
            solid = unary_union(cut) if cut else None
            rest = [l for l in between_stations(fer_sh[r["route_id"]], landings[r["route_id"]])
                    if solid is None or l.interpolate(0.5, normalized=True).distance(solid) > FADED_OVERLAP_DEG]
            if rest:
                f = feature("NYC Ferry", color, name, rest)
                f["properties"]["faded"] = True
                feats.append(f)

    (_, la, lo), (_, lb, lob) = st.SI_FERRY
    ends = [Point(lo, la), Point(lob, lb)]
    sif = [l for f in water if f["properties"].get("ref") == "SIF" for l in osm_lines(f)]
    feats.append(feature("Staten Island Ferry", "#f58220", "Staten Island Ferry",
                         between_stations(denser([LineString(ends)], sif, ends), ends)))
    (_, la, lo), (_, lb, lob) = st.TRAM
    ends = [Point(lo, la), Point(lob, lb)]
    tram = [l for f in water if f["properties"]["name"] == "Roosevelt Island Tramway" for l in osm_lines(f)]
    feats.append(feature("Roosevelt Island Tram", "#c60c30", "Roosevelt Island Tram",
                         denser([LineString(ends)], tram, ends)))
    json.dump({"type": "FeatureCollection", "features": feats}, open(OUT, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(feats)} lines, {os.path.getsize(OUT) // 1024} KB")


if __name__ == "__main__":
    main()
