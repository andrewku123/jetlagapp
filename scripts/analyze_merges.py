"""Classify each manual merge override against the current auto-dedup signals.

For every [child, parent] merge we measure why the automatic passes missed it:
  - distance child<->parent
  - shared distinctive tokens (what name-pass needs)
  - shared distinctive tokens after dropping ':'-tail (norm only keeps pre-colon)
  - is_sub(child)  (whether the sub-part pass would even consider it)
This tells us which merges are systematically catchable vs judgment-only.
"""
import json, os
import dedup_poi as D

HERE = os.path.dirname(os.path.abspath(__file__))
curated = json.load(open(os.path.join(HERE, "poi_curated.json")))
overrides = {k: v for k, v in json.load(
    open(os.path.join(HERE, "poi_dedup_overrides.json"))).items()
    if not k.startswith("_")}


def full_distinctive(name):
    """distinctive tokens over the WHOLE name (not just pre-colon)."""
    import re
    s = name.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    toks = {t for t in s.split() if t and t not in D.STOP and not t.isdigit()}
    return toks - D.GENERIC


for cat, ov in overrides.items():
    places = curated[cat]["places"]
    print(f"\n========== {cat} ({len(ov.get('merge', []))} merges) ==========")
    for child, parent in ov.get("merge", []):
        ci = D.resolve_name(places, child)
        pi = D.resolve_name(places, parent)
        if not ci or not pi:
            print(f"  [UNRESOLVED] {child!r} -> {parent!r}  ci={ci} pi={pi}")
            continue
        c = ci[0]
        revs = [p.get("userRatingCount") or 0 for p in places]
        p = max(pi, key=lambda i: revs[i])
        if c == p:
            continue
        d = D.hav(places[c]["lat"], places[c]["lon"],
                  places[p]["lat"], places[p]["lon"])
        shared_norm = D.distinctive(places[c]["name"]) & D.distinctive(places[p]["name"])
        shared_full = full_distinctive(places[c]["name"]) & full_distinctive(places[p]["name"])
        sub = D.is_sub(places[c]["name"])
        has_colon = (":" in places[c]["name"]) or ("(" in places[c]["name"])
        print(f"  d={d:6.0f}m sub={int(sub)} colon={int(has_colon)} "
              f"normTok={sorted(shared_norm) or '-'} fullTok={sorted(shared_full) or '-'}")
        print(f"        child = {places[c]['name']!r}")
        print(f"        paren = {places[p]['name']!r}")
