#!/usr/bin/env python3
"""Apply a manual curation batch to the review map **and** the decision ledger.

Every delete / merge / unmerge / rep-swap from the human review pass goes through
here so the two files can never drift: the review map (`poi_merge_viz.js`) is what
you look at, the ledger (`poi_decisions.<region>.json`) is what the next refresh
diffs against. A deletion applied only to the map would silently come back on the
next scan.

    # names are matched exactly (case/space/unicode-insensitive)
    python3 poi_curate.py delete --region la --file batch.txt
    python3 poi_curate.py delete --region la --name "Clinic" --at 34.18683,-118.39855
    python3 poi_curate.py merge  --region la --into "Torrance Memorial ... 204" \
                                 --name "... 201" --name "... 102"
    python3 poi_curate.py unmerge --region la --name "Cedars-Sinai Gastroenterology"
    python3 poi_curate.py swap    --region la --to "Kindred Hospital Paramount"

    # clearing an UNDER5 batch: these died for want of reviews, so keep them
    # re-testable instead of sticky
    python3 poi_curate.py delete --region la --file under5.txt --reason review_failed

    # kill a refresh queue item for good without ever putting it on the map
    python3 poi_curate.py reject --region la --key google:ChIJ... --note "chiropractic suite"

`--file` takes one name per line; a leading "- " is stripped, "# " comments and
blank lines are ignored, and a trailing coordinate disambiguates a duplicated name:

    - Clinic @ 34.18683,-118.39855
    - California Sports and Rehab 34.03873134527533, -118.47465962883501

Rules that keep a batch safe:
- An ambiguous name (>1 pin) is **never guessed** — the run aborts and prints the
  candidates with Google Maps links so the human can pick.
- Deleting a group's representative does **not** delete kids that weren't listed:
  each surviving kid is promoted to its own standalone pin, and the promotion is
  reported.
- Ledger decisions written here are **sticky** by default (`reason: manual`): a
  refresh never offers them back, and only a rename re-opens them. Pass
  `--reason review_failed` for pins that are only being dropped because they are
  under 5 reviews — those stay re-testable for ever, so they come back the moment
  they earn the reviews.
"""
import argparse
import os
import sys

import poi_ledger as L


# --------------------------------------------------------------- name matching

