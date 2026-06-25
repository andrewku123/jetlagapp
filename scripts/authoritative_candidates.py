"""Authoritative-source candidates for the POI pipeline.

Third discovery source (after Google search + OSM): official public registries.
Each source is normalized to the SAME candidate shape the OSM audit emits
    {category: [{name, lat, lon, query?}, ...]}
so they flow through the EXISTING Google icon-check (verify_gap_icons.py) -> the
Google "has the category icon" rule still governs; the list only widens recall.

Built-in automated sources (clean, programmatic):
  * mountain  -> GeoNames country dump (feature class T, codes PK/MT). Has coords.
  * hospital  -> CMS "Hospital General Information" (data.cms.gov). Address-only;
                 the icon-check geocodes it via searchText.

Generic intake for everything else (consulates, museums, libraries, zoos,
aquariums, parks, or ANY city/country list): drop a CSV in ./auth_lists/ with
columns  category,name,city,state[,lat,lon]  and it is picked up automatically.
This is the source-agnostic path — see gather-poi SKILL.md for the per-country
source tables (US + Canada).

Output: auth_gap_candidates.json (already gap-filtered against our curated pins).
"""
import os, csv, json, math, re, urllib.request, urllib.parse, zipfile, io
import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
play = poi_geo.load_play()
S, W, N, E = poi_geo.bbox_swne(play)
in_play = poi_geo.make_in_play(play)
cx = (W + E) / 2.0          # play-area centroid: used as a coarse search bias
cy = (S + N) / 2.0          # for address-only sources (no coords of their own)
curated = json.load(open(os.path.join(HERE, "poi_curated.json")))

# Address-only US sources can't be bbox-filtered, so pre-filter by the admin
# areas (counties) that intersect the play area; the icon-check + in_play then
# trims precisely. Per-city input — swap for a new play area.
US_COUNTIES = {"ALAMEDA", "CONTRA COSTA", "MARIN", "NAPA", "SAN FRANCISCO",
               "SAN MATEO", "SANTA CLARA", "SOLANO", "SONOMA"}
GEONAMES_COUNTRY = "US"     # GeoNames dump to use (US.zip, CA.zip, ...)


def norm(s):
    s = s.lower().replace("&", " and ").replace("+", " and ")
    return " ".join(re.sub(r"[^\w\s]", " ", s).split())


def km(a, b, c, d):
    return math.hypot((a - c) * 111.0, (b - d) * 88.0)


def already_have(cat, name, lat, lon):
    """True if this candidate already matches one of our curated pins."""
    nn = norm(name)
    toks = set(nn.split())
    for p in curated.get(cat, {}).get("places", []):
        pn = norm(p.get("name", ""))
        pt = set(pn.split())
        close = (lat is not None and "lat" in p and km(lat, lon,
                 p["lat"], p["lon"]) < 0.4)
        if pn == nn:
            return True
        if close and (toks <= pt or pt <= toks):
            return True
    return False


# ---- automated source: GeoNames peaks -------------------------------------
def geonames_mountains():
    cache = os.path.join(HERE, f"geonames_{GEONAMES_COUNTRY}.zip")
    if not os.path.exists(cache):
        url = f"https://download.geonames.org/export/dump/{GEONAMES_COUNTRY}.zip"
        print("  downloading", url)
        urllib.request.urlretrieve(url, cache)
    out = []
    with zipfile.ZipFile(cache) as z:
        txt = z.read(f"{GEONAMES_COUNTRY}.txt").decode("utf-8", "replace")
    for line in txt.splitlines():
        f = line.split("\t")
        if len(f) < 9 or f[6] != "T" or f[7] not in ("PK", "MT"):
            continue
        lat, lon = float(f[4]), float(f[5])
        if S <= lat <= N and W <= lon <= E and in_play(lon, lat):
            out.append({"name": f[1], "lat": lat, "lon": lon})
    return out


# ---- automated source: CMS hospitals --------------------------------------
def cms_hospitals():
    base = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"
    out, off = [], 0
    while True:
        url = f"{base}?limit=500&offset={off}"
        with urllib.request.urlopen(url, timeout=60) as r:
            rows = json.load(r).get("results", [])
        if not rows:
            break
        for x in rows:
            if x.get("state") != "CA":
                continue
            if (x.get("countyparish") or "").upper() not in US_COUNTIES:
                continue
            nm = (x.get("facility_name") or "").title()
            city = (x.get("citytown") or "").title()
            out.append({"name": nm, "lat": cy, "lon": cx,
                        "query": f"{nm}, {city}, CA"})
        off += 500
    return out


# ---- generic intake: any CSV in ./auth_lists/ -----------------------------
def csv_lists():
    d = os.path.join(HERE, "auth_lists")
    by_cat = {}
    if not os.path.isdir(d):
        return by_cat
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".csv"):
            continue
        for row in csv.DictReader(open(os.path.join(d, fn))):
            cat = (row.get("category") or "").strip()
            nm = (row.get("name") or "").strip()
            if not cat or not nm:
                continue
            lat = row.get("lat"); lon = row.get("lon")
            lat = float(lat) if lat else cy
            lon = float(lon) if lon else cx
            city = (row.get("city") or "").strip()
            st = (row.get("state") or "").strip()
            q = ", ".join(x for x in [nm, city, st] if x)
            by_cat.setdefault(cat, []).append({"name": nm, "lat": lat,
                                               "lon": lon, "query": q})
    return by_cat


def main():
    raw = {"mountain": geonames_mountains(), "hospital": cms_hospitals()}
    for cat, items in csv_lists().items():
        raw.setdefault(cat, []).extend(items)

    cand, total = {}, 0
    for cat, items in raw.items():
        seen, keep = set(), []
        for it in items:
            key = norm(it["name"])
            if key in seen:
                continue
            seen.add(key)
            if already_have(cat, it["name"], it.get("lat"), it.get("lon")):
                continue
            keep.append(it)
        cand[cat] = keep
        total += len(keep)
        print(f"{cat:15s} raw={len(items):5d} new(gap)={len(keep):5d}")
    json.dump(cand, open(os.path.join(HERE, "auth_gap_candidates.json"), "w"),
              indent=1)
    print(f"\ntotal new authoritative candidates: {total}")
    print("wrote auth_gap_candidates.json  (feed to verify_gap_icons.py)")


if __name__ == "__main__":
    main()
