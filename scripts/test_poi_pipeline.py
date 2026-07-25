#!/usr/bin/env python3
"""Tests for the POI decision ledger, the curation CLI and the refresh diff.

Plain `python3 test_poi_pipeline.py` — no pytest, nothing installed, no network
and no billable API call: the refresh is exercised against a hand-built sweep.
"""
import copy
import sys

import build_poi_data as B
import poi_curate as C
import registry_audit as A
import poi_geo
import poi_ledger as L
import poi_refresh as R

FAILED = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def pin(n, i, lat=34.0, lon=-118.0, src=None):
    p = {"n": n, "lat": lat, "lon": lon, "r": 0, "id": i}
    if src:
        p["src"] = src
    return p


def viz():
    return {"hospital": {"label": "Hospitals",
            "groups": [{"rep": pin("Rep A", "a"),
                        "kids": [pin("Kid A1", "a1", src="name"), pin("Kid A2", "a2", src="name")]},
                       {"rep": pin("Rep B", "b"), "kids": [pin("Kid B1", "b1", src="name")]}],
            "singles": [pin("Solo", "s"), pin("Dupe", "d1", lat=34.0), pin("Dupe", "d2", lat=34.9)],
            "before": 0, "after": 0}}


def roles(obj):
    return [(role, p["id"]) for _, role, p, _ in L.iter_pins(obj)]


# --------------------------------------------------------------- curation ops
print("curation")
o = viz()
promoted = C.op_delete(o, C.resolve(o, [("Rep A", None), ("Kid A1", None)]))
check("deleting a rep keeps its unlisted kid as a standalone pin",
      ("single", "a2") in roles(o) and [k["id"] for _, k in promoted] == ["a2"], roles(o))
check("a promoted kid loses its merge source", "src" not in C.find(o, "Kid A2")[0][2])
check("a listed kid dies with its rep", ("single", "a1") not in roles(o) and ("kid", "a1") not in roles(o))

o = viz()
C.op_delete(o, C.resolve(o, [("Kid B1", None)]))
check("deleting the last kid collapses the group to a single pin",
      ("single", "b") in roles(o) and ("rep", "b") not in roles(o), roles(o))

o = viz()
try:
    C.resolve(o, [("Dupe", None)])
    check("an ambiguous name aborts the batch", False)
except SystemExit:
    check("an ambiguous name aborts the batch", True)
check("a coordinate disambiguates a duplicated name",
      C.resolve(o, [("Dupe", (34.9, -118.0))])[0][2]["id"] == "d2")
check("a coordinate near-misses still match (tolerance)",
      C.resolve(o, [("Dupe", (34.9001, -118.0001))])[0][2]["id"] == "d2")

o = viz()
C.op_merge(o, C.resolve(o, [("Solo", None)])[0], C.resolve(o, [("Rep B", None)]))
check("merging into a single promotes it to a group rep",
      ("rep", "s") in roles(o) and ("kid", "b") in roles(o), roles(o))
C.op_unmerge(o, C.resolve(o, [("Rep B", None)]))
check("un-merging restores a standalone pin",
      ("single", "b") in roles(o) and "src" not in C.find(o, "Rep B")[0][2], roles(o))

o = viz()
old = C.op_swap(o, C.resolve(o, [("Kid A1", None)])[0])
g = C.find(o, "Kid A1")[0][3]
check("a rep swap demotes the old rep to a merged-away kid",
      g["rep"]["id"] == "a1" and [k["id"] for k in g["kids"]] == ["a", "a2"]
      and g["kids"][0].get("src") == "name", roles(o))

check("parse_line reads '@ lat,lon'", C.parse_line("- Clinic @ 34.18683,-118.39855") == ("Clinic", (34.18683, -118.39855)))
check("parse_line reads a bare trailing coordinate",
      C.parse_line("- Cal Sports 34.038731, -118.474659") == ("Cal Sports", (34.038731, -118.474659)))
