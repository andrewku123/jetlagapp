#!/usr/bin/env python3
"""LA per-city (Census "place") polygons for the Matching -> city question.

Output: src/data/la.places.geojson.json — a FeatureCollection of Polygon /
MultiPolygon features, one per in-play Census place, `properties.name` = Census
NAMELSAD (e.g. "Los Angeles city", "East Los Angeles CDP").

Same shape/logic as build_city_places.py (Bay Area): emit EVERY Census place
that lies inside the play area (city, town OR CDP), each clipped to the play-area
polygon. No SFO-style airport-ownership override (LA has no equivalent quirk).

Source: Census TIGER/Line 2023 CA places (shared _census_place cache).
"""
import io, json, math, os, sys, zipfile, urllib.request
import shapely
from shapely.geometry import shape, mapping, box, Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union
import fetch_la_rivers

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "src", "data")
CACHE = os.path.join(HERE, "..", "..", "app-mainpr", "scripts", "_census_place")
PLAY_AREA = os.path.join(DATA, "la.play-area.geojson.json")
PLACE_URL = "https://www2.census.gov/geo/tiger/TIGER2023/PLACE/tl_2023_06_place.zip"
PLACE_STEM = "tl_2023_06_place"
SIMPLIFY_DEG = 0.0002
MIN_AREA_DEG2 = 1e-7

# River-fold tuning: rivers/washes are unincorporated gaps in the Census places,
# so we fold each river's in-play area into the cities on its banks (split down
# the middle) to keep the city-matching shading gap-free. Cosmetic only:
# elimination still resolves each station through the same polygons.
RIVER_CELL_M = 12.0       # raster resolution of the fill split
RIVER_BOUND_STEP_M = 15.0  # city-boundary sampling step for nearest-bank test
RIVER_NEAR_M = 130.0       # a bank city must be within this of a fill cell
RIVER_MIN_COMP_KM2 = 0.0008


def polygonal(g):
    if g.is_empty:
        return g
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    if isinstance(g, GeometryCollection):
        parts = [p for p in g.geoms if isinstance(p, (Polygon, MultiPolygon))]
        return unary_union(parts) if parts else Polygon()
    return Polygon()


def ensure_shapefile(url, stem):
    shp = os.path.join(CACHE, stem + ".shp")
    if os.path.exists(shp):
        return shp
    os.makedirs(CACHE, exist_ok=True)
    print(f"downloading {url} ...", file=sys.stderr)
    data = urllib.request.urlopen(url, timeout=180).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(CACHE)
    return shp


def load_play_area():
    fc = json.load(open(PLAY_AREA))
    g = shape(fc["features"][0]["geometry"])
    return g.buffer(0) if not g.is_valid else g