def parse_line(line):
    """'- Name @ 34.1,-118.4' / '- Name 34.1, -118.4' -> (name, (lat,lon)|None)."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("- "):
        s = s[2:].strip()
    if "@" in s:
        head, _, tail = s.rpartition("@")
        at = parse_at(tail)
        if at:
            return head.strip(), at
    parts = s.replace(",", " ").split()
    if len(parts) >= 3:
        at = parse_at(",".join(parts[-2:]))
        if at:
            return " ".join(s.split()[:-2]).rstrip(","), at
    return s, None


def parse_at(text):
    try:
        lat, lon = (float(x) for x in text.strip().split(","))
    except ValueError:
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def find(obj, name, at=None, cat=None, tol=3e-4):
    """All pins whose name matches exactly (normalized), optionally near `at`."""
    want = L.norm(name)
    hits = [(c, role, pin, grp) for c, role, pin, grp in L.iter_pins(obj)
            if L.norm(pin["n"]) == want and (cat is None or c == cat)]
    if at:
        near = [h for h in hits
                if abs(h[2]["lat"] - at[0]) < tol and abs(h[2]["lon"] - at[1]) < tol]
        if near:
            return near
    return hits


def resolve(obj, targets, cat=None):
    """[(name, at)] -> [(cat, role, pin, group)], aborting on miss/ambiguity."""
    out, problems = [], []
    for name, at in targets:
        hits = find(obj, name, at, cat)
        if len(hits) == 1:
            out.append(hits[0])
        else:
            problems.append((name, at, hits))
    if problems:
        for name, at, hits in problems:
            if not hits:
                print(f"NO MATCH   {name}" + (f"  @ {at}" if at else ""))
            else:
                print(f"AMBIGUOUS  {name}  ({len(hits)} pins) — re-run with '@ lat,lon':")
                for c, role, pin, _ in hits:
                    print(f"             {c:14} {role:6} {pin['lat']:.5f},{pin['lon']:.5f}  {L.gmaps(pin)}")
        raise SystemExit(f"\n{len(problems)} unresolved name(s); nothing was changed.")
    return out


# ------------------------------------------------------------------ operations

def op_delete(obj, hits):
    """Delete every resolved pin; kids of a deleted rep survive as standalone.

    Rebuilt in one pass so a batch that hits a rep *and* some of its kids behaves:
    the group disappears and only the **unlisted** kids become their own pins.
    """
    doomed = {id(pin) for _, _, pin, _ in hits}
    promoted = []
    for cat in {c for c, _, _, _ in hits}:
        c = obj[cat]
        groups, singles = [], [s for s in c["singles"] if id(s) not in doomed]
        for g in c["groups"]:
            kids = [k for k in g["kids"] if id(k) not in doomed]
            if id(g["rep"]) in doomed:
                for k in kids:
                    k.pop("src", None)
                promoted += [(cat, k) for k in kids]
                singles += kids
            elif kids:
                g["kids"] = kids
                groups.append(g)
            else:
                singles.append(g["rep"])           # a group of one is just a pin
        c["groups"], c["singles"] = groups, singles
    return promoted


def _detach(obj, cat, role, pin, group):
    """Pull a pin out of the structure without deleting it."""
    c = obj[cat]
    if role == "single":
        c["singles"].remove(pin)
    elif role == "kid":
        group["kids"].remove(pin)
        if not group["kids"]:
            c["groups"].remove(group)
            c["singles"].append(group["rep"])
    else:
        c["groups"].remove(group)
        c["singles"].extend(group["kids"])


def op_merge(obj, rep_hit, kid_hits):
    cat, role, rep, group = rep_hit
    if role == "kid":
        raise SystemExit(f"--into target '{rep['n']}' is itself merged away; unmerge or swap first")
    if role == "single":
        obj[cat]["singles"].remove(rep)
        group = {"rep": rep, "kids": []}
        obj[cat]["groups"].append(group)
    for kcat, krole, kpin, kgroup in kid_hits:
        if kcat != cat:
            raise SystemExit(f"cannot merge across categories ({kcat} -> {cat})")
        if kpin is rep:
            continue
        _detach(obj, kcat, krole, kpin, kgroup)
        kpin["src"] = "manual"
        group["kids"].append(kpin)
    return group


def op_unmerge(obj, hits):
    for cat, role, pin, group in hits:
        if role != "kid":
            raise SystemExit(f"'{pin['n']}' is not a merged-away pin (it is a {role})")
        _detach(obj, cat, role, pin, group)
        pin.pop("src", None)
        obj[cat]["singles"].append(pin)


def op_swap(obj, hit):
    """Make a merged-away kid the group's representative; the old rep becomes a kid."""
    cat, role, pin, group = hit
    if role != "kid":
        raise SystemExit(f"'{pin['n']}' is already a {role}; --to must name a merged-away pin")
    old = group["rep"]
    old["src"] = pin.pop("src", "name")
    group["rep"] = pin
    group["kids"] = [old] + [k for k in group["kids"] if k is not pin]
    return old


# ------------------------------------------------------- ledger reconciliation

def sync_ledger(region, led, obj, reason="manual"):
    """Rewrite ledger decisions from the current review map.

    Alive pins take their decision from their role; anything the ledger thought was
    alive and is now absent becomes a **sticky** drop. Review-gate state is never
    lost, and a `drop` is never resurrected (curation only ever removes pins).
    """
    pending_cats = L.REGIONS[region]["pendingCats"]
    day = L.today()
    alive, changes = set(), {"drop": 0, "merged": 0, "keep": 0}
    for cat, role, pin, group in L.iter_pins(obj):
        k = L.key_for(pin.get("id"))
        alive.add(k)
        rec = led["places"].setdefault(k, {
            "cat": cat, "name": pin["n"], "lat": pin["lat"], "lon": pin["lon"],
            "reviewGate": "unknown", "closed": None, "firstSeen": day, "lastSeen": day,
        })
        was = rec.get("decision")
        if role == "kid":
            new, into = "merged", L.key_for(group["rep"].get("id"))
        else:
            new, into = ("pending" if cat in pending_cats else "keep"), None
        if was == "drop":
            # The map is what the human sees, so a pin they put back is alive again
            # — but say so out loud, because refreshes never do this on their own.
            print(f"  NOTE: '{pin['n']}' was a {rec.get('reason')} drop and is on the map "
                  f"again — restoring it as {new}")
        if was != new or rec.get("mergedInto") != into:
            rec.update(decision=new, mergedInto=into, reason=None, decidedAt=day)
            changes[new if new != "pending" else "keep"] += 1
        rec["name"] = pin["n"]
        rec["mergeSrc"] = pin.get("src") if role == "kid" else None
    for k, rec in led["places"].items():
        if k in alive or rec.get("decision") == "drop":
            continue
        rec.update(decision="drop", reason=reason, mergedInto=None, decidedAt=day)
        changes["drop"] += 1
    return changes


