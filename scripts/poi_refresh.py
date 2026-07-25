#!/usr/bin/env python3
"""Run a POI **refresh cycle** (the 2nd and every later check for a region).

The first build curates every pin by hand. A refresh must never redo that: it
re-scans the whole map, diffs against the decision ledger (`poi_ledger.py`), and
hands the human three short queues instead of thousands of pins.

    phase 1  sweep      full quadtree re-scan of the play area          (paid)
    phase 2  details    review count / status for pins the sweep missed (paid, gated)
    phase 3  reconcile  ledger diff -> NEW / CHANGED / GONE queues      (free)

Cost model (Places API New, per 1,000 calls; first 1,000/month of each Enterprise
SKU are free):

    Nearby Search Pro          $32     id, displayName, location, types,
                                       primaryType, businessStatus
    Nearby Search Enterprise   $35     ... + userRatingCount   <-- what we use
    Place Details Enterprise   $20     one *place*, not 20

Search bills **per call (<=20 places), not per place**, so buying `userRatingCount`
inside the sweep costs ~+9% (~$0.0018/place) versus $0.02/place through Place
Details -- about 11x cheaper. That is why the sweep is never gated and the
"only pins under 5 reviews" rule applies to phase 2 instead: Place Details is only
spent on live pins whose gate is still unknown *and* that the sweep didn't return.
`places.reviews` (Enterprise + Atmosphere, $40/1k) is never requested -- the rule
needs the count, not the text. `businessStatus` is a Pro-tier field, so the
closure check rides along inside the sweep for free.

Nothing is spent without `--confirm-spend`; every phase caches to disk, so an
interrupted run never re-buys what it already has.

    python3 poi_refresh.py --region la                     # plan + cost estimate
    python3 poi_refresh.py --region la --phase sweep --confirm-spend
    python3 poi_refresh.py --region la --phase details --confirm-spend --max-details 500
    python3 poi_refresh.py --region la --phase reconcile --write
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

import poi_geo
import poi_ledger as L

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")

SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
DETAILS_URL = "https://places.googleapis.com/v1/places/"

# The refresh field mask. `userRatingCount` is what lifts the call from the Pro to
# the Enterprise SKU; everything else here is Pro-tier or below, so the closure
# check and the review gate cost nothing extra on top of it.
SWEEP_FIELDS = ",".join([
    "places.id", "places.displayName", "places.location", "places.primaryType",
    "places.types", "places.formattedAddress", "places.businessStatus",
    "places.userRatingCount",
])
DETAILS_FIELDS = "id,displayName,businessStatus,userRatingCount"

USD_PER_SWEEP_CALL = 35.0 / 1000
USD_PER_DETAILS_CALL = 20.0 / 1000

MAX_RESULTS = 20
MAX_RADIUS = 50000.0
MIN_RADIUS = 25.0

CLOSED_PERM = "CLOSED_PERMANENTLY"
CLOSED_TEMP = "CLOSED_TEMPORARILY"


def paths(region):
    return {
        "raw": os.path.join(HERE, f"poi_refresh_raw.{region}.json"),
        "details": os.path.join(HERE, f"poi_refresh_details.{region}.json"),
        "queues": os.path.join(HERE, f"poi_refresh_queues.{region}.json"),
        "md": os.path.join(HERE, f"poi_refresh.{region}.md"),
    }


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


# ------------------------------------------------------------- phase 1: sweep

class Sweep:
    """Recursive quadtree over the play-area bbox (searchNearby has no pagination
    and caps at 20 results, so dense cells must be split)."""

    def __init__(self, in_play, max_calls):
        self.in_play = in_play
        self.max_calls = max_calls
        self.calls = 0

    def nearby(self, types, clat, clon, radius):
        if self.calls >= self.max_calls:
            raise SystemExit(f"hit --max-calls ({self.max_calls}); re-run to continue "
                             f"(finished categories are cached)")
        body = json.dumps({
            "includedTypes": types, "maxResultCount": MAX_RESULTS,
            "locationRestriction": {"circle": {
                "center": {"latitude": clat, "longitude": clon}, "radius": radius}},
        }).encode()
        req = urllib.request.Request(SEARCH_URL, data=body, method="POST", headers={
            "Content-Type": "application/json", "X-Goog-Api-Key": KEY,
            "X-Goog-FieldMask": SWEEP_FIELDS,
        })
        last = None
        for attempt in range(8):
            try:
                self.calls += 1
                with urllib.request.urlopen(req, timeout=90) as r:
                    time.sleep(0.05)
                    return json.load(r).get("places", [])
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read().decode()[:300]}"
                if e.code in (429, 500, 503):
                    time.sleep(2 * (attempt + 1))
                    continue
                sys.exit(last)
            except Exception as e:                      # transient network error
                last = repr(e)
                time.sleep(2 * (attempt + 1))
        sys.exit(f"repeated request failures; last error: {last}")

    def box(self, types, lat0, lat1, lon0, lon1, out):
        clat, clon = (lat0 + lat1) / 2, (lon0 + lon1) / 2
        radius = haversine(clat, clon, lat1, lon1)
        quad = lambda: [self.box(types, a, b, c, d, out) for a, b, c, d in (
            (lat0, clat, lon0, clon), (lat0, clat, clon, lon1),
            (clat, lat1, lon0, clon), (clat, lat1, clon, lon1))]
        if radius > MAX_RADIUS:
            quad()
            return
        places = self.nearby(types, clat, clon, radius)
        for p in places:
            out[p["id"]] = p
        if len(places) >= MAX_RESULTS and radius > MIN_RADIUS:
            quad()


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def flatten(p):
    loc = p["location"]
    return {"id": p["id"], "name": p.get("displayName", {}).get("text", ""),
            "primaryType": p.get("primaryType"), "types": p.get("types", []),
            "address": p.get("formattedAddress", ""),
            "userRatingCount": p.get("userRatingCount", 0),
            "businessStatus": p.get("businessStatus"),
            "lat": loc["latitude"], "lon": loc["longitude"]}


def run_sweep(region, max_calls):
    play = poi_geo.load_play(os.path.join(ROOT, L.REGIONS[region]["play"]))
    in_play = poi_geo.make_in_play(play)
    bbox = poi_geo.bbox(play)
    p = paths(region)
    raw = load_json(p["raw"], {})
    sweep = Sweep(in_play, max_calls)
    for cat, types, _ in poi_geo.CATS:
        if cat in raw:
            print(f"{cat:15s} (cached, skip)", flush=True)
            continue
        found = {}
        sweep.box(types, *bbox, found)
        kept = [flatten(x) for x in found.values()
                if in_play(x["location"]["longitude"], x["location"]["latitude"])]
        raw[cat] = {"places": sorted(kept, key=lambda x: x["name"]),
                    "sweptAt": L.today(), "calls": sweep.calls}
        dump_json(p["raw"], raw)
        ge5 = sum(1 for x in kept if (x["userRatingCount"] or 0) >= poi_geo.MIN_REVIEWS)
        print(f"{cat:15s} in_play={len(kept):5d} >=5rev={ge5:5d} calls={sweep.calls}", flush=True)
    print(f"\n{sweep.calls} calls  ~${sweep.calls * USD_PER_SWEEP_CALL:.2f}  -> {p['raw']}")


# ----------------------------------------------------------- phase 2: details

def details_targets(region, led, raw, scope):
    """Live pins whose review gate is still unknown *and* that the sweep didn't
    return -- the only places worth a per-place call."""
    seen = {pl["id"] for cat in raw.values() for pl in cat["places"]}
    out = []
    for k, rec in led["places"].items():
        if not k.startswith("google:") or k.split(":", 1)[1] in seen:
            continue
        if rec["cat"] in poi_geo.KEEP_ALL or rec.get("reviewGate") == "passed":
            continue                       # never re-buy a gate that already passed
        if rec["decision"] in ("keep", "pending"):
            out.append(k)
        elif scope == "keep+recheck" and rec.get("recheckOnce"):
            out.append(k)
    return out


def run_details(region, targets, max_details):
    p = paths(region)
    cache = load_json(p["details"], {})
    todo = [k for k in targets if k.split(":", 1)[1] not in cache][:max_details]
    for i, k in enumerate(todo, 1):
        pid = k.split(":", 1)[1]
        req = urllib.request.Request(DETAILS_URL + pid, headers={
            "X-Goog-Api-Key": KEY, "X-Goog-FieldMask": DETAILS_FIELDS})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.load(r)
            cache[pid] = {"name": d.get("displayName", {}).get("text", ""),
                          "userRatingCount": d.get("userRatingCount", 0),
                          "businessStatus": d.get("businessStatus"), "checked": L.today()}
        except urllib.error.HTTPError as e:
            # 404 = the place id no longer resolves: a real signal, not an error
            cache[pid] = {"error": e.code, "checked": L.today()}
        if i % 25 == 0 or i == len(todo):
            dump_json(p["details"], cache)
            print(f"  details {i}/{len(todo)}  ~${i * USD_PER_DETAILS_CALL:.2f}", flush=True)
    dump_json(p["details"], cache)
    return len(todo)


# --------------------------------------------------------- phase 3: reconcile

def reconcile(region, led, raw, details, write):
    """Diff the sweep against the ledger. Returns the human queues.

    Sticky rules enforced here:
      * a `drop`/`merged` decision is never resurrected by a scan;
      * the one exception is the legacy first-pass seed (`recheckOnce`), which gets
        exactly one re-test against the >=5-review rule and is then sticky;
      * closure and disappearance are *manual* signals -- only CLOSED_PERMANENTLY
        auto-drops, because Google's temporary flag is routinely stale and a pin
        missing from one sweep is usually search wobble, not a closed business.
    """
    day = L.today()
    q = {k: [] for k in ("NEW", "UNDER5", "CHANGED", "GONE", "RECHECK")}
    seen = set()

    def entry(rec, k, why, extra=None):
        return {"key": k, "cat": rec["cat"], "name": rec["name"], "why": why,
                "lat": rec["lat"], "lon": rec["lon"],
                "maps": f"https://www.google.com/maps/search/?api=1&query="
                        f"{rec['lat']:.5f}%2C{rec['lon']:.5f}", **(extra or {})}

    for cat, block in raw.items():
        for pl in block["places"]:
            k = L.key_for(pl["id"])
            seen.add(k)
            icon = poi_geo.keep_by_type(cat, pl)
            n = pl.get("userRatingCount") or 0
            gate_ok = cat in poi_geo.KEEP_ALL or n >= poi_geo.MIN_REVIEWS
            status = pl.get("businessStatus")
            rec = led["places"].get(k)

            if rec is None:
                if not icon:
                    continue               # off-icon noise the broad pull always returns
                # `auto_discovered`: found by a sweep, not yet on the review map. It
                # only reaches a human once it clears the review rule.
                rec = led["places"][k] = {
                    "cat": cat, "name": pl["name"], "lat": pl["lat"], "lon": pl["lon"],
                    "decision": "pending", "mergedInto": None, "mergeSrc": None,
                    "reason": "auto_discovered",
                    "reviewGate": "passed" if gate_ok else "unknown",
                    "closed": status if status in (CLOSED_PERM, CLOSED_TEMP) else None,
                    "firstSeen": day, "decidedAt": day, "lastSeen": day}
                if gate_ok and status != CLOSED_PERM:
                    q["NEW"].append(entry(rec, k, "new place", {"reviews": n}))
                continue

            renamed = pl["name"] != rec["name"] and L.norm(pl["name"]) != L.norm(rec["name"])
            was_unknown = rec.get("reviewGate") != "passed"
            rec["lastSeen"] = day
            if gate_ok:
                rec["reviewGate"] = "passed"          # monotonic: never re-checked
            rec["closed"] = status if status in (CLOSED_PERM, CLOSED_TEMP) else None
            decision = rec["decision"]

            if decision == "drop":
                if rec.pop("recheckOnce", None) and icon and gate_ok and status != CLOSED_PERM:
                    # legacy first-pass deletion that clears the review rule today:
                    # re-test it once, then it is sticky whatever the human decides
                    q["RECHECK"].append(entry(rec, k, "deleted in the first pass, now >=5 reviews",
                                              {"reviews": n, "newName": pl["name"] if renamed else None}))
                elif renamed:
                    q["CHANGED"].append(entry(rec, k, "deleted pin was renamed — re-judge",
                                              {"reviews": n, "newName": pl["name"]}))
                continue
            if decision == "merged":
                if renamed:
                    rec["name"] = pl["name"]
                continue

            auto = rec.get("reason") == "auto_discovered"   # discovered, not yet mapped
            if status == CLOSED_PERM:
                q["GONE"].append(entry(rec, k, "permanently closed (auto-dropped)"))
                rec.update(decision="drop", reason="closed_permanently", decidedAt=day)
            elif auto:
                rec["name"] = pl["name"]
                if gate_ok and was_unknown:
                    q["NEW"].append(entry(rec, k, "crossed 5 reviews since the last refresh",
                                          {"reviews": n}))
            elif status == CLOSED_TEMP:
                q["CHANGED"].append(entry(rec, k, "temporarily closed — verify by hand"))
            elif renamed:
                q["CHANGED"].append(entry(rec, k, "renamed", {"newName": pl["name"]}))
                rec["name"] = pl["name"]
            elif not gate_ok and cat not in poi_geo.KEEP_ALL:
                q["UNDER5"].append(entry(rec, k, "visible pin under 5 reviews", {"reviews": n}))

    for k, rec in led["places"].items():
        if k in seen or rec["decision"] not in ("keep", "pending"):
            continue
        if rec.get("reason") == "auto_discovered":
            continue          # never reached the map, so its absence is not news
        d = details.get(k.split(":", 1)[1], {}) if k.startswith("google:") else {}
        if d.get("businessStatus") == CLOSED_PERM:
            q["GONE"].append(entry(rec, k, "permanently closed (auto-dropped)"))
            rec.update(decision="drop", reason="closed_permanently", decidedAt=day)
            continue
        if d and (d.get("userRatingCount") or 0) >= poi_geo.MIN_REVIEWS:
            rec["reviewGate"] = "passed"
        # absence from a sweep is NOT closure -- search coverage wobbles
        q["GONE"].append(entry(rec, k, "not returned by this sweep — verify by hand",
                               {"reviews": d.get("userRatingCount")}))

    if write:
        led["lastRefresh"] = day
        L.save_ledger(region, led)
    return q


def write_report(region, q):
    p = paths(region)
    dump_json(p["queues"], q)
    head = {
        "NEW": "New places to review (icon + >=5 reviews)",
        "UNDER5": "Visible pins under 5 reviews — should be dropped per the rulebook",
        "CHANGED": "Renamed / temporarily closed — judge by hand",
        "GONE": "Permanently closed (auto-dropped) or missing from the sweep",
        "RECHECK": "First-pass deletions that now clear the >=5-review rule (one-time re-test)",
    }
    lines = [f"# POI refresh — {region.upper()} — {L.today()}", ""]
    lines += [f"- **{k}**: {len(v)}" for k, v in q.items()]
    for k, items in q.items():
        if not items:
            continue
        lines += ["", f"## {k} — {head[k]}", ""]
        for cat in sorted({i["cat"] for i in items}):
            lines += [f"### {poi_geo.LABEL.get(cat, cat)}", ""]
            for i in sorted((x for x in items if x["cat"] == cat), key=lambda x: x["name"]):
                extra = f" — now *{i['newName']}*" if i.get("newName") else ""
                rev = f" · {i['reviews']} reviews" if i.get("reviews") is not None else ""
                lines.append(f"- [{i['name']}]({i['maps']}){extra}{rev} — {i['why']}")
            lines.append("")
    with open(p["md"], "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--region", default="la", choices=sorted(L.REGIONS))
    ap.add_argument("--phase", default="plan",
                    choices=["plan", "sweep", "details", "reconcile", "all"])
    ap.add_argument("--confirm-spend", action="store_true",
                    help="required for any billable phase")
    ap.add_argument("--max-calls", type=int, default=8000, help="sweep call cap")
    ap.add_argument("--max-details", type=int, default=500, help="per-place call cap")
    ap.add_argument("--details-scope", default="keep", choices=["keep", "keep+recheck"],
                    help="'keep+recheck' also re-prices first-pass deletions the sweep missed")
    ap.add_argument("--write", action="store_true", help="apply ledger updates in reconcile")
    a = ap.parse_args()

    led = L.load_ledger(a.region)
    p = paths(a.region)
    raw = load_json(p["raw"], {})
    billable = a.phase in ("sweep", "details", "all")
    if billable and not (KEY and a.confirm_spend):
        print("billable phase: needs GOOGLE_PLACES_API_KEY and --confirm-spend\n")
        a.phase = "plan"

    if a.phase == "plan":
        live = sum(1 for r in led["places"].values() if r["decision"] in ("keep", "pending"))
        unknown = sum(1 for r in led["places"].values()
                      if r["decision"] in ("keep", "pending")
                      and r.get("reviewGate") != "passed" and r["cat"] not in poi_geo.KEEP_ALL)
        recheck = sum(1 for r in led["places"].values() if r.get("recheckOnce"))
        swept = ", ".join(sorted(raw)) or "nothing yet"
        print(f"region {a.region}: {len(led['places'])} ledger places, {live} live, "
              f"{unknown} awaiting a review-count check, {recheck} legacy drops to re-test once")
        print(f"sweep cache: {swept}")
        print(f"\nphase 1 sweep    ~{a.max_calls} calls max  -> up to "
              f"${a.max_calls * USD_PER_SWEEP_CALL:.2f} (prices review counts for every "
              f"place it returns, ~$0.0018/place)")
        print(f"phase 2 details  <= {unknown} calls          -> up to "
              f"${min(unknown, a.max_details) * USD_PER_DETAILS_CALL:.2f} "
              f"(only live pins the sweep missed; $0.02 each)")
        print("\nre-run with --phase sweep --confirm-spend to start")
        return

    if a.phase in ("sweep", "all"):
        run_sweep(a.region, a.max_calls)
        raw = load_json(p["raw"], {})
    if a.phase in ("details", "all"):
        targets = details_targets(a.region, led, raw, a.details_scope)
        print(f"details: {len(targets)} gated target(s), cap {a.max_details}")
        n = run_details(a.region, targets, a.max_details)
        print(f"details: {n} call(s)  ~${n * USD_PER_DETAILS_CALL:.2f}")
    if a.phase in ("reconcile", "all"):
        if not raw:
            raise SystemExit("no sweep cache — run --phase sweep first")
        q = reconcile(a.region, led, raw, load_json(p["details"], {}), a.write)
        out = write_report(a.region, q)
        print("  ".join(f"{k}={len(v)}" for k, v in q.items()))
        print(f"wrote {out['md']}" + ("" if a.write else "  (ledger NOT updated; use --write)"))


if __name__ == "__main__":
    main()