def fold_rivers(clipped, play):
    """Fold each river/wash's in-play area into the cities on its banks so the
    matching shading has no unincorporated-channel gaps. Splits the fill region
    down the middle between opposite banks via a nearest-city-boundary raster.
    Mutates `clipped` in place; returns km2 folded."""
    import numpy as np
    from scipy.spatial import cKDTree
    names = list(clipped)
    geoms = [clipped[n] for n in names]
    cities = unary_union(geoms)
    riv = fetch_la_rivers.load()
    ru = unary_union([shape(f["geometry"]).buffer(0) for f in riv["features"]]).intersection(play)
    fill = ru.difference(cities)
    if fill.is_empty:
        return 0.0

    lat0 = play.centroid.y
    mlat = 111320.0
    mlon = 111320.0 * math.cos(math.radians(lat0))

    # sample every city's boundary into metre points tagged with its index
    allpts, allidx = [], []
    for ci, g in enumerate(geoms):
        for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
            for ring in [poly.exterior, *poly.interiors]:
                arr = np.array([(x * mlon, y * mlat) for x, y in ring.coords])
                if len(arr) < 2:
                    continue
                seg = np.hypot(np.diff(arr[:, 0]), np.diff(arr[:, 1]))
                cum = np.concatenate([[0], np.cumsum(seg)])
                if cum[-1] == 0:
                    continue
                t = np.arange(0, cum[-1], RIVER_BOUND_STEP_M)
                xs = np.interp(t, cum, arr[:, 0]); ys = np.interp(t, cum, arr[:, 1])
                allpts.append(np.column_stack([xs, ys]))
                allidx.append(np.full(len(t), ci))
    allpts = np.vstack(allpts); allidx = np.concatenate(allidx)
    tree = cKDTree(allpts)

    cdx = RIVER_CELL_M / mlon
    cdy = RIVER_CELL_M / mlat
    comps = [c for c in (fill.geoms if fill.geom_type == "MultiPolygon" else [fill])
             if c.area * 111 * 92 > RIVER_MIN_COMP_KM2]
    from collections import defaultdict
    city_cells = defaultdict(list)
    for comp in comps:
        minx, miny, maxx, maxy = comp.buffer(cdx).bounds
        gx = np.arange(minx, maxx, cdx); gy = np.arange(miny, maxy, cdy)
        if len(gx) == 0 or len(gy) == 0:
            continue
        XX, YY = np.meshgrid(gx, gy)
        mask = shapely.contains_xy(comp, XX, YY)
        if not mask.any():
            rp = comp.representative_point()
            d, k = tree.query([rp.x * mlon, rp.y * mlat])
            if d <= RIVER_NEAR_M:
                city_cells[int(allidx[k])].append(comp)
            continue
        px = XX[mask]; py = YY[mask]
        d, k = tree.query(np.column_stack([px * mlon, py * mlat]))
        ci = allidx[k]; good = d <= RIVER_NEAR_M
        for cc in np.unique(ci[good]):
            sel = (ci == cc) & good
            cells = [box(x - cdx / 2, y - cdy / 2, x + cdx / 2, y + cdy / 2)
                     for x, y in zip(px[sel], py[sel])]
            city_cells[int(cc)].append(unary_union(cells))

    folded = 0.0
    for ci, parts in city_cells.items():
        u = unary_union(parts).buffer(cdx * 0.6).buffer(-cdx * 0.6)  # close raster seams
        u = polygonal(u.simplify(cdx * 0.5, preserve_topology=True))  # thin raster vertices
        if u.is_empty:
            continue
        folded += u.area
        clipped[names[ci]] = polygonal(unary_union([clipped[names[ci]], u]).intersection(play))
    return folded * 111 * 92


def main():
    import shapefile
    play = load_play_area()
    r = shapefile.Reader(ensure_shapefile(PLACE_URL, PLACE_STEM))
    flds = [f[0] for f in r.fields[1:]]
    clipped = {}
    for sh, rec in zip(r.shapes(), r.records()):
        d = dict(zip(flds, rec))
        name = d["NAMELSAD"]
        g = shape(sh.__geo_interface__)
        if not g.is_valid:
            g = g.buffer(0)
        if not g.intersects(play):
            continue
        g = polygonal(g.intersection(play))
        if not g.is_valid:
            g = g.buffer(0)
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        clipped[name] = g

    # Simplify FIRST (this is what opens the river channels as gaps), THEN fold
    # the rivers back in — folding before simplify would just be re-eroded.
    simp = {}
    for name in clipped:
        g = polygonal(clipped[name].simplify(SIMPLIFY_DEG, preserve_topology=True))
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        simp[name] = g

    try:
        folded = fold_rivers(simp, play)
        print(f"folded river channels into banks: {folded:.2f} km2", file=sys.stderr)
    except Exception as e:  # numpy/scipy missing or Overpass down: ship without polish
        print(f"WARNING: river fold skipped ({e}); channels stay as thin gaps", file=sys.stderr)

    out = {"type": "FeatureCollection", "features": []}
    for name in sorted(simp):
        g = simp[name]
        if g.is_empty or g.area < MIN_AREA_DEG2:
            continue
        out["features"].append({"type": "Feature", "properties": {"name": name},
                                "geometry": mapping(g)})
    dest = os.path.join(DATA, "la.places.geojson.json")
    with open(dest, "w") as f:
        json.dump(out, f)
    print(f"wrote {dest} — {len(out['features'])} places, {os.path.getsize(dest)} bytes")


if __name__ == "__main__":
    main()