def reject(led, keys, note):
    """Sticky-drop ledger records that were never on the map (refresh queue items)."""
    day, out = L.today(), []
    for k in keys:
        rec = led["places"].get(k)
        if rec is None:
            raise SystemExit(f"no ledger record for {k}")
        rec.update(decision="drop", reason="manual", mergedInto=None, decidedAt=day)
        if note:
            rec["note"] = note
        out.append(rec)
    return out


def ledger_keys(led, targets):
    """Resolve --name/--at against the ledger (queue items aren't on the map)."""
    keys = []
    for name, at in targets:
        hits = [k for k, r in led["places"].items()
                if L.norm(r["name"]) == L.norm(name)
                and (at is None or (abs(r["lat"] - at[0]) < 3e-4 and abs(r["lon"] - at[1]) < 3e-4))]
        if len(hits) != 1:
            for k in hits:
                r = led["places"][k]
                print(f"    {k}  {r['cat']:14} {r['lat']:.5f},{r['lon']:.5f}  {r['decision']}")
            raise SystemExit(f"{'no' if not hits else len(hits)} ledger match(es) for {name!r}")
        keys += hits
    return keys


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("delete", "merge", "unmerge", "swap", "reject"):
        p = sub.add_parser(name)
        p.add_argument("--region", default="la", choices=sorted(L.REGIONS))
        p.add_argument("--cat", help="restrict name matching to one category")
        p.add_argument("--name", action="append", default=[])
        p.add_argument("--at", help="lat,lon disambiguating a single --name")
        p.add_argument("--file", help="one name per line ('- ' and '# ' tolerated)")
        p.add_argument("--dry-run", action="store_true")
        if name == "merge":
            p.add_argument("--into", required=True, help="the surviving representative")
        if name == "swap":
            p.add_argument("--to", required=True, help="merged-away pin to promote to rep")
        if name == "delete":
            p.add_argument("--reason", default="manual", choices=["manual", "review_failed"],
                           help="'review_failed' stays re-testable; 'manual' is sticky")
        if name == "reject":
            p.add_argument("--key", action="append", default=[],
                           help="ledger key, e.g. google:ChIJ... (repeatable)")
            p.add_argument("--note", help="why, for the record")
    a = ap.parse_args()

    targets = [(n, parse_at(a.at) if a.at else None) for n in a.name]
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            targets += [t for t in (parse_line(line) for line in f) if t]

    led = L.load_ledger(a.region)

    if a.cmd == "reject":
        keys = a.key + ledger_keys(led, targets)
        for rec in reject(led, keys, a.note):
            print(f"sticky drop: {rec['cat']} · {rec['name']}")
        if a.dry_run:
            print("\n--dry-run: nothing written")
            return
        L.save_ledger(a.region, led)
        print(f"\nwrote {L.REGIONS[a.region]['ledger']}")
        return

    obj = L.load_viz(a.region)

    if a.cmd == "delete":
        hits = resolve(obj, targets, a.cat)
        promoted = op_delete(obj, hits)
        print(f"deleting {len(hits)} pin(s)")
        for cat, kid in promoted:
            print(f"  KEPT (unlisted kid of a deleted rep, now standalone): "
                  f"{cat} · {kid['n']} · {L.gmaps(kid)}")
    elif a.cmd == "merge":
        rep = resolve(obj, [parse_line(a.into)], a.cat)[0]
        kids = resolve(obj, targets, a.cat)
        op_merge(obj, rep, kids)
        hits = kids + [rep]
        print(f"merged {len(kids)} pin(s) into {rep[2]['n']}")
    elif a.cmd == "unmerge":
        hits = resolve(obj, targets, a.cat)
        op_unmerge(obj, hits)
        print(f"un-merged {len(hits)} pin(s) into standalone pins")
    else:
        hits = [resolve(obj, [parse_line(a.to)], a.cat)[0]]
        old = op_swap(obj, hits[0])
        print(f"swapped rep: {old['n']} -> {hits[0][2]['n']} "
              f"({len(hits[0][3]['kids'])} merged-away pin(s))")

    changes = sync_ledger(a.region, led, obj, getattr(a, "reason", "manual"))
    print("ledger: " + ", ".join(f"{k}+{v}" for k, v in changes.items() if v))
    for cat in sorted({h[0] for h in hits}):
        L.recount(obj[cat])
        print(f"{cat}: {obj[cat]['before']} candidates / {obj[cat]['after']} visible")

    if a.dry_run:
        print("\n--dry-run: nothing written")
        return
    L.save_viz(a.region, obj)
    L.save_ledger(a.region, led)
    print(f"\nwrote {L.REGIONS[a.region]['viz']} and {L.REGIONS[a.region]['ledger']}")


if __name__ == "__main__":
    sys.exit(main())
