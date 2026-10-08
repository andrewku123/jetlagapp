#!/usr/bin/env python3
"""Incremental OSM same-footprint merge for non-park POI categories, applied on
top of the current review map (public/poi-la-review/poi_merge_viz.js) so manual
work is preserved. Mirrors dedup_poi.py pass-3 (OSM-footprint collapse). Pins
(current visible reps + singles) that fall inside the SAME OSM footprint collapse
to one group. Existing groups keep their kids; the reviewer-chosen rep is kept
when a merged pin is already a group rep.

Usage: _osm_merge_other_cats.py [--apply] cat [cat ...]
Writes a CSV of every merge to _osm_merge_<cat>_la.csv.
"""
import os, json, sys, math, re, csv
from collections import defaultdict
from shapely import wkt as shp_wkt
from shapely.geometry import Point
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
VIZ = os.path.join(HERE, "..", "public", "poi-la-review", "poi_merge_viz.js")

STOP = {"the","at","of","and","a","an","for","to","in","on","&","-","|","de","la","el"}
GENERIC = {"park","parks","hospital","hospitals","medical","center","centre","garden",
"gardens","plaza","square","playground","dog","play","area","community","memorial",
"public","open","space","regional","county","city","state","mini","neighborhood",
"playlot","field","fields","clinic","health","care","services","service","foundation",
"trail","shoreline","preserve","reserve","creek","lake","pond","grove","campus",
"medicine","skatepark","skate","rec","recreation","library","libraries","branch",
"street","st","avenue","ave","road","rd","boulevard","blvd","way","drive","dr","lane",
"ln","court","ct","place","pl","highway","hwy","terrace","circle","row","consulate",
"consulates","consulado","consulados","consul","consular","general","embassy","honorary",
"office","san","francisco","jose","oakland","california","ca","bay","north","south",
"east","west","los","angeles","of"}
STRUCTURAL = {"entrance","exit","parking","lot","garage","valet","drop","off","loading",
"dock","helipad","ambulance","building","bldg","wing","annex","pavilion","suite","ste",
"floor","basement","department","dept","radiology","imaging","pharmacy","laboratory",
"lab","cafeteria","gift","shop","store","member","registration","admitting","box",
"office","ticket","kiosk","restroom","main","staging","station","ranger","no","number"}
ANCHOR = {"hospital":["medical center","medical centre","medical foundation","hospital"],
"museum":["museum","gallery"],"library":["library","biblioteca"],
"movie_theater":["cinema","theatre","theater","cineplex","imax","drive-in"],
"zoo":["zoo"],"aquarium":["aquarium"],"amusement_park":["amusement","theme park","water park"]}
_QUALIFIER_TAIL = re.compile(r"\([^)]*\)\s*$")
DEG2_M2 = (111320.0 * math.cos(math.radians(34.05))) * 110574.0

def norm(name):
    s = re.split(r"[|(:—–]", name)[0].lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return [t for t in s.split() if t and t not in STOP]
def distinctive(name):
    return {t for t in set(norm(name)) if not t.isdigit()} - GENERIC
def anchor_hit(name, cat):
    nm = name.lower(); return any(a in nm for a in ANCHOR.get(cat, []))
def has_qualifier(name):
    return (":" in name) or ("|" in name) or bool(_QUALIFIER_TAIL.search(name.strip()))

def load_viz():
    s = open(VIZ).read().strip()
    return json.loads(s[len("window.VIZ="):].rstrip(";"))

def load_osm(cat):
    path = os.path.join(HERE, f"osm_polys_{cat}_la.json")
    feats = json.load(open(path))
    geoms, fnames, areas = [], [], []
    for f in feats:
        try:
            g = shp_wkt.loads(f["wkt"])
        except Exception:
            continue
        if g.is_empty: continue
        if not g.is_valid: g = g.buffer(0)
        if g.is_empty: continue
        geoms.append(g); fnames.append(f.get("name","")); areas.append(g.area*DEG2_M2)
    return {"tree": STRtree(geoms), "geoms": geoms, "names": fnames, "areas": areas}

def rep_score(node, fname, cat, is_group):
    """Higher = better rep. Prefer existing group, flagship anchor noun, clean
    (non-qualifier) name, name-overlap with footprint, then longer name."""
    nm = node["n"]
    return (1 if is_group else 0,
            1 if anchor_hit(nm, cat) else 0,
            0 if has_qualifier(nm) else 1,
            len(distinctive(nm) & distinctive(fname)),
            len(nm))

def plan_cat(cat, viz):
    osm = load_osm(cat)
    catobj = viz[cat]
    # visible pins: ('group',gi) reps and ('single',si)
    pins = []  # (kind, idx, node)
    for gi,g in enumerate(catobj["groups"]):
        pins.append(("group", gi, g["rep"]))
    for si,s in enumerate(catobj["singles"]):
        pins.append(("single", si, s))
    assign = {}
    for pi,(kind,idx,node) in enumerate(pins):
        pt = Point(node["lon"], node["lat"])
        cand = osm["tree"].query(pt)
        inside = [gi for gi in cand if osm["geoms"][gi].covers(pt)]
        if not inside: continue
        best = max(inside, key=lambda gi: (
            len(distinctive(node["n"]) & distinctive(osm["names"][gi])),
            -osm["geoms"][gi].area))
        assign[pi] = best
    byf = defaultdict(list)
    for pi,f in assign.items(): byf[f].append(pi)
    merges = []  # dict per cluster
    for f, members in byf.items():
        if len(members) < 2: continue
        fname = osm["names"][f]
        keeper = max(members, key=lambda pi: rep_score(pins[pi][2], fname, cat, pins[pi][0]=="group"))
        absorbed = [pi for pi in members if pi != keeper]
        merges.append({"f":f,"fname":fname,"area_km2":osm["areas"][f]/1e6,
                       "keeper":keeper,"absorbed":absorbed})
    return osm, pins, merges

