"""Authoritative museums + public libraries -> auth_lists/{museum,library}.csv.

Source: the IMLS national registries, queried as ArcGIS feature layers (bbox-
filtered) so we never touch imls.gov directly (that host wouldn't load from CI):
  - museums  : the "Galleries, Libraries, Archives and Museums (GLAMs)" layer,
               which is derived from IMLS's Museum Universe Data File (MUDF).
               We keep TYPE_MAIN == 'MUS'.
  - libraries: the IMLS Public Library Survey "Public Library Outlet" layer
               (has real LONGITUD/LATITUDE per outlet).

Both come back with coordinates, so `authoritative_candidates.py` gap-filters
them against our pins and the icon-check geocodes survivors via Google searchText
+ the in_play polygon test (museum / library icons).

City-agnostic: the query bbox is derived from play-area.geojson.json via poi_geo,
so a new US metro needs zero edits here. (MUDF/GLAMs is US-only; for Canada use
the per-country museum registry — see the SKILL source table.)

Caveat: MUDF/GLAMs is intentionally *over-inclusive* (historical societies, dept
collections, art galleries). Expect the icon-check + your manual review to prune
a large fraction; libraries are clean but largely redundant with OSM+Google.
"""
import os, csv, json, urllib.request, urllib.parse
import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))

# IMLS-derived ArcGIS feature layers (public, no key). layer index 0.
GLAMS = ("https://services2.arcgis.com/njxlOVQKvDzk10uN/arcgis/rest/services/"
         "Galleries_Libraries_Archives_and_Museums_(GLAMs)/FeatureServer/0/query")
PLS = ("https://services8.arcgis.com/DlJzJLOZpPXmMpWi/arcgis/rest/services/"
       "Public_Library_Outlet_Data_File/FeatureServer/0/query")


def query(base, out_fields):
    s, w, n, e = poi_geo.bbox_swne(poi_geo.load_play())
    params = {
        "where": "1=1",
        "geometry": f"{w},{s},{e},{n}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "returnGeometry": "false",
        "resultRecordCount": "2000",
        "f": "json",
    }
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r).get("features", [])


def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "name", "city", "state", "lat", "lon"])
        w.writerows(rows)
    print(f"wrote {path}: {len(rows)} rows")


def main():
    # museums (GLAMs MUS)
    feats = query(GLAMS, "REPNAME,CITY,STATE,TYPE_MAIN,XLON,YLAT")
    mus = []
    for ft in feats:
        a = ft["attributes"]
        if a.get("TYPE_MAIN") != "MUS":
            continue
        nm = (a.get("REPNAME") or "").strip()
        if not nm:
            continue
        mus.append(["museum", nm.title(), (a.get("CITY") or "").title(),
                    a.get("STATE") or "", a.get("YLAT") or "", a.get("XLON") or ""])
    write_csv(os.path.join(HERE, "auth_lists", "museum.csv"), mus)

    # public libraries (PLS outlets)
    feats = query(PLS, "LIBNAME,CITY,STABR,LONGITUD,LATITUDE")
    lib = []
    for ft in feats:
        a = ft["attributes"]
        nm = (a.get("LIBNAME") or "").strip()
        if not nm:
            continue
        lib.append(["library", nm.title(), (a.get("CITY") or "").title(),
                    a.get("STABR") or "", a.get("LATITUDE") or "",
                    a.get("LONGITUD") or ""])
    write_csv(os.path.join(HERE, "auth_lists", "library.csv"), lib)


if __name__ == "__main__":
    main()
