"""Validate the auto-dedup against the manual overrides (ground truth).

For each category we run dedup twice:
  * OFF  - overrides disabled  -> what the auto-logic catches on its own
  * ON   - overrides enabled   -> the desired target grouping

Then we report:
  1. how many ground-truth manual merges the auto-logic now catches (OFF),
  2. any `separate` override the auto-logic violates (OFF) -- must be zero,
  3. any OVER-MERGE: a pair the auto-logic (OFF) joins but the target (ON)
     keeps apart -- i.e. the new heuristics merged something we did NOT want.
"""
import json, os
import dedup_poi as D

HERE = os.path.dirname(os.path.abspath(__file__))
curated = json.load(open(os.path.join(HERE, "poi_curated.json")))
overrides = {k: v for k, v in json.load(
    open(os.path.join(HERE, "poi_dedup_overrides.json"))).items()
    if not k.startswith("_")}


def groups_of(places, osm, fm, fs, campus):
    r = D.dedup_category(places, osm, forced_merge=fm, forced_sep=fs,
                         campus=campus)
    _, root = D.final_parent(r["edges"])
    return {i: root(i) for i in range(len(places))}, r


tot_merges = tot_caught = tot_sepviol = tot_over = 0
for key in [k for k in D.LABEL if k in curated and k in overrides]:
    places = curated[key]["places"]
    osm = D.load_osm(key)
    fm, fs, rn = D.load_overrides(places, key, overrides)
    # OFF = auto-logic with the `separate` guardrails still on (they are a
    # permanent safety net), but the manual MERGES removed -- this is what the
    # auto-logic catches by itself in production.
    cmp = key in D.CAMPUS_CATS
    g_off, r_off = groups_of(places, osm, [], fs, cmp)
    g_on, r_on = groups_of(places, osm, fm, fs, cmp)  # desired target

    print(f"\n========== {key} ==========")

    # 1) ground-truth merges auto-caught
    caught = missed = 0
    miss_list = []
    for child_i, parent_i in fm:
        if g_off[child_i] == g_off[parent_i]:
            caught += 1
        else:
            missed += 1
            miss_list.append((places[child_i]["name"], places[parent_i]["name"]))
    print(f"  merges: {caught}/{caught+missed} auto-caught")
    for c, p in miss_list:
        print(f"    [still-manual] {c!r} -> {p!r}")
    tot_merges += caught + missed
    tot_caught += caught

    # 2) separate-override violations
    for pair in fs:
        a, b = tuple(pair)
        if g_off[a] == g_off[b]:
            tot_sepviol += 1
            print(f"  !! SEPARATE VIOLATED: {places[a]['name']!r} == "
                  f"{places[b]['name']!r}")

    # 3) over-merges: same group OFF but different group in target ON
    from collections import defaultdict
    off_grp = defaultdict(list)
    for i, gid in g_off.items():
        off_grp[gid].append(i)
    over = []
    for gid, members in off_grp.items():
        if len(members) < 2:
            continue
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                i, j = members[a], members[b]
                if g_on[i] != g_on[j]:
                    over.append((places[i]["name"], places[j]["name"]))
    if over:
        print(f"  OVER-MERGES vs target: {len(over)}")
        for i, j in over:
            print(f"    [over] {i!r}  ==  {j!r}")
        tot_over += len(over)

print(f"\n==== TOTAL: {tot_caught}/{tot_merges} merges auto-caught | "
      f"{tot_sepviol} separate-violations | {tot_over} over-merges ====")