check("parse_line leaves a plain name alone", C.parse_line("- Plain Name") == ("Plain Name", None))
check("parse_line skips comments/blanks", C.parse_line("# note") is None and C.parse_line("  ") is None)

o = viz()
L.recount(o["hospital"])
check("recount counts merged-away pins as candidates, not as visible",
      (o["hospital"]["before"], o["hospital"]["after"]) == (8, 5),
      (o["hospital"]["before"], o["hospital"]["after"]))


# ------------------------------------------------------- ledger sync (sticky)
print("\nledger sync")


def ledger_from(obj, **over):
    led = {"region": "la", "places": {}}
    C.sync_ledger("la", led, obj)
    for k, v in over.items():
        led["places"][f"google:{k}"].update(v)
    return led


o = viz()
led = ledger_from(o)
check("a merged kid records its parent",
      led["places"]["google:a1"]["decision"] == "merged"
      and led["places"]["google:a1"]["mergedInto"] == "google:a")
check("hospitals seed as 'pending' (first manual pass unfinished)",
      led["places"]["google:a"]["decision"] == "pending")

C.op_delete(o, C.resolve(o, [("Solo", None)]))
C.sync_ledger("la", led, o)
rec = led["places"]["google:s"]
check("a curated delete is a sticky manual drop by default",
      rec["decision"] == "drop" and rec["reason"] == "manual" and not L.retestable(rec), rec)

o3 = viz()
led3 = ledger_from(o3)
C.op_delete(o3, C.resolve(o3, [("Solo", None)]))
C.sync_ledger("la", led3, o3, "review_failed")
check("--reason review_failed keeps a dropped pin re-testable",
      L.retestable(led3["places"]["google:s"]))

led3 = ledger_from(viz())
C.reject(led3, ["google:s"], "chiropractic suite")
check("reject sticky-drops a queue item that was never on the map",
      led3["places"]["google:s"]["decision"] == "drop"
      and not L.retestable(led3["places"]["google:s"])
      and led3["places"]["google:s"]["note"] == "chiropractic suite")
check("reject resolves a name against the ledger",
      C.ledger_keys(led3, [("Rep A", None)]) == ["google:a"])

o2 = viz()                          # a human puts the pin back on the review map
C.sync_ledger("la", led, o2)
check("a human putting a dropped pin back on the map restores it (loudly)",
      led["places"]["google:s"]["decision"] == "pending")

o = viz()
C.op_merge(o, C.resolve(o, [("Rep B", None)])[0],
           C.resolve(o, [("Kid A1", None), ("Kid A2", None), ("Rep A", None)]))
b = [g for g in o["hospital"]["groups"] if g["rep"]["n"] == "Rep B"][0]
check("a merge can swallow a whole group, rep last",
      sorted(k["n"] for k in b["kids"]) == ["Kid A1", "Kid A2", "Kid B1", "Rep A"]
      and [g["rep"]["n"] for g in o["hospital"]["groups"]] == ["Rep B"],
      [k["n"] for k in b["kids"]])

o = viz()
C.op_merge(o, C.resolve(o, [("Solo", None)])[0], C.resolve(o, [("Rep A", None)]))
check("merging just the rep leaves its kids behind as standalone pins",
      sorted(s["n"] for s in o["hospital"]["singles"]) == ["Dupe", "Dupe", "Kid A1", "Kid A2"]
      and all("src" not in s for s in o["hospital"]["singles"]),
      [s["n"] for s in o["hospital"]["singles"]])

o = viz()
led = ledger_from(o)
C.op_swap(o, C.resolve(o, [("Kid A1", None)])[0])
C.sync_ledger("la", led, o)
check("a swap re-points every sibling at the new rep",
      led["places"]["google:a"]["decision"] == "merged"
      and led["places"]["google:a"]["mergedInto"] == "google:a1"
      and led["places"]["google:a2"]["mergedInto"] == "google:a1"
      and led["places"]["google:a1"]["decision"] == "pending"
      and led["places"]["google:a1"]["mergedInto"] is None)


