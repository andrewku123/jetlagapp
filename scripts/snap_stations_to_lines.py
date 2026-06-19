"""Snap station markers onto their own system's drawn transit-line overlay.

Where a line runs a one-way couplet (northbound and southbound on different
parallel streets), OSM stores a separate stop for each direction. The overlay
draws one direction's track while a station's coordinate may come from the
other, leaving the dot a block off the line (e.g. VTA downtown San Jose:
1st/2nd Street couplet). This nudges any station that sits more than SNAP_TOL_M
from its system's overlay onto the nearest point of that overlay, so the dot
always lands on the drawn line. Stations already on their line (the vast
majority) are untouched.

Operates in place on the built app data; airport distances are recomputed for
moved stations (county/city/elevation move <100 m and are left as-is).
"""
import json, math

DATA = "/home/ubuntu/repos/bayarea-hideandseek/src/data"
STATIONS = f"{DATA}/stations.json"
LINES = f"{DATA}/transit-lines.geojson.json"

SNAP_TOL_M = 40.0    # leave stations already this close to their line alone
SNAP_MAX_M = 400.0   # don't drag a station from further than this (safety)

AIRPORTS = {
    "SFO": (37.619083, -122.381597),
    "OAK": (37.719016, -122.219595),
    "SJC": (37.363510, -121.928648),
}


def hav(a, b):
    R = 6371000.0
    dlat = math.radians(b[0] - a[0]); dlon = math.radians(b[1] - a[1])
    x = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def _mpd(lat):
    return 111320.0 * math.cos(math.radians(lat)), 110540.0


def nearest_on_segment(p, a, b):
    """Nearest point (lat, lon) on segment a-b to p, and its distance (m),
    using a local planar approximation around p."""
    mx, my = _mpd(p[0])
    px, py = p[1] * mx, p[0] * my
    ax, ay = a[1] * mx, a[0] * my
    bx, by = b[1] * mx, b[0] * my
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    dist = math.hypot(px - cx, py - cy)
    return (cy / my, cx / mx), dist


def main():
    stations = json.load(open(STATIONS))
    geo = json.load(open(LINES))
    lines_by_sys = {}
    for f in geo["features"]:
        lines_by_sys.setdefault(f["properties"]["system"], []).append(f["geometry"]["coordinates"])

    moved = 0
    for s in stations:
        best_pt, best_d = None, 1e18
        for sys in s["systems"]:
            for line in lines_by_sys.get(sys, []):
                for i in range(len(line) - 1):
                    pt, d = nearest_on_segment((s["lat"], s["lon"]),
                                               (line[i][1], line[i][0]),
                                               (line[i + 1][1], line[i + 1][0]))
                    if d < best_d:
                        best_d, best_pt = d, pt
        if best_pt is None or best_d <= SNAP_TOL_M or best_d > SNAP_MAX_M:
            continue
        s["lat"], s["lon"] = round(best_pt[0], 6), round(best_pt[1], 6)
        dist = {k: round(hav((s["lat"], s["lon"]), v), 1) for k, v in AIRPORTS.items()}
        s["airportDist"] = dist
        s["nearestAirport"] = min(dist, key=dist.get)
        moved += 1
        print(f"snapped {s['name']:28} ({s['systems']})  {best_d:.0f} m -> on line")

    json.dump(stations, open(STATIONS, "w"), indent=1)
    print(f"done: {moved} station(s) snapped onto their overlay; {len(stations)} total")


if __name__ == "__main__":
    main()