def main():
    args = sys.argv[1:]
    apply = "--apply" in args
    cats = [a for a in args if a != "--apply"]
    viz = load_viz()
    grand = 0
    for cat in cats:
        osm, pins, merges = plan_cat(cat, viz)
        n_abs = sum(len(m["absorbed"]) for m in merges)
        grand += n_abs
        print(f"\n===== {cat}: {len(merges)} merges, {n_abs} pins absorbed =====")
        rows = []
        for m in sorted(merges, key=lambda m:-len(m["absorbed"])):
            kp = pins[m["keeper"]][2]
            kg = " (existing group)" if pins[m["keeper"]][0]=="group" else ""
            flag = " <== BIG FOOTPRINT" if m["area_km2"]>0.05 else ""
            print(f'  [{len(m["absorbed"])}] keep {kp["n"]!r}{kg}  <=  footprint {m["fname"]!r} {m["area_km2"]*1000:.1f} dam2{flag}')
            for pi in m["absorbed"]:
                nd = pins[pi][2]
                grp = " (existing group)" if pins[pi][0]=="group" else ""
                print(f'        - {nd["n"]!r}{grp}')
                rows.append({"cat":cat,"keep":kp["n"],"keep_lat":kp["lat"],"keep_lon":kp["lon"],
                    "merged":nd["n"],"merged_lat":nd["lat"],"merged_lon":nd["lon"],
                    "merged_was_group":pins[pi][0]=="group","footprint":m["fname"],
                    "footprint_dam2":round(m["area_km2"]*1000,2)})
        with open(os.path.join(HERE, f"_osm_merge_{cat}_la.csv"),"w",newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["cat","keep","keep_lat","keep_lon","merged",
                "merged_lat","merged_lon","merged_was_group","footprint","footprint_dam2"])
            w.writeheader(); w.writerows(rows)
    print(f"\nGRAND TOTAL pins absorbed across {cats}: {grand}")
    if apply:
        apply_merges(viz, cats)

def apply_merges(viz, cats):
    for cat in cats:
        osm, pins, merges = plan_cat(cat, viz)
        catobj = viz[cat]
        groups = catobj["groups"]; singles = catobj["singles"]
        # Build new structures. Determine per pin whether it stays, is a keeper,
        # or is absorbed (with its kids) into a keeper.
        keeper_of = {}   # absorbed pin -> keeper pin
        cluster = {}     # keeper pin -> list absorbed pins
        for m in merges:
            cluster[m["keeper"]] = m["absorbed"]
            for pi in m["absorbed"]:
                keeper_of[pi] = m["keeper"]
        # helper to get the existing kids list for a pin
        def node_and_kids(pi):
            kind, idx, rep = pins[pi]
            if kind == "group":
                g = groups[idx]
                return dict(g["rep"]), [dict(k) for k in g["kids"]]
            else:
                return dict(singles[idx]), []
        new_groups = []
        used_pins = set()
        # first, keepers -> build merged groups
        for keeper_pi, absorbed in cluster.items():
            rep, kids = node_and_kids(keeper_pi)
            used_pins.add(keeper_pi)
            for pi in absorbed:
                anode, akids = node_and_kids(pi)
                anode = dict(anode); anode["src"] = "osm"
                anode.pop("r", None) if False else None
                kids.append(anode)
                for k in akids:
                    kids.append(k)   # keep grandkids
                used_pins.add(pi)
            new_groups.append({"rep":{k:rep[k] for k in ("n","lat","lon","r","id") if k in rep},
                               "kids":kids})
        # then, untouched groups + singles
        untouched_groups = []
        untouched_singles = []
        for pi,(kind,idx,node) in enumerate(pins):
            if pi in used_pins: continue
            if kind == "group":
                untouched_groups.append(groups[idx])
            else:
                untouched_singles.append(singles[idx])
        catobj["groups"] = untouched_groups + new_groups
        catobj["singles"] = untouched_singles
        after = len(catobj["groups"]) + len(catobj["singles"])
        before = after + sum(len(g["kids"]) for g in catobj["groups"])
        catobj["before"] = before; catobj["after"] = after
        print(f"applied {cat}: groups={len(catobj['groups'])} singles={len(catobj['singles'])} before={before} after={after}")
    # dup id check
    dup = 0; ids = {}
    for cat in cats:
        for g in viz[cat]["groups"]:
            for nd in [g["rep"]]+g["kids"]:
                i = nd.get("id")
                if i:
                    if i in ids: dup += 1
                    ids[i]=1
        for s in viz[cat]["singles"]:
            i = s.get("id")
            if i:
                if i in ids: dup += 1
                ids[i]=1
    print("intra-batch duplicate ids:", dup)
    out = "window.VIZ=" + json.dumps(viz, ensure_ascii=False) + ";"
    open(VIZ,"w").write(out)
    print("written", len(out), "bytes")

if __name__ == "__main__":
    main()