# ------------------------------------------------------------ refresh / diff
print("\nrefresh diff")


def place(i, name, cat_type="hospital", reviews=50, status="OPERATIONAL", lat=34.0, lon=-118.0):
    return {"id": i, "name": name, "primaryType": cat_type, "types": [cat_type],
            "address": "", "userRatingCount": reviews, "businessStatus": status,
            "lat": lat, "lon": lon}


def base_ledger():
    return {"region": "la", "places": {
        "google:keep1": {"cat": "hospital", "name": "Kept Hospital", "lat": 34.0, "lon": -118.0,
                         "decision": "pending", "mergedInto": None, "reason": None,
                         "reviewGate": "passed", "closed": None, "firstSeen": "2026-07-01",
                         "decidedAt": "2026-07-01", "lastSeen": "2026-07-01"},
        "google:merged1": {"cat": "hospital", "name": "Merged Away", "lat": 34.0, "lon": -118.0,
                           "decision": "merged", "mergedInto": "google:keep1", "reason": None,
                           "reviewGate": "passed", "closed": None, "firstSeen": "2026-07-01",
                           "decidedAt": "2026-07-01", "lastSeen": "2026-07-01"},
        "google:legacy1": {"cat": "hospital", "name": "First-pass Delete", "lat": 34.0, "lon": -118.0,
                           "decision": "drop", "reason": "legacy_first_pass", "mergedInto": None,
                           "reviewGate": "unknown", "closed": None,
                           "firstSeen": "2026-07-01", "decidedAt": "2026-07-10", "lastSeen": None},
        "google:manual1": {"cat": "hospital", "name": "Manual Delete", "lat": 34.0, "lon": -118.0,
                           "decision": "drop", "reason": "manual", "mergedInto": None,
                           "reviewGate": "passed", "closed": None, "firstSeen": "2026-07-01",
                           "decidedAt": "2026-07-20", "lastSeen": None},
    }}


def run(sweep_places, led=None, details=None, cat="hospital"):
    led = led or base_ledger()
    raw = {cat: {"places": sweep_places, "sweptAt": L.today(), "calls": 1}}
    q = R.reconcile("la", led, raw, details or {}, write=False)
    return led, q


def names(q, key):
    return sorted(i["name"] for i in q[key])


led, q = run([place("keep1", "Kept Hospital"), place("merged1", "Merged Away"),
              place("new1", "Brand New Hospital"), place("legacy1", "First-pass Delete"),
              place("manual1", "Manual Delete")])
check("a genuinely new place lands in NEW", names(q, "NEW") == ["Brand New Hospital"], names(q, "NEW"))
check("a merged-away pin is skipped entirely",
      all("Merged Away" not in names(q, k) for k in q))
check("a manual (post-ledger) deletion is never re-queued",
      all("Manual Delete" not in names(q, k) for k in q))
check("a review-failure drop that now clears >=5 reviews is re-offered",
      names(q, "RECHECK") == ["First-pass Delete"], names(q, "RECHECK"))
check("it stays dropped until a human acts on the queue",
      led["places"]["google:legacy1"]["decision"] == "drop")
led2, q2 = run([place("legacy1", "First-pass Delete")], led=led)
check("and it keeps being offered on every later refresh",
      names(q2, "RECHECK") == ["First-pass Delete"])
led3, q3 = run([place("legacy1", "First-pass Delete", reviews=2)])
check("a review-failure drop still under 5 stays silent",
      q3["RECHECK"] == [] and L.retestable(led3["places"]["google:legacy1"]))
led4 = base_ledger()
C.reject(led4, ["google:legacy1"], None)
_, q4 = run([place("legacy1", "First-pass Delete")], led=led4)
check("rejecting it by hand stops the re-testing for good", q4["RECHECK"] == [])

led, q = run([place("new2", "Fresh Clinic", reviews=2)])
check("a new place under 5 reviews is recorded but not queued",
      q["NEW"] == [] and led["places"]["google:new2"]["reviewGate"] == "unknown")
