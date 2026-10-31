#!/usr/bin/env python3
"""Replay a human's POI decisions from a plain-text file onto the review map.

The point: **nobody hand-edits generated data.** `poi_deduped.<region>.json`, the
review map and `src/data/<region>.poi.json` are all rebuilt from the pipeline, so
an edit made in them is lost at the next refresh. Decisions instead live in

    scripts/poi_edits.<region>.txt

one per line, and this replays the whole file after any rebuild:

    python3 dedup_poi.py --region dc --force     # regenerate from the raw pull
    python3 poi_apply_edits.py --region dc       # re-apply every human decision
    python3 build_poi_data.py --region dc        # -> src/data/dc.poi.json

Grammar (verbs are case-insensitive, `#` starts a comment, blank lines ignored;
add `@ lat,lon` after any name to disambiguate a repeated one):

    delete  Prince George's Ballroom @ 38.9426,-76.8815
    merge   Children's National Hospital <- Children's Main Bldg | Sheikh Zayed Campus
    rename  Fort Dupont Ice Arena -> Fort Dupont Ice Rink
    keep    Rock Creek Park Horse Center      # undo an automatic merge
    rep     Kindred Hospital Paramount        # promote a merged-away pin to the group's pin
    closed  Uptown Theater                    # shut for now: out of the app, still watched
    open    Anacostia Community Museum        # it's open — ignore Google's closed flag

`delete` and `closed` both take a place out of the app, and the difference
matters: `delete` says "this was never a POI for the game" and is **sticky**, so a
rescan can never bring it back; `closed` says "this place is shut *right now*",
which a refresh is allowed to undo by itself if the place reopens. Use `open` to
put a closed place back, or to overrule a stale Google closure flag.

Pins Google flags `CLOSED_TEMPORARILY` are closed automatically: every run rewrites
a generated block at the end of the file with one `closed` line per flagged pin
(`--no-auto-closed` skips that). The flag is sometimes stale, so `closed` — the
reversible verb — is the one used, and a stale one is undone by adding `open <name>`
anywhere above the block; the block then stops listing it. A closed place that
Google later shows open again is queued by the refresh for an `open` line.

Every op is **idempotent**: re-running the file is a no-op, and a line whose place
is already in the requested state reports `ok (already)`. Lines that no longer
resolve (a place Google dropped, a typo) are reported at the end and the run exits
non-zero — but every other line is still applied, so one stale line can't block a
batch. This is the same machinery as `poi_curate.py`; the file is the record.
"""
import argparse
import os
import re
import sys

import poi_curate as C
import poi_ledger as L
import poi_geo


def edits_path(region):
    return poi_geo.work(region, "poi_edits.txt")


TEMPLATE = """# POI decisions for {label} — replayed onto the review map by
#   python3 scripts/poi_apply_edits.py --region {region}
# One decision per line. Paste the block the review map's "Copy edits" button
# gives you; nothing here is ever overwritten by a rebuild.
#
#   delete  <name> [@ lat,lon]              drop the pin entirely
#   merge   <keep this> <- <a> | <b>        fold pins into one place
#   rename  <old> -> <new>                  fix a name
#   keep    <name>                          undo an automatic merge
#   rep     <name>                          make this pin the group's pin
#   closed  <name>                          shut for now (reversible; still re-checked)
#   open    <name>                          it's open — undo a closure / Google's flag
#
# Pins Google calls temporarily closed are closed for you in the generated
# block at the bottom; add `open <name>` above it for any that are really open.
"""

AUTO_BEGIN = ("# >>> auto: Google says temporarily closed — regenerated on every run, "
              "don't edit;")
AUTO_BEGIN_2 = "# >>> add `open <name>` above this block for any that are actually open"
AUTO_END = "# <<< end auto"
AUTO_REASON = "temp_closed_auto"
CLOSED_TEMP = "CLOSED_TEMPORARILY"


def parse(path):
    """-> ([(lineno, verb, payload)], [(lineno, text, error)])"""
    if not os.path.exists(path):
        return [], []
    with open(path, encoding="utf-8") as f:
        return parse_lines(f)


