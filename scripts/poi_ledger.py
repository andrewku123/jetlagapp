#!/usr/bin/env python3
"""The POI **decision ledger** — the durable record that makes re-checks cheap.

The first build of a city curates every pin by hand. Every later refresh must be a
*diff*, not a re-review: a place already confirmed a hospital stays confirmed, a
merge stays merged, a deletion stays deleted. The ledger is what remembers that, so
a rescan can never resurrect a decision and we never re-buy a review count we
already paid for.

Shape (`poi_decisions.<region>.json`):

    {"region": "la",
     "reviewThreshold": 5,
     "gateExemptCats": ["mountain"],
     "places": {
       "google:ChIJ...": {
          "cat": "hospital",
          "name": "Providence Little Company of Mary - San Pedro",
          "lat": 33.74, "lon": -118.29,
          "decision": "keep" | "pending" | "merged" | "drop",
          "mergedInto": "google:ChIJ..." | null,
          "mergeSrc": "name" | "bigpark" | null,
          "reason": "legacy_first_pass" | "manual" | ...,
          "reviewGate": "passed" | "unknown",
          "recheckOnce": true,          # legacy drops only; see below
          "closed": null | "CLOSED_TEMPORARILY" | "CLOSED_PERMANENTLY",
          "firstSeen": "2026-07-16", "decidedAt": "2026-07-24",
          "lastSeen": "2026-07-24"      # last refresh sweep that returned it
       }}}

Key facts encoded here:
- **Key = stable id.** `google:<place_id>` (a place_id is the one Google field
  exempt from their caching restrictions, so it may be stored indefinitely), else
  `osm:<type>/<id>`. Names move; ids don't.
- **`reviewGate` is a boolean, not a count.** Review counts only rise, so once a
  pin clears >=5 it never needs checking again — and storing our derived pass/fail
  rather than Google's number keeps us inside their content-caching terms.
- **Decisions are sticky.** `drop`/`merged` survive every later scan. The single
  exception is the legacy seed: pins deleted during a city's *first* manual pass
  can't be told apart ("<5 reviews" vs "not really a hospital"), so they are seeded
  `recheckOnce: true` and get exactly one re-test on the next refresh. After that
  refresh clears the flag they are sticky like everything else.

Seeding a region (`seed`) reconstructs all of this from the review map's **git
history**: every revision of `poi_merge_viz.js` is a snapshot of the curation, so
the union over all revisions is every pin ever seen, the latest revision is the
survivors, and the revision where a pin disappears dates its deletion.

    python3 poi_ledger.py seed --region la
    python3 poi_ledger.py stats --region la
"""
import argparse
import datetime as _dt
import json
import os
import subprocess
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VIZ_PREFIX = "window.VIZ="

# Per-region wiring. A new city adds one entry; nothing else in the pipeline
# hard-codes a city.
REGIONS = {
    "la": {
        "viz": "public/poi-la-review/poi_merge_viz.js",
        "play": "src/data/la.play-area.geojson.json",
        "ledger": "scripts/poi_decisions.la.json",
        # Categories whose first manual pass is still unfinished: survivors are
        # seeded `pending` (not yet human-confirmed) instead of `keep`.
        "pendingCats": ["hospital"],
    },
    "bay": {
        "viz": "scripts/poi_merge_viz.js",
        "play": "src/data/play-area.geojson.json",
        "ledger": "scripts/poi_decisions.bay.json",
        "pendingCats": [],
    },
}

REVIEW_THRESHOLD = 5
GATE_EXEMPT_CATS = ["mountain"]  # peaks are kept regardless of review count


# ---------------------------------------------------------------- viz file I/O

def norm(name):
    """Case/space/unicode-insensitive name key used for matching user requests."""
    s = unicodedata.normalize("NFKC", name or "").casefold()
    return " ".join(s.replace("\u2019", "'").split())


def viz_path(region):
    return os.path.join(ROOT, REGIONS[region]["viz"])


def ledger_path(region):
    return os.path.join(ROOT, REGIONS[region]["ledger"])


def parse_viz(text):
    return json.loads(text[len(VIZ_PREFIX):].rstrip(";\n"))


def load_viz(region):
    with open(viz_path(region), encoding="utf-8") as f:
        return parse_viz(f.read())


def recount(cat):
    """Refresh a category's before/after counts. `before` counts every raw pin
    (merged-away kids included), `after` counts what stays visible."""
    cat["before"] = sum(1 + len(g["kids"]) for g in cat["groups"]) + len(cat["singles"])
    cat["after"] = len(cat["groups"]) + len(cat["singles"])


def save_viz(region, obj):
    for cat in obj.values():
        if isinstance(cat, dict) and "groups" in cat:
            recount(cat)
    with open(viz_path(region), "w", encoding="utf-8") as f:
        f.write(VIZ_PREFIX + json.dumps(obj, ensure_ascii=False) + ";\n")


def iter_pins(obj):
    """Yield (cat, role, pin, group) for every pin. role: rep | kid | single."""
    for cat, c in obj.items():
        if not isinstance(c, dict) or "groups" not in c:
            continue
        for g in c["groups"]:
            yield cat, "rep", g["rep"], g
            for k in g["kids"]:
                yield cat, "kid", k, g
        for s in c["singles"]:
            yield cat, "single", s, None


def gmaps(pin):
    return f"https://www.google.com/maps/search/?api=1&query={pin['lat']:.5f}%2C{pin['lon']:.5f}"


# ------------------------------------------------------------------- ledger IO

def key_for(place_id=None, osm_type=None, osm_id=None):
    if place_id:
        return f"google:{place_id}"
    return f"osm:{osm_type}/{osm_id}"