led, q = run([place("new2", "Fresh Clinic", reviews=9)], led=led)
check("it surfaces later, once it crosses 5 reviews",
      names(q, "NEW") == ["Fresh Clinic"] and led["places"]["google:new2"]["reviewGate"] == "passed")

led, q = run([place("new3", "Corner Dentist", cat_type="dentist")])
check("an off-icon result is ignored (not a hospital icon)",
      q["NEW"] == [] and "google:new3" not in led["places"])

led, q = run([place("peak1", "Mt Lukens", cat_type="mountain_peak", reviews=0)], cat="mountain")
check("mountains skip the review gate entirely",
      names(q, "NEW") == ["Mt Lukens"] and q["UNDER5"] == [])

led, q = run([place("keep1", "Kept Hospital", status=R.CLOSED_PERM)])
check("permanent closure auto-drops and reports it",
      names(q, "GONE") == ["Kept Hospital"]
      and led["places"]["google:keep1"]["decision"] == "drop"
      and led["places"]["google:keep1"]["reason"] == "closed_permanently")

led, q = run([place("keep1", "Kept Hospital", status=R.CLOSED_TEMP)])
check("temporary closure is manual review, never an auto-drop",
      names(q, "CHANGED") == ["Kept Hospital"]
      and led["places"]["google:keep1"]["decision"] == "pending")

led, q = run([place("keep1", "Renamed Medical Center")])
check("a rename on a live pin is queued and the ledger follows the new name",
      names(q, "CHANGED") == ["Kept Hospital"]
      and led["places"]["google:keep1"]["name"] == "Renamed Medical Center")

led = base_ledger()
led["places"]["google:manual1"]["decision"] = "drop"
_, q = run([place("manual1", "Something Else Entirely")], led=led)
check("a renamed *deleted* pin re-opens for judgement",
      names(q, "CHANGED") == ["Manual Delete"], names(q, "CHANGED"))

led = base_ledger()
led["places"]["google:keep1"]["reviewGate"] = "unknown"
led, q = run([place("keep1", "Kept Hospital", reviews=3)], led=led)
check("a visible pin under 5 reviews is flagged for deletion",
      names(q, "UNDER5") == ["Kept Hospital"], names(q, "UNDER5"))

led, q = run([])
check("a pin missing from the sweep is manual 'verify', never an auto-delete",
      names(q, "GONE") == ["Kept Hospital"]
      and led["places"]["google:keep1"]["decision"] == "pending")
led, q = run([], details={"keep1": {"businessStatus": R.CLOSED_PERM, "userRatingCount": 40}})
check("...unless Place Details confirms it is permanently closed",
      led["places"]["google:keep1"]["decision"] == "drop")

led = base_ledger()
led["places"]["google:keep1"]["reviewGate"] = "unknown"
raw = {"hospital": {"places": [place("keep1", "Kept Hospital")], "sweptAt": L.today(), "calls": 1}}
check("the sweep covers the gate, so Place Details is only for pins it missed",
      R.details_targets("la", led, raw, "keep") == [])
raw["hospital"]["places"] = []
check("a live pin the sweep missed is a Place Details target",
      R.details_targets("la", led, raw, "keep") == ["google:keep1"])
led["places"]["google:keep1"]["reviewGate"] = "passed"
check("a passed gate is never re-bought", R.details_targets("la", led, raw, "keep") == [])
check("re-testable drops are only re-priced when asked for",
      R.details_targets("la", led, raw, "keep") == []
      and R.details_targets("la", led, raw, "keep+retest") == ["google:legacy1"])


# -------------------------------------------------------- app data build
print("\napp data build")
app = B.from_viz(viz())["hospital"]
check("only representatives and singles reach the app",
      sorted(p["n"] for p in app) == ["Dupe", "Dupe", "Rep A", "Rep B", "Solo"])
check("a merged-away child is not a POI", not any(p["n"].startswith("Kid") for p in app))
check("the representative keeps its own coordinates",
      next(p for p in app if p["n"] == "Rep A")["lat"] == 34.0)