def parse_lines(lines):
    ops, bad = [], []
    for i, raw in enumerate(lines, 1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        verb, _, rest = line.partition(" ")
        verb, rest = verb.lower(), rest.strip()
        if not rest:
            bad.append((i, line, f"'{verb}' needs a name")); continue
        if verb == "merge":
            if "<-" not in rest:
                bad.append((i, line, "merge needs '<-' (keep <- absorbed)")); continue
            head, _, tail = rest.partition("<-")
            kids = [C.parse_line(k) for k in tail.split("|") if k.strip()]
            if not head.strip() or not kids:
                bad.append((i, line, "merge needs a name on each side")); continue
            ops.append((i, verb, (C.parse_line(head), kids)))
        elif verb == "rename":
            if "->" not in rest:
                bad.append((i, line, "rename needs '->' (old -> new)")); continue
            old, _, new = rest.partition("->")
            if not old.strip() or not new.strip():
                bad.append((i, line, "rename needs a name on each side")); continue
            ops.append((i, verb, (C.parse_line(old), new.strip())))
        elif verb in ("delete", "keep", "rep", "closed", "open"):
            ops.append((i, verb, C.parse_line(rest)))
        else:
            bad.append((i, line, f"unknown verb '{verb}' (delete / merge / "
                                 "rename / keep / rep / closed / open)"))
    return ops, bad


def one(obj, target):
    """Resolve a (name, at) to exactly one pin, or raise the reason it didn't."""
    name, at = target
    hits = C.find(obj, name, at)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise LookupError(f"no pin named {name!r}"
                          + (f" near {at[0]},{at[1]}" if at else ""))
    where = "; ".join(f"{c} {p['lat']:.5f},{p['lon']:.5f}" for c, _, p, _ in hits)
    raise LookupError(f"{len(hits)} pins named {name!r} — add '@ lat,lon' ({where})")


def known_gone(led, name):
    """True if the ledger already records a place of this name as dropped/merged.

    Lets a replay report `already gone` for a decision that has been applied,
    while a name that was never on the map at all (a typo) still fails loudly.
    """
    want = L.norm(name)
    return any(L.norm(r.get("name")) == want and r["decision"] in ("drop", "merged")
               for r in led["places"].values())


def ledger_find(led, target, decision=None):
    """Ledger records matching a (name, at) — the only trace a closed place leaves.

    A closed pin is off the review map, so `open` can't resolve it the way every
    other verb does; the ledger keeps the pin's own data for exactly this.
    """
    name, at = target
    want = L.norm(name)
    out = [(k, r) for k, r in led["places"].items()
           if L.norm(r.get("name")) == want
           and (decision is None or r.get("decision") == decision)]
    if at:
        near = [(k, r) for k, r in out if abs(r.get("lat", 0) - at[0]) < 3e-4
                and abs(r.get("lon", 0) - at[1]) < 3e-4]
        if near:
            return near
    return out


def apply_op(obj, led, verb, payload, auto=False):
    """-> a status string, or raise LookupError. Idempotent by construction.

    `auto` marks a line from the generated temp-closed block, so the ledger can
    tell a closure the pipeline made from one a reviewer made."""
    if verb == "delete":
        name, at = payload
        if not C.find(obj, name, at):
            if known_gone(led, name):
                return "already gone"
            raise LookupError(f"no pin named {name!r}, and nothing of that name "
                              "was ever on the map")
        hit = one(obj, payload)
        promoted = C.op_delete(obj, [hit])
        extra = "".join(f"; kept unlisted kid {k['n']}" for _, k in promoted)
        return "deleted" + extra

    if verb == "merge":
        rep_t, kid_ts = payload
        rep = one(obj, rep_t)
        merged, already = [], 0
        for kt in kid_ts:
            kid = one(obj, kt)
            if kid[0] != rep[0]:
                # one physical place can't be a hospital and a park; a cross-category
                # merge is always a misclick, and it would corrupt both categories
                raise LookupError(f"{kid[2]['n']!r} is a {kid[0]}, "
                                  f"{rep[2]['n']!r} is a {rep[0]} — merge is per category")
            if kid[3] is not None and kid[3] is rep[3] and kid[1] == "kid":
                already += 1; continue
            merged.append(kid)
        if merged:
            C.op_merge(obj, rep, merged)
        return (f"merged {len(merged)} into {rep[2]['n']}" if merged
                else f"already merged ({already})")

    if verb == "rename":
        (old, at), new = payload
        if not C.find(obj, old, at) and C.find(obj, new, at):
            return "already renamed"
        cat, _, pin, _ = one(obj, (old, at))
        pin["n"] = new
        return f"renamed -> {new} ({cat})"

    if verb == "keep":
        cat, role, pin, grp = one(obj, payload)
        if role != "kid":
            return "already standalone"
        C.op_unmerge(obj, [(cat, role, pin, grp)])
        return "un-merged"

    if verb == "closed":
        name, at = payload
        if not C.find(obj, name, at):
            if ledger_find(led, payload, "closed"):
                return "already closed"
            if known_gone(led, name):
                return "already gone"
            raise LookupError(f"no pin named {name!r}, and nothing of that name "
                              "was ever on the map")
        hit = one(obj, payload)
        cat, _, pin, _ = hit
        rec = led["places"].setdefault(L.key_for(pin.get("id")), {
            "cat": cat, "name": pin["n"], "lat": pin["lat"], "lon": pin["lon"],
            "reviewGate": "unknown", "closed": None,
            "firstSeen": L.today(), "lastSeen": L.today(),
        })
        # keep the pin itself, not just its name: `open` rebuilds the map entry
        # from this, and nothing else remembers its review count or Google id
        rec["pin"] = {k: v for k, v in pin.items() if k != "src"}
        rec.update(decision="closed", reason=AUTO_REASON if auto else "closed",
                   mergedInto=None,
                   closedOverride=False, decidedAt=L.today())
        promoted = C.op_delete(obj, [hit])
        extra = "".join(f"; kept unlisted kid {k['n']}" for _, k in promoted)
        return "closed" + extra

    if verb == "open":
        name, at = payload
        if C.find(obj, name, at):
            cat, _, pin, _ = one(obj, payload)
            flag = pin.pop("bs", None)
            rec = led["places"].get(L.key_for(pin.get("id")))
            if rec is not None:
                rec.update(closed=None, closedOverride=True)
            return f"open (was flagged {flag})" if flag else "already open"
        recs = ledger_find(led, payload, "closed")
        if not recs:
            raise LookupError(f"no pin named {name!r} on the map, and no closed "
                              "record of that name to re-open")
        if len(recs) > 1:
            where = "; ".join(f"{r['lat']:.5f},{r['lon']:.5f}" for _, r in recs)
            raise LookupError(f"{len(recs)} closed places named {name!r} "
                              f"— add '@ lat,lon' ({where})")
        key, rec = recs[0]
        pin = rec.pop("pin", None) or {
            "n": rec["name"], "lat": rec["lat"], "lon": rec["lon"], "r": None,
            "id": key.split("google:", 1)[1] if key.startswith("google:") else None}
        pin.pop("bs", None)
        obj[rec["cat"]]["singles"].append(pin)
        rec.update(closed=None, closedOverride=True)
        return "re-opened"

    if verb == "rep":
        cat, role, pin, grp = one(obj, payload)
        if role == "rep":
            return "already the group's pin"
        if role != "kid":
            raise LookupError(f"{pin['n']!r} is not in a merged group")
        old = C.op_swap(obj, (cat, role, pin, grp))
        return f"now the pin for the group (was {old['n']})"

    raise LookupError(f"unknown verb {verb}")


def split_auto(lines):
    """-> (the reviewer's lines, the generated block's lines)."""
    human, auto, inside = [], [], False
    for raw in lines:
        if raw.startswith(AUTO_BEGIN[:11]):
            inside = True
        elif inside and raw.startswith(AUTO_END):
            inside = False
        elif inside:
            if not raw.startswith("#"):
                auto.append(raw)
        else:
            human.append(raw)
    return human, auto


def google_says_temp_closed(pin, rec, led):
    """The freshest closure signal for a pin still on the map.

    The pin's `bs` is what Google said at the pull that built the map; a later
    refresh sweep that returned the place records its status in the ledger, and
    that one wins (it may have reopened, or closed since)."""
    if rec and led.get("lastRefresh") and rec.get("lastSeen") == led["lastRefresh"]:
        return rec.get("closed") == CLOSED_TEMP
    return pin.get("bs") == CLOSED_TEMP


def auto_closed_block(obj, led):
    """The generated `closed` lines: every visible pin Google calls temporarily
    closed, plus the ones this block already closed (they are off the map now, and
    stay closed until a reviewer adds `open`). A pin a human already ruled on — an
    `open` (closedOverride), their own `closed`, a delete — is never listed."""
    rows = {}
    for cat, role, pin, _ in L.iter_pins(obj):
        if role == "kid":
            continue                        # merged away: not in the app anyway
        k = L.key_for(pin.get("id"))
        rec = led["places"].get(k) or {}
        if rec.get("closedOverride") or not google_says_temp_closed(pin, rec, led):
            continue
        rows[k] = (cat, pin["n"], pin["lat"], pin["lon"])
    for k, rec in led["places"].items():
        if (rec.get("decision") == "closed" and rec.get("reason") == AUTO_REASON
                and not rec.get("closedOverride")):
            rows.setdefault(k, (rec["cat"], rec["name"], rec["lat"], rec["lon"]))
    if not rows:
        return []
    out = ["\n", AUTO_BEGIN + "\n", AUTO_BEGIN_2 + "\n"]
    for cat, name, lat, lon in sorted(rows.values(), key=lambda r: (r[0], L.norm(r[1]))):
        out.append(f"closed  {name} @ {lat:.5f},{lon:.5f}    # {cat} · "
                   f"https://www.google.com/maps/search/?api=1&query={lat:.5f}%2C{lon:.5f}\n")
    out.append(AUTO_END + "\n")
    return out


def main():
    ap = poi_geo.add_region_arg(argparse.ArgumentParser(
        description=__doc__.split("\n")[0]))
    ap.add_argument("--file", help="override the region's edits file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-auto-closed", action="store_true",
                    help="replay the generated temp-closed block as it is instead "
                         "of regenerating it")
    ap.add_argument("--init", action="store_true",
                    help="write the commented template if the file doesn't exist")
    a = ap.parse_args()
    region = a.region
    path = a.file or edits_path(region)

    if a.init and not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(TEMPLATE.format(region=region,
                                    label=poi_geo.REGIONS[region]["label"]))
        print(f"wrote {path}")
        return 0

    if not os.path.exists(path):
        print(f"no decisions in {path} — nothing to do")
        return 0
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    human, old_auto = split_auto(lines)
    ops, bad = parse_lines(human)

    obj = L.load_viz(region)
    led = L.load_ledger(region)
    applied = failed = 0

    def replay(batch, auto=False):
        nonlocal applied, failed
        for lineno, verb, payload in batch:
            try:
                status = apply_op(obj, led, verb, payload, auto=auto)
            except LookupError as e:
                bad.append((lineno, verb, str(e))); failed += 1; continue
            applied += 1
            print(f"  line {lineno:>4}  {verb:<7} {status}")

    replay(ops)
    # The block is built after the reviewer's own lines have run, so an `open`,
    # `closed` or `delete` they wrote this time already keeps a pin out of it.
    if a.no_auto_closed:
        block, text = None, "".join(lines)
        auto_ops, auto_bad = parse_lines(old_auto)
    else:
        # closing a group's pin can promote a kid that is flagged too, so build
        # the block until a pass adds nothing new
        done, auto_bad = set(), []
        base = len(human)
        while base and not human[base - 1].strip():
            base -= 1
        while True:
            block = auto_closed_block(obj, led)
            fresh = [(i + base, v, p) for i, v, p in parse_lines(block)[0]
                     if repr(p) not in done]
            if not fresh:
                break
            done.update(repr(op[2]) for op in fresh)
            replay(fresh, auto=True)
        if block:
            while human and not human[-1].strip():
                human.pop()
            if human and not human[-1].endswith("\n"):
                human[-1] += "\n"
        text = "".join(human) + "".join(block)
        auto_ops = parse_lines(block)[0]
    bad += auto_bad
    if a.no_auto_closed:
        replay(auto_ops, auto=True)

    if not ops and not auto_ops and not bad:
        print(f"no decisions in {path} — nothing to do")
        return 0

    changes = C.sync_ledger(region, led, obj)
    print(f"\n{applied} decision(s) applied, {failed} unresolved"
          + (f" ({len(auto_ops)} from the auto-closed block)" if auto_ops else ""))
    if changes:
        print("ledger: " + ", ".join(f"{k}+{v}" for k, v in changes.items() if v))
    for lineno, what, why in sorted(bad):
        print(f"  ! line {lineno:>4}  {what}: {why}")

    if a.dry_run:
        print("\n--dry-run: nothing written")
    else:
        L.save_viz(region, obj)
        L.save_ledger(region, led)
        print(f"\nwrote {L.viz_path(region)} and {L.ledger_path(region)}")
        if block is not None and text != "".join(lines):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"rewrote the auto-closed block in {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