def load_ledger(region):
    p = ledger_path(region)
    if not os.path.exists(p):
        raise SystemExit(f"no ledger at {p} — run: python3 poi_ledger.py seed --region {region}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_ledger(region, led):
    led["places"] = dict(sorted(led["places"].items()))
    with open(ledger_path(region), "w", encoding="utf-8") as f:
        json.dump(led, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")


def today():
    return _dt.date.today().isoformat()


# ----------------------------------------------------------------------- seed

def _git(args):
    return subprocess.run(["git", "-C", ROOT] + args, capture_output=True, text=True, check=True).stdout


def _revisions(rel_path):
    """[(sha, YYYY-MM-DD)] oldest first, for every commit touching the file."""
    out = _git(["log", "--reverse", "--format=%H %cI", "--", rel_path]).strip().splitlines()
    return [(line.split()[0], line.split()[1][:10]) for line in out if line.strip()]


def _snapshot(rel_path, sha):
    return parse_viz(_git(["show", f"{sha}:{rel_path}"]))


def seed(region, gate="passed"):
    cfg = REGIONS[region]
    revs = _revisions(cfg["viz"])
    if not revs:
        raise SystemExit(f"{cfg['viz']} has no git history to seed from")

    places = {}
    prev_ids = set()
    for sha, date in revs:
        snap = _snapshot(cfg["viz"], sha)
        seen = {}
        for cat, role, pin, group in iter_pins(snap):
            k = key_for(pin.get("id"))
            seen[k] = (cat, role, pin, group)
            rec = places.get(k)
            if rec is None:
                rec = places[k] = {"firstSeen": date}
            rec.update(cat=cat, name=pin["n"], lat=pin["lat"], lon=pin["lon"],
                       role=role, mergeSrc=pin.get("src"),
                       mergedInto=key_for(group["rep"]["id"]) if role == "kid" else None,
                       presentAt=date)
        for k in prev_ids - set(seen):          # disappeared in this revision
            places[k].setdefault("goneAt", date)
        for k in set(seen) & prev_ids:
            places[k].pop("goneAt", None)        # came back (an un-delete)
        prev_ids = set(seen)

    out = {}
    for k, r in places.items():
        alive = "goneAt" not in r
        if not alive:
            # A first-pass deletion: we can't tell "<5 reviews" from "not really a
            # hospital", so it gets exactly one re-test on the next refresh.
            rec = {"decision": "drop", "reason": "legacy_first_pass",
                   "reviewGate": "unknown", "recheckOnce": True,
                   "decidedAt": r["goneAt"]}
        elif r["role"] == "kid":
            rec = {"decision": "merged", "mergedInto": r["mergedInto"],
                   "mergeSrc": r.get("mergeSrc"), "reviewGate": gate,
                   "decidedAt": r["presentAt"]}
        else:
            pending = r["cat"] in cfg["pendingCats"]
            rec = {"decision": "pending" if pending else "keep",
                   "reviewGate": "unknown" if pending else gate,
                   "decidedAt": r["presentAt"]}
        rec = {"cat": r["cat"], "name": r["name"], "lat": r["lat"], "lon": r["lon"], **rec}
        rec.setdefault("mergedInto", None)
        rec["closed"] = None
        rec["firstSeen"] = r["firstSeen"]
        rec["lastSeen"] = r["presentAt"] if alive else None
        out[k] = rec

    led = {"region": region, "generated": today(),
           "reviewThreshold": REVIEW_THRESHOLD, "gateExemptCats": GATE_EXEMPT_CATS,
           "source": {"viz": cfg["viz"], "revisions": len(revs), "headRev": revs[-1][0][:10]},
           "note": ("Seeded from the review map's git history. Survivors in "
                    f"{cfg['pendingCats'] or 'no category'} are 'pending' (first manual pass "
                    "unfinished); every other survivor is human-confirmed. Legacy drops carry "
                    "recheckOnce=True — the next refresh re-tests them against the >=5-review "
                    "rule once, then they are sticky forever."),
           "places": out}
    save_ledger(region, led)
    return led


# ---------------------------------------------------------------------- stats

def stats(led):
    from collections import Counter
    rows = Counter((r["cat"], r["decision"]) for r in led["places"].values())
    cats = sorted({c for c, _ in rows})
    kinds = ["keep", "pending", "merged", "drop"]
    w = max(len(c) for c in cats) + 2
    print(f"{'category':{w}}" + "".join(f"{k:>9}" for k in kinds) + f"{'total':>9}")
    for c in cats:
        n = [rows[(c, k)] for k in kinds]
        print(f"{c:{w}}" + "".join(f"{v:>9}" for v in n) + f"{sum(n):>9}")
    tot = [sum(rows[(c, k)] for c in cats) for k in kinds]
    print(f"{'TOTAL':{w}}" + "".join(f"{v:>9}" for v in tot) + f"{sum(tot):>9}")
    gate = Counter(r["reviewGate"] for r in led["places"].values())
    recheck = sum(1 for r in led["places"].values() if r.get("recheckOnce"))
    print(f"\nreviewGate: {dict(gate)}   legacy drops to re-test once: {recheck}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("seed", "stats"):
        p = sub.add_parser(name)
        p.add_argument("--region", default="la", choices=sorted(REGIONS))
    a = ap.parse_args()
    if a.cmd == "seed":
        led = seed(a.region)
        print(f"wrote {ledger_path(a.region)}  ({len(led['places'])} places)\n")
        stats(led)
    else:
        stats(load_ledger(a.region))


if __name__ == "__main__":
    main()