check("a category with no Google type of its own gets the canonical one",
      B.from_viz({"consulate": {"groups": [], "singles": [pin("C", "c")]}})
      ["consulate"][0]["t"] == "embassy")

square = [[-118.1, 33.9], [-117.9, 33.9], [-117.9, 34.1], [-118.1, 34.1], [-118.1, 33.9]]
rings = B.rings_of({"features": [{"geometry": {"type": "Polygon", "coordinates": [square]}}]})
check("a POI inside the play area is in play", B.in_play(rings, 34.0, -118.0))
check("a POI just off a simplified boundary still counts",
      B.in_play(rings, 34.1 + 100 / 111320, -118.0))
check("a POI well outside the play area does not",
      not B.in_play(rings, 34.1 + 400 / 111320, -118.0))


# ------------------------------------------------------- the real LA ledger
print("\nseeded LA ledger")
try:
    la = L.load_ledger("la")
except SystemExit as e:
    print(f"  skip   ({e})")
    la = None
if la:
    obj = L.load_viz("la")
    alive = {L.key_for(p.get("id")) for _, _, p, _ in L.iter_pins(obj)}
    kids = {L.key_for(p.get("id")) for _, role, p, _ in L.iter_pins(obj) if role == "kid"}
    places = la["places"]
    check("every pin on the review map is in the ledger", alive <= set(places))
    check("visible pins are keep/pending",
          all(places[k]["decision"] in ("keep", "pending") for k in alive - kids))
    check("merged-away pins are 'merged' with a parent",
          all(places[k]["decision"] == "merged" and places[k]["mergedInto"] in places for k in kids))
    check("everything else is a drop",
          all(r["decision"] == "drop" for k, r in places.items() if k not in alive))
    check("pre-ledger drops are re-testable review failures",
          all(L.retestable(r) for r in places.values()
              if r.get("reason") == "legacy_first_pass"))
    check("no merge points at a dropped or merged pin",
          all(places[r["mergedInto"]]["decision"] not in ("drop", "merged")
              for r in places.values() if r.get("mergedInto")))


# --------------------------------------------------- registry cross-check
print("\nregistry audit")
check("a one-word pin name never claims a registry entry",
      not A.related("Tarzana", "Tarzana Treatment Center"))
check("a name that contains the other's words matches",
      A.related("Olive View-UCLA Medical Center", "LAC Olive View UCLA Medical Center"))
check("unrelated names of the same length don't match",
      not A.related("Saint Francis Medical Center", "Saint Mary Medical Center"))
if la:
    hosp = L.load_viz("la")["hospital"]
    rep = hosp["groups"][0]["rep"]
    kid = hosp["groups"][0]["kids"][0]
    entries = [
        {"name": rep["n"], "city": "", "lat": rep["lat"], "lon": rep["lon"]},
        {"name": kid["n"], "city": "", "lat": kid["lat"], "lon": kid["lon"]},
        {"name": "Nowhere Hospital", "city": "", "lat": 34.05, "lon": -118.30},
        {"name": "Pacific Ocean Hospital", "city": "", "lat": 33.0, "lon": -122.0},
    ]
    b = A.audit("la", "hospital", entries)
    got = {k: [e["name"] if isinstance(e, dict) else e[0]["name"] for e in v]
           for k, v in b.items()}
    check("a registry entry on a visible pin reads covered", rep["n"] in got["covered"])
    check("a registry entry on a merged-away pin reads merged",
          kid["n"] in got["merged"] or kid["n"] in got["covered"])
    check("an undiscovered facility reads missing", got["missing"] == ["Nowhere Hospital"])
    check("entries outside the play area are not counted as gaps",
          got["out"] == ["Pacific Ocean Hospital"])

print("\n" + (f"{len(FAILED)} FAILED: " + ", ".join(FAILED) if FAILED else "all tests passed"))
sys.exit(1 if FAILED else 0)
