"""Per-station ground elevation range within each preset hiding-zone radius.

The hider answers the sea-level question from wherever they stand inside their
hiding zone, so a station survives "closer to sea level" when the lowest in-play
ground in its zone is at or below the seeker, and "further" when the highest is
above. This precomputes those lows/highs so the app never fetches terrain.

Terrain: AWS Terrain Tiles (Terrarium PNG, zoom 14, ~7.5 m/px), which are USGS
3DEP in the US and Copernicus/SRTM elsewhere, so the same script works for a
non-US city. Only pixels inside the play area count (the hider can't stand in
the Pacific); bay water is in the play area, so pixels below -10 m (bathymetry)
are dropped too. The station's own USGS point elevation is folded into every
band.

    python3 scripts/build_zone_elevation.py --region bay   # or sfmuni / la / dc

Writes src/data/<prefix>zone-elev.json:
    {"bandsMi": [...], "stations": {"s000": [[min, max], ...per band], ...}}
Tiles are cached under ~/.cache/terrarium.
"""
import argparse
import io
import json
import math
import os
import urllib.request

import numpy as np
import shapely
from PIL import Image
from shapely.geometry import shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.expanduser("~/.cache/terrarium")
ZOOM = 14
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
# default x {1/2, 3/4, 1, 3/2} for small/medium (0.25 mi) and large (0.5 mi)
# zones, plus 1 mi. The output carries its own bands, so TS needs no copy.
BANDS_MI = [0.125, 0.1875, 0.25, 0.375, 0.5, 0.75, 1.0]
WATER_BELOW_M = -10.0
M_PER_MI = 1609.344

REGIONS = {
    "bay": ("src/data/stations.json", "src/data/play-area.geojson.json", "src/data/zone-elev.json"),
    "sfmuni": ("src/data/sfmuni.stations.json", "src/data/sfmuni.play-area.geojson.json", "src/data/sfmuni.zone-elev.json"),
    "la": ("src/data/la.stations.json", "src/data/la.play-area.geojson.json", "src/data/la.zone-elev.json"),
    "dc": ("src/data/dc.stations.json", "src/data/dc.play-area.geojson.json", "src/data/dc.zone-elev.json"),
}


def tile(x, y):
    path = os.path.join(CACHE, str(ZOOM), str(x), f"{y}.png")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with urllib.request.urlopen(TILE_URL.format(z=ZOOM, x=x, y=y), timeout=60) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def world_px(lat, lon):
    n = 256 * 2 ** ZOOM
    x = (lon + 180) / 360 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def px_lonlat(px, py):
    n = 256 * 2 ** ZOOM
    lon = px / n * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * py / n))))
    return lon, lat


def zone_ranges(st, play, tiles):
    rmax = BANDS_MI[-1] * M_PER_MI
    m_per_px = 156543.03392 * math.cos(math.radians(st["lat"])) / 2 ** ZOOM
    cx, cy = world_px(st["lat"], st["lon"])
    pad = math.ceil(rmax / m_per_px) + 1
    x0, x1 = int(cx - pad), int(cx + pad)
    y0, y1 = int(cy - pad), int(cy + pad)
    xs = np.arange(x0, x1 + 1)
    ys = np.arange(y0, y1 + 1)
    gx, gy = np.meshgrid(xs, ys)
    elev = np.empty(gx.shape)
    for ty in range(y0 // 256, y1 // 256 + 1):
        for tx in range(x0 // 256, x1 // 256 + 1):
            if (tx, ty) not in tiles:
                tiles[(tx, ty)] = tile(tx, ty)
            t = tiles[(tx, ty)]
            m = (gx // 256 == tx) & (gy // 256 == ty)
            elev[m] = t[gy[m] % 256, gx[m] % 256]
    lon, lat = px_lonlat(gx + 0.5, gy + 0.5)
    kx = 111320.0 * math.cos(math.radians(st["lat"]))
    d = np.hypot((lon - st["lon"]) * kx, (lat - st["lat"]) * 110574.0)
    ok = (d <= rmax) & (elev > WATER_BELOW_M)
    ok[ok] = shapely.contains_xy(play, lon[ok], lat[ok])
    own = st.get("elevation")
    out = []
    for b in BANDS_MI:
        sel = elev[ok & (d <= b * M_PER_MI)]
        vals = list(sel) + ([own] if own is not None else [])
        if not vals:
            out.append(None)
            continue
        out.append([round(float(min(vals)), 1), round(float(max(vals)), 1)])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, choices=sorted(REGIONS))
    a = ap.parse_args()
    st_path, play_path, out_path = (os.path.join(ROOT, p) for p in REGIONS[a.region])
    stations = json.load(open(st_path))
    fc = json.load(open(play_path))
    feats = fc["features"] if fc.get("type") == "FeatureCollection" else [fc]
    play = shapely.union_all([shape(f["geometry"]) for f in feats]).buffer(0)
    shapely.prepare(play)
    tiles = {}
    out = {}
    for i, st in enumerate(stations):
        out[st["id"]] = zone_ranges(st, play, tiles)
        if i % 25 == 0:
            print(f"{i}/{len(stations)} {st['name']}: {out[st['id']][2]}", flush=True)
    with open(out_path, "w") as f:
        json.dump({"bandsMi": BANDS_MI, "stations": out}, f, separators=(",", ":"))
        f.write("\n")
    print("wrote", out_path, len(out), "stations,", len(tiles), "tiles")


if __name__ == "__main__":
    main()
