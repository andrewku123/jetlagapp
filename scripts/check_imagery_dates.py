#!/usr/bin/env python3
"""Check whether Esri World Imagery has been refreshed over the play area(s).

This is map-agnostic: it probes one representative point per in-play **county**
found in `src/data/stations.json`, so it automatically covers every region the
app ships — adding a new city/metro to the station data extends the check with no
edits here. It queries Esri's World_Imagery metadata for each point and compares
the capture dates against the committed baseline `scripts/imagery_baseline.json`.

Usage:
  python3 scripts/check_imagery_dates.py                 # check vs baseline
  python3 scripts/check_imagery_dates.py --update-baseline  # rewrite baseline

Exit code 0 = all dates unchanged, 1 = something changed / new region, 2 = error.
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIONS = ROOT / "src" / "data" / "stations.json"
BASELINE = Path(__file__).resolve().parent / "imagery_baseline.json"
IDENTIFY = "https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/identify"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def probe_points() -> dict[str, tuple[float, float]]:
    """One representative (lat, lon) per county: the station nearest that county's
    centroid, so the point is always real imagery (a station), not open water."""
    stations = json.loads(STATIONS.read_text())
    by_county: dict[str, list[tuple[float, float]]] = {}
    for s in stations:
        county = s.get("county")
        if not county or s.get("lat") is None or s.get("lon") is None:
            continue
        by_county.setdefault(county, []).append((s["lat"], s["lon"]))
    points: dict[str, tuple[float, float]] = {}
    for county, pts in by_county.items():
        clat = sum(p[0] for p in pts) / len(pts)
        clon = sum(p[1] for p in pts) / len(pts)
        nearest = min(pts, key=lambda p: (p[0] - clat) ** 2 + (p[1] - clon) ** 2)
        points[county] = nearest
    return dict(sorted(points.items()))


def fetch_date(lat: float, lon: float) -> str:
    """Imagery capture date at a point as 'Mon YYYY' (e.g. 'Aug 2025')."""
    params = {
        "geometry": json.dumps({"x": lon, "y": lat}),
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "layers": "all",
        "tolerance": "2",
        "mapExtent": "0",
        "imageDisplay": "600,600,96",
        "returnGeometry": "false",
        "f": "json",
    }
    with urllib.request.urlopen(IDENTIFY + "?" + urllib.parse.urlencode(params), timeout=60) as r:
        data = json.loads(r.read().decode())
    results = data.get("results", [])
    if not results:
        raise RuntimeError("no identify results")
    attrs = results[0].get("attributes", {})
    raw = attrs.get("SRC_DATE2") or attrs.get("SRC_DATE") or attrs.get("Date")
    if not raw:
        raise RuntimeError(f"no date attribute in {sorted(attrs)}")
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", str(raw))
    if not m:
        raise RuntimeError(f"unexpected date format: {raw!r}")
    return f"{MONTHS[int(m.group(1)) - 1]} {m.group(3)}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true",
                    help="write fresh dates to scripts/imagery_baseline.json")
    args = ap.parse_args()

    try:
        points = probe_points()
        fresh = {county: fetch_date(lat, lon) for county, (lat, lon) in points.items()}
    except Exception as e:  # noqa: BLE001
        print(f"ERROR querying Esri imagery metadata: {e}", file=sys.stderr)
        return 2

    if args.update_baseline:
        BASELINE.write_text(json.dumps(fresh, indent=2) + "\n")
        print(f"Wrote baseline for {len(fresh)} counties to {BASELINE.name}:")
        for county, date in fresh.items():
            print(f"  {county:16} {date}")
        return 0

    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    changed = False
    print("Esri World Imagery capture dates per in-play county:")
    for county, date in fresh.items():
        was = baseline.get(county, "(new region)")
        flag = "" if date == was else "  <-- CHANGED"
        if date != was:
            changed = True
        print(f"  {county:16} baseline={was:11} esri={date:11}{flag}")
    for county in baseline:
        if county not in fresh:
            changed = True
            print(f"  {county:16} baseline={baseline[county]:11} esri=(gone)      <-- REMOVED")

    if changed:
        print("\nImagery changed (or a region was added/removed). Re-run with "
              "--update-baseline to refresh scripts/imagery_baseline.json, and update "
              "the per-region dates in the Legend ('Satellite imagery' in src/App.tsx).")
        return 1
    print("\nNo change — all county dates still match the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
