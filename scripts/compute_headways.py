#!/usr/bin/env python3
"""Compute per-station service headway (headwayMin) from a GTFS feed.

Eligibility rule (see src/data/questionSets.ts, ELIGIBLE_HEADWAY_MIN = 60):
a station is a valid hiding spot only if it is served at least once an hour.

IMPORTANT — this is the *longest*-gap rule, PER DIRECTION, not an average:
  * For each day type (weekday / weekend) and each travel direction, we take the
    LONGEST gap between consecutive departures inside the game window.
  * A station qualifies only if BOTH directions have a departure at least once
    per hour, so the value we store is the WORSE of the two directions:
        headwayMin[day] = max(longest_gap_dir0, longest_gap_dir1)
    Then `headwayMin[day] <= 60` is true iff every direction runs >= hourly.
  * We use max (worst wait), NOT median/average — a single 90-minute midday gap
    disqualifies the station even if the rest of the day is every 30 minutes.

Frequent fixed-frequency systems (metro/light-rail/streetcar that run well under
the threshold all day, e.g. LA Metro, Muni, VTA) can skip GTFS parsing and use a
per-line published constant via `constant_headways()`.
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict

# Game day window: a departure is required at least once an hour throughout.
GAME_START_SEC = int(7.5 * 3600)   # 07:30
GAME_END_SEC = 22 * 3600           # 22:00
THRESHOLD_MIN = 60                 # ELIGIBLE_HEADWAY_MIN
# Require the first departure within THRESHOLD of the window start and the last
# within THRESHOLD of the window end (coverage across the whole game day), by
# adding the window edges as sentinels before measuring gaps.
INCLUDE_WINDOW_EDGES = True


def _to_sec(t: str) -> int:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def _read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _day_type(cal_row: dict) -> str | None:
    """Map a calendar.txt row to 'wd' (runs all weekdays) or 'we' (any weekend day)."""
    if all(cal_row[d] == "1" for d in
           ("monday", "tuesday", "wednesday", "thursday", "friday")):
        return "wd"
    if cal_row["saturday"] == "1" or cal_row["sunday"] == "1":
        return "we"
    return None


def longest_gap_min(times_sec: list[int]) -> float | None:
    """Longest gap (minutes) between consecutive departures inside the game
    window. Returns None when the direction has no usable service in the window."""
    pts = sorted({t for t in times_sec if GAME_START_SEC <= t <= GAME_END_SEC})
    if not pts:
        return None
    if INCLUDE_WINDOW_EDGES:
        pts = [GAME_START_SEC] + pts + [GAME_END_SEC]
    if len(pts) < 2:
        return None
    return max((pts[i + 1] - pts[i]) / 60 for i in range(len(pts) - 1))


def gtfs_headways(gtfs_dir: str) -> dict[str, dict[str, float]]:
    """Return {stop_id: {'wd': headwayMin, 'we': headwayMin}} for a GTFS feed.

    headwayMin[day] is the worst (longest) per-direction longest-gap, so
    <= THRESHOLD means every direction is served at least hourly.
    """
    cal = {r["service_id"]: r for r in _read_csv(os.path.join(gtfs_dir, "calendar.txt"))}
    trips = {t["trip_id"]: t for t in _read_csv(os.path.join(gtfs_dir, "trips.txt"))}

    # stop -> day -> direction -> [departure seconds]
    deps: dict[str, dict[str, dict[str, list[int]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    for r in _read_csv(os.path.join(gtfs_dir, "stop_times.txt")):
        ti = trips.get(r["trip_id"])
        if not ti:
            continue
        day = _day_type(cal[ti["service_id"]]) if ti["service_id"] in cal else None
        if day is None:
            continue
        t = r.get("departure_time") or r.get("arrival_time")
        if not t:
            continue
        try:
            sec = _to_sec(t)
        except ValueError:
            continue
        deps[r["stop_id"]][day][ti.get("direction_id", "0")].append(sec)

    out: dict[str, dict[str, float]] = {}
    for stop_id, by_day in deps.items():
        rec: dict[str, float] = {}
        for day in ("wd", "we"):
            dirs = by_day.get(day, {})
            per_dir = [longest_gap_min(times) for times in dirs.values()]
            per_dir = [g for g in per_dir if g is not None]
            # No service in a needed direction => not hourly => sentinel 999.
            if not per_dir or len(dirs) < 2:
                rec[day] = 999.0
            else:
                rec[day] = max(per_dir)  # worst direction governs eligibility
        out[stop_id] = rec
    return out


def constant_headways(line_headway_min: dict[str, float],
                      lines: list[str]) -> dict[str, float]:
    """Headway for a frequent fixed-frequency station: min published headway over
    the station's lines (best-served line), applied to both day types."""
    vals = [line_headway_min[ln] for ln in lines if ln in line_headway_min]
    hw = min(vals) if vals else 999.0
    return {"wd": hw, "we": hw}


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("gtfs_dir", help="path to an unzipped GTFS feed")
    ap.add_argument("--json", action="store_true", help="print full JSON map")
    args = ap.parse_args()

    hw = gtfs_headways(args.gtfs_dir)
    stops = {s["stop_id"]: s["stop_name"]
             for s in _read_csv(os.path.join(args.gtfs_dir, "stops.txt"))}
    if args.json:
        print(json.dumps(hw, indent=2))
    else:
        print(f"window {GAME_START_SEC//3600}:{GAME_START_SEC%3600//60:02d}"
              f"-{GAME_END_SEC//3600}:00  threshold {THRESHOLD_MIN}m  "
              f"(worst per-direction longest gap; <= {THRESHOLD_MIN} = eligible)")
        for sid, rec in sorted(hw.items(), key=lambda kv: stops.get(kv[0], kv[0])):
            wd, we = rec["wd"], rec["we"]
            print(f"  {stops.get(sid, sid):36} wd={wd:6.0f} "
                  f"{'OK' if wd <= THRESHOLD_MIN else 'no'}   "
                  f"we={we:6.0f} {'OK' if we <= THRESHOLD_MIN else 'no'}")
