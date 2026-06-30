#!/usr/bin/env python3
"""Collapse duplicate / sub-part POI pins by NAME (proximity-gated).

Google lists one physical place as many pins: a hospital campus = the main
hospital + its ER + each entrance + departments + affiliated clinics/office
buildings, and several individually clear the >=5-review bar, so they clump on
the map. This pass collapses the obvious duplicates the way a human would --
by reading the names -- using proximity only as a guard so two genuinely
distinct nearby places are never merged.

Two kinds of confident merge (no Google API; works on poi_curated.json):

  1. SUB-PART pins (entrance / parking / garage / building N / department /
     pavilion / address-only name / ...) are absorbed into the most-reviewed
     real POI within SUB_D metres.
  2. SAME-NAME pins: among the remaining "real" POIs, ones within NAME_D metres
     whose normalized name is identical, or one name's significant tokens are a
     subset of the other's, collapse to the most-reviewed.

Anything else that is merely *close* (distinct, unrelated names) is KEPT and,
if it shares any significant token with a neighbour, surfaced in the review
file under "close clusters to eyeball" -- never auto-merged.

Reads:  poi_curated.json   (full-area, icon + >=5 reviews)
Writes: poi_deduped.json, poi_dedup_review.md
Usage:  python dedup_poi.py [NAME_D] [SUB_D]
"""
import os, re, json, sys, math
from collections import defaultdict
from shapely import wkt as shp_wkt
from shapely.geometry import Point, shape as shp_shape
from shapely.prepared import prep
from shapely import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))

# Categories whose pins must lie strictly inside the play-area city polygons.
# Everything else gets a small shoreline buffer so pier/waterfront pins inside an
# in-play city (Exploratorium, USS Hornet...) survive. See build_play_area.py.
NATURAL_CATS = {"park", "mountain"}


def load_play_area():
    """Return (prepared_raw, prepared_buffered) play-area polygons, or (None,None)
    if not built yet (filter is then a no-op)."""
    raw = os.path.join(HERE, "play_area.geojson")
    buf = os.path.join(HERE, "play_area_buffered.geojson")
    if not os.path.exists(raw):
        return None, None
    g_raw = shp_shape(json.load(open(raw))["geometry"])
    g_buf = shp_shape(json.load(open(buf))["geometry"]) if os.path.exists(buf) else g_raw
    return prep(g_raw), prep(g_buf)


def in_play(p, cat, pa_raw, pa_buf):
    if pa_raw is None:
        return True
    poly = pa_raw if cat in NATURAL_CATS else pa_buf
    return poly.contains(Point(p["lon"], p["lat"]))


def load_osm(cat):
    """Load cached OSM footprints for a category -> dict(tree, geoms, names)."""
    path = os.path.join(HERE, f"osm_polys_{cat}.json")
    if not os.path.exists(path):
        return None
    feats = json.load(open(path))
    geoms, fnames, areas = [], [], []
    for f in feats:
        try:
            g = shp_wkt.loads(f["wkt"])
        except Exception:
            continue
        if g.is_empty:
            continue
        geoms.append(g)
        fnames.append(f.get("name", ""))
        areas.append(g.area * DEG2_M2)   # deg^2 -> m^2 (equirect. @ bay lat)
    if not geoms:
        return None
    return {"tree": STRtree(geoms), "geoms": geoms, "names": fnames,
            "areas": areas}


# equirectangular deg^2 -> m^2 around the bay (~37.7N); good enough to size parks
DEG2_M2 = (111320.0 * math.cos(math.radians(37.7))) * 110574.0
# big-park container thresholds: fold interior sub-park pins into the one
# flagship pin of any park whose OSM polygon area is in this range. The upper
# cap excludes the 135 km^2 "Golden Gate National Recreation Area" umbrella so
# the Presidio / Lands End keep their own pins instead of melting into it.
PARK_CONT_MIN_M2 = 3.0e5      # 0.3 km^2
PARK_CONT_MAX_M2 = 2.0e7      # 20 km^2

# park sub-features that are not their own destination -- a named amenity *within*
# a park (dog run, community garden, skate park, trail staging area, an entrance).
# These fold into the nearest real park pin that shares a distinctive name word.
PARK_SUBFEATURE_RE = re.compile(
    r"\b(dog\s*(park|run|play|training)|off[-\s]?leash|community\s+garden|"
    r"instructional\s+garden|demonstration\s+garden|skate\s*park|staging\s+area|"
    r"trail\s*head|\bentrance\b|boat\s+launch|kayak\s+launch)\b", re.I)
PARK_SUB_FOLD_M = 1200.0      # max child->parent distance for the name-matched fold
# weak geographic words that must NOT be the sole link for a sub-feature fold:
# "Eureka Valley Dog Play Area" must not fold into "Noe Valley Park" just because
# both say "valley". The fold needs a real shared name token (a place/brand word).
FOLD_WEAK = {
    "valley", "hill", "hills", "heights", "canyon", "ridge", "point", "waterfront",
    "linear", "spur", "town", "upper", "lower", "north", "south", "east", "west",
    "old", "new", "main", "river", "bay", "island", "meadow", "meadows",
    "vista", "view", "highland", "highlands", "mission", "willow", "cedar",
}


SRC = os.path.join(HERE, "poi_curated.json")
NAME_D = float(sys.argv[1]) if len(sys.argv) > 1 else 300.0   # same-name merge
SUB_D = float(sys.argv[2]) if len(sys.argv) > 2 else 400.0    # sub-part absorb
CO_D = 60.0          # two real pins this close are the same point -> merge
SUBSET_MAXREV = 50   # only absorb a subset-named pin if it's minor (< this)
# campus heuristics (cut future manual merges of hospital department/satellite
# pins): two pins that share >=2 distinctive (brand/place) words within BRAND2_D
# are the same complex; a MINOR pin (< MINOR_MAX reviews) sharing >=1 such word
# within BRAND1_D of a stronger anchor is a satellite of it. Strong, distinctly
# named pins (big review counts) are never auto-absorbed -> they stay manual.
BRAND2_D = 700.0     # >=2 shared distinctive words -> same complex
BRAND1_D = 500.0     # 1 shared distinctive word -> absorb only a MINOR pin
MINOR_MAX = 60       # a pin under this many reviews may be absorbed as a satellite
# categories whose pins form multi-building "campuses" sharing a real brand/place
# name (hospital systems). The campus heuristics ONLY run for these -- generic
# categories (parks, museums, ...) would over-merge distinct places that merely
# share a descriptive word, so they keep the conservative passes only.
CAMPUS_CATS = {"hospital"}

LABEL = {
    "museum": "Museums", "library": "Libraries", "movie_theater": "Movie Theaters",
    "hospital": "Hospitals", "zoo": "Zoos", "aquarium": "Aquariums",
    "amusement_park": "Amusement Parks", "park": "Parks", "golf_course": "Golf Courses",
    "consulate": "Consulates", "mountain": "Mountains", "stadium": "Sports Stadiums",
}

# Category-specific name patterns for pins that are never a valid POI of that
# category, regardless of review count / Google type, so they are auto-dropped
# every audit (no per-pin override needed). Libraries: a *high school* library is
# a campus facility, not a public library; a *Little Free Library* is a sidewalk
# book box (some have the icon + >=5 reviews, so neither the icon nor the review
# rule filters them). Note this only catches book boxes that say "Little Free
# Library"; un-named ones need the no-footprint review step (see gather-poi skill).
AUTO_DROP_NAME_RE = {
    "library": re.compile(r"\bhigh school\b|\blittle free librar", re.I),
}

# --- sub-part signals: a pin whose name is one of these is a piece of a bigger
#     same-category place, not a place of its own. Conservative on purpose.
# Only UNAMBIGUOUS structural pieces of a bigger place. Deliberately excludes
# words that can be a real facility's whole name (outpatient, urgent care,
# surgery center, dialysis, institute, ER) -- those stay as their own POI.
SUB_WORDS = [
    r"\bentrance\b", r"\bexit\b", r"\bparking\b", r"\bgarage\b", r"\bvalet\b",
    r"\bdrop[\s-]?off\b", r"\bloading dock\b", r"\bhelipad\b", r"\bambulance\b",
    r"\bbuilding\b", r"\bbldg\b", r"\bwing\b", r"\bannex\b",
    r"\bpavilion\b", r"\bsuite\b", r"\bste\.?\b", r"\bfloor\b", r"\bbasement\b",
    r"\bdepartment\b", r"\bdept\b", r"\bradiology\b", r"\bimaging\b",
    r"\bpharmacy\b", r"\blaborator(y|ies)\b", r"\bcafeteria\b", r"\bgift shop\b",
    r"\bmember services\b", r"\bregistration\b", r"\badmitting\b",
    r"\bbox office\b", r"\bticket\b", r"\bkiosk\b", r"\brestroom\b",
]
SUB_RE = re.compile("|".join(SUB_WORDS), re.I)
ADDRESS_RE = re.compile(r"^\s*\d{2,6}\s+[a-z]", re.I)   # "875 Blake Wilbur Drive"
BUILDING_LETTER_RE = re.compile(r"\bbuilding\s+[a-z0-9]\b", re.I)

STOP = {"the", "at", "of", "and", "a", "an", "for", "to", "in", "on", "&",
        "-", "|", "de", "la", "el"}

# generic category words: shared ONLY by these is not enough to call two pins the
# same place ("Oak Park" vs "Lincoln Park" both have "park").
GENERIC = {
    "park", "parks", "hospital", "hospitals", "medical", "center", "centre",
    "garden", "gardens", "plaza", "square", "playground", "dog", "play", "area",
    "community", "memorial", "public", "open", "space", "regional", "county",
    "city", "state", "mini", "neighborhood", "playlot", "field", "fields",
    "clinic", "health", "care", "services", "service", "foundation", "trail",
    "shoreline", "preserve", "reserve", "creek", "lake", "pond", "grove",
    "campus", "medicine", "skatepark", "skate", "garden", "rec", "recreation",
    # category words: two distinct same-category places sharing only this are not
    # the same place ("C.V. Starr Library" vs "Earth Science & Map Library")
    "library", "libraries", "branch",
    # street-type words: sharing only "street"/"ave" is not the same place
    "street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd",
    "way", "drive", "dr", "lane", "ln", "court", "ct", "place", "pl",
    "highway", "hwy", "terrace", "circle", "row",
    # diplomatic titles: distinct consulates share these + often one building, so
    # sharing only these must NOT merge them (only the country name is distinctive)
    "consulate", "consulates", "consulado", "consulados", "consul", "consular",
    "general", "embassy", "honorary", "office",
    # place/region words: two different places sharing only the city/region name
    # are not the same place ("San Jose Museum" vs "San Jose Library")
    "san", "francisco", "jose", "oakland", "california", "ca", "bay", "north",
    "south", "east", "west",
}
# structural piece words, stripped before checking a sub-part's real identity
STRUCTURAL = {
    "entrance", "exit", "parking", "lot", "garage", "valet", "drop", "off",
    "loading", "dock", "helipad", "ambulance", "building", "bldg", "wing",
    "annex", "pavilion", "suite", "ste", "floor", "basement", "department",
    "dept", "radiology", "imaging", "pharmacy", "laboratory", "lab",
    "cafeteria", "gift", "shop", "store", "member", "registration", "admitting",
    "box", "office", "ticket", "kiosk", "restroom", "main", "north", "south",
    "east", "west", "no", "number", "staging", "station", "ranger",
}


# headline nouns of the "main" place in a group. When there are NO review counts
# (future cities are pulled cheap/no-reviews), the representative can't be picked
# by popularity, so we prefer the pin carrying its category's flagship noun
# ("... Medical Center"/"... Hospital", "... Museum") over a department/branch.
ANCHOR = {
    "hospital": ["medical center", "medical centre", "medical foundation",
                 "hospital"],
    "museum": ["museum"],
    "library": ["library", "biblioteca"],
    "movie_theater": ["cinema", "theatre", "theater", "cineplex"],
    "zoo": ["zoo"],
    "aquarium": ["aquarium"],
    "amusement_park": ["amusement", "theme park"],
    "park": ["regional park", "state park", "national park", "preserve",
             "reserve", "open space", "park"],
    "golf_course": ["golf", "country club"],
    "consulate": ["consulate", "consulado", "embassy"],
    "mountain": ["mountain", "peak", "mount ", "mt "],
    "stadium": ["stadium", "park", "arena", "center", "coliseum", "ballpark", "field"],
}
_QUALIFIER_TAIL = re.compile(r"\([^)]*\)\s*$")
# medical specialty / department lead-ins: a pin named after a clinical
# specialty is a department, never the "main" campus pin, even when it carries
# an anchor noun ("Internal Medicine ... Palo Alto Medical Foundation").
_SPECIALTY_RE = re.compile(
    r"\b(internal medicine|family medicine|sports medicine|sleep medicine|"
    r"primary care|urgent care|maternal|fetal|pediatric|paediatric|obstetric|"
    r"gyne?colog|cardiolog|dermatolog|ophthalmolog|optometr|psychiatr|"
    r"oncolog|radiolog|imaging|orthop.?dic|urolog|neurolog|gastroenterolog|"
    r"endocrinolog|rheumatolog|allergy|immunolog|nephrolog|pulmonolog|"
    r"physical therapy|occupational therapy|rehab|infusion|dialysis|"
    r"chemical dependency)\b", re.I)


def is_specialty(name):
    return bool(_SPECIALTY_RE.search(name))


def anchor_hit(name, cat):
    nm = name.lower()
    return any(a in nm for a in ANCHOR.get(cat, []))


def has_qualifier(name):
    """A branch/department/disambiguated listing: a ':' or '|' section, or a
    trailing parenthetical ('Sunnyvale Center (401)', '... (formerly Bascom)').
    The 'main' pin is the clean, unqualified name."""
    if ":" in name or "|" in name:
        return True
    return bool(_QUALIFIER_TAIL.search(name.strip()))


def distinctive(name, drop_structural=False):
    toks = {t for t in sig_tokens(name) if not t.isdigit()} - GENERIC
    if drop_structural:
        toks = toks - STRUCTURAL
    return toks


def distinctive_full(name):
    """Brand/place words over the WHOLE name (norm() keeps only the pre-':' head,
    which loses the real identity of 'Family House: UCSF ...' / 'Pediatrics: ...'
    style listings). Drops generic + structural words so a shared token means a
    shared brand/place, not a shared 'building'/'center'."""
    s = re.sub(r"[^\w\s]", " ", name.lower())
    toks = {t for t in s.split() if t and t not in STOP and not t.isdigit()}
    return toks - GENERIC - STRUCTURAL


def hav(a, b, c, d):
    R = 6371000.0
    p = math.pi / 180
    x = (math.sin((c - a) * p / 2) ** 2
         + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(x))


def norm(name):
    s = re.split(r"[|(:—–]", name)[0]            # drop trailing "| Campus" etc.
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    toks = [t for t in s.split() if t and t not in STOP]
    return toks


def sig_tokens(name):
    return set(norm(name))


def is_sub(name):
    if ADDRESS_RE.search(name):
        return True
    if BUILDING_LETTER_RE.search(name):
        return True
    return bool(SUB_RE.search(name))


def subset(a, b):
    """a's significant tokens are a (proper, non-trivial) subset of b's."""
    if not a or not b or a == b:
        return False
    return a <= b and len(a) >= 1


def match_norm(s):
    s = s.lower().replace("&", " and ").replace("+", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def resolve_name(places, query):
    """Indices of places matching an override name (exact-normalized, else substring)."""
    qn = match_norm(query)
    exact = [i for i, p in enumerate(places) if match_norm(p["name"]) == qn]
    if exact:
        return exact
    return [i for i, p in enumerate(places)
            if qn and (qn in match_norm(p["name"]) or match_norm(p["name"]) in qn)]


def resolve_near(places, query, lat, lon, tol=200.0):
    """Index of the place matching `query` nearest to (lat,lon), within `tol` m.
    Used for `drop`/coord-pinned overrides where the name alone is ambiguous
    (chains like 'Sky Zone Trampoline Park' appear in several cities)."""
    cands = resolve_name(places, query)
    if not cands:
        return None
    best = min(cands, key=lambda i: hav(places[i]["lat"], places[i]["lon"], lat, lon))
    return best if hav(places[best]["lat"], places[best]["lon"], lat, lon) <= tol else None


def maps_link(p):
    pid = p.get("id")
    base = f"https://www.google.com/maps/search/?api=1&query={p['lat']}%2C{p['lon']}"
    return base + (f"&query_place_id={pid}" if pid else "")


def dedup_category(places, osm=None, forced_merge=None, forced_sep=None,
                   campus=False, cat=None):
    # campus=True turns on the brand/place "same medical campus" heuristics
    # (>=2 shared brand words within BRAND2_D, and minor-satellite absorption).
    # They are calibrated for hospital systems (Kaiser/UCSF/Sutter/Stanford) and
    # would over-merge distinct parks/museums that merely share a descriptive
    # word ("... Dog Park", "... Historical Society"), so they stay OFF for the
    # generic-name categories and only the conservative name/OSM passes run there.
    forced_merge = forced_merge or []
    forced_sep = forced_sep or []   # list of frozenset({idx, idx}) to keep apart
    n = len(places)
    pts = [(p["lat"], p["lon"]) for p in places]
    rev = [p.get("userRatingCount") or 0 for p in places]
    names = [p["name"] for p in places]
    toks = [sig_tokens(nm) for nm in names]
    dist = [distinctive(nm) for nm in names]              # non-generic words
    dfb = [distinctive_full(nm) for nm in names]          # whole-name brand words
    dsub = [distinctive(nm, drop_structural=True) for nm in names]
    sub = [is_sub(nm) for nm in names]
    real = [i for i in range(n) if not sub[i]]

    # 1) union-find merge among REAL pins: close + (same name or token subset)
    par = list(range(n))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    def union(x, y):
        par[find(x)] = find(y)

    def sep_blocks(i, j):
        """True if joining i,j would put a forced-separate pair in one group."""
        ri, rj = find(i), find(j)
        for pair in forced_sep:
            a, b = tuple(pair)
            ra, rb = find(a), find(b)
            if ra in (ri, rj) and rb in (ri, rj) and ra != rb:
                return True
        return False

    lim = max(NAME_D, BRAND2_D) if campus else NAME_D
    for ai in range(len(real)):
        for bi in range(ai + 1, len(real)):
            i, j = real[ai], real[bi]
            d = hav(pts[i][0], pts[i][1], pts[j][0], pts[j][1])
            if d > lim:
                continue
            # never merge two pins that don't share a distinctive (brand/place)
            # word -- this is what keeps distinct neighbours (Oak Park vs Lincoln
            # Park, UCSF Stanyan vs Hyde) separate even when co-located. On campus
            # categories use the whole-name brand words so ':'-style department
            # listings still match their parent; elsewhere use the conservative
            # pre-':' distinctive set (old behaviour) to avoid spurious matches.
            shared = (dfb[i] & dfb[j]) if campus else (dist[i] & dist[j])
            if not shared:
                continue
            if sep_blocks(i, j):
                continue
            # co-located + shares a real word => same physical place (e.g. old vs
            # new name of one hospital at one coordinate)
            if d <= CO_D:
                union(i, j)
                continue
            if toks[i] == toks[j]:
                union(i, j)
                continue
            # >=2 shared brand/place words within campus distance => same complex
            # (e.g. Kaiser Permanente Walnut Creek <dept>, UCSF Mission Bay ...).
            # The two SCVMC / John Muir WC-vs-Concord pairs are >BRAND2_D apart so
            # they stay distinct. (campus categories only)
            if campus and len(shared) >= 2 and d <= BRAND2_D:
                union(i, j)
                continue
            if d > NAME_D:
                continue
            # subset (one name is the other plus extra words) only collapses the
            # MINOR pin -- never merges two well-reviewed distinct hospitals
            if subset(toks[i], toks[j]) and rev[i] < SUBSET_MAXREV:
                union(i, j)
            elif subset(toks[j], toks[i]) and rev[j] < SUBSET_MAXREV:
                union(i, j)

    # a reviewer who writes a `merge [child, parent]` override is naming the pin
    # they want kept -> that parent must win rep selection (and never be absorbed
    # as a satellite below), even if a co-located sibling has more reviews.
    pref_rep = {p for _, p in forced_merge} - {c for c, _ in forced_merge}

    # representative pick, most-decisive first:
    #   1. reviewer-named merge parent (explicit choice of the pin to keep)
    #   2. a real pin over a structural sub-part
    #   3. most reviews (the popular flagship) WHEN we have review counts
    #   4. not named after a clinical specialty/department
    #   5. carries the category's flagship noun ("... Medical Center"/"Museum")
    #   6. a clean, unqualified name (no ':'/'|'/trailing parenthetical)
    #   7. shorter name
    # 3 sits above the name signals so already-reviewed cities keep their reps;
    # when a city is pulled with no reviews (all rev == 0) 4-7 pick the "main"
    # pin by name alone.
    def rep_score(i):
        return (1 if i in pref_rep else 0,
                0 if sub[i] else 1,
                rev[i],
                0 if is_specialty(names[i]) else 1,
                1 if anchor_hit(names[i], cat) else 0,
                0 if has_qualifier(names[i]) else 1,
                -len(names[i]))

    groups = defaultdict(list)
    for i in real:
        groups[find(i)].append(i)
    reps = []
    edges = []                      # (child, parent, source)
    for g in groups.values():
        rep = max(g, key=rep_score)
        reps.append(rep)
        for i in g:
            if i != rep:
                edges.append((i, rep, "name"))

    def sep_pair(i, j):
        return frozenset((i, j)) in forced_sep

    # 2a) absorb a MINOR representative (few reviews) into a stronger nearby rep
    #     that shares a distinctive brand/place word -> a campus satellite of a
    #     bigger hospital (UCSF Medical Records -> UCSF Medical Center, etc).
    #     Only minor pins move, into the NEAREST stronger anchor, so two strong
    #     distinct hospitals are never joined (UCSF Stanyan vs Hyde untouched).
    for r in (sorted(list(reps), key=lambda i: rev[i]) if campus else []):
        if rev[r] >= MINOR_MAX or r in pref_rep:
            continue
        cands = [s for s in reps
                 if s != r and rev[s] > rev[r] and (dfb[r] & dfb[s])
                 and hav(pts[r][0], pts[r][1], pts[s][0], pts[s][1]) <= BRAND1_D
                 and not sep_pair(r, s)]
        if not cands:
            continue
        anchor = min(cands, key=lambda s: hav(
            pts[r][0], pts[r][1], pts[s][0], pts[s][1]))
        edges.append((r, anchor, "name"))
        reps.remove(r)

    # 2) absorb each SUB pin into a real representative within SUB_D
    orphan_subs = []
    for i in range(n):
        if not sub[i]:
            continue
        cands = [r for r in reps
                 if hav(pts[i][0], pts[i][1], pts[r][0], pts[r][1]) <= SUB_D
                 and not sep_pair(i, r)]
        if not cands:
            orphan_subs.append(i)
            continue
        if dsub[i]:
            named = [r for r in cands if dsub[i] & dist[r]]
            if named:
                edges.append((i, max(named, key=lambda r: rev[r]), "name"))
            else:
                orphan_subs.append(i)
        else:
            edges.append((i, min(cands, key=lambda r: hav(
                pts[i][0], pts[i][1], pts[r][0], pts[r][1])), "name"))

    # 3) OSM-footprint pass: representatives that fall inside the SAME OSM
    #    hospital/park polygon are the same physical place -> collapse.
    after_name = reps + orphan_subs
    osm_child = set()
    if osm is not None:
        assign = {}
        for r in after_name:
            pt = Point(pts[r][1], pts[r][0])
            cand = osm["tree"].query(pt)
            inside = [gi for gi in cand if osm["geoms"][gi].covers(pt)]
            if not inside:
                continue
            # prefer the footprint whose name best matches the pin; then the
            # smallest (most specific) one -- so a pin that IS a distinct named
            # OSM feature stays on its own rather than melting into a big park.
            best = max(inside, key=lambda gi: (
                len(distinctive(names[r]) & distinctive(osm["names"][gi])),
                -osm["geoms"][gi].area))
            assign[r] = best
        byf = defaultdict(list)
        for r, f in assign.items():
            byf[f].append(r)
        for f, members in byf.items():
            if len(members) < 2:
                continue
            fname = osm["names"][f]
            frep = max(members, key=lambda r: (
                len(distinctive(names[r]) & distinctive(fname)), rev[r]))
            grouped = [frep]
            for r in members:
                if r == frep:
                    continue
                if any(sep_pair(r, g) for g in grouped):
                    continue
                edges.append((r, frep, "osm"))
                osm_child.add(r)
                grouped.append(r)

    # 3b) BIG-PARK container pass (park only): fold every interior sub-feature
    #     pin (named gardens, playgrounds, trails, "bench with view"...) into the
    #     single flagship pin of the large park whose OSM polygon contains it, so
    #     one big park reads as one POI. Uses the SMALLEST containing big-park
    #     footprint (so the Presidio wins over the huge GGNRA umbrella) and only
    #     when that footprint has a name-matching flagship pin inside it -- never
    #     collapses a cluster into an arbitrary member. Neighbourhood parks that
    #     merely sit just outside a big park's real polygon are untouched.
    if cat == "park" and osm is not None and osm.get("areas"):
        conts = [gi for gi in range(len(osm["geoms"]))
                 if PARK_CONT_MIN_M2 <= osm["areas"][gi] <= PARK_CONT_MAX_M2]
        if conts:
            absorbed = {c for c, _, _ in edges}
            standing = [r for r in after_name if r not in absorbed]
            cont_pt = {r: Point(pts[r][1], pts[r][0]) for r in standing}
            cont_members, cont_parent = {}, {}
            for gi in conts:
                g = osm["geoms"][gi]
                mem = [r for r in standing if g.covers(cont_pt[r])]
                cont_members[gi] = mem
                fdist = distinctive(osm["names"][gi])
                cand = [r for r in mem if distinctive(names[r]) & fdist]
                cont_parent[gi] = (max(cand, key=lambda r: rev[r])
                                   if cand else None)
            for r in standing:
                holding = sorted(
                    (gi for gi in conts if cont_parent[gi] is not None
                     and r in cont_members[gi]),
                    key=lambda gi: osm["areas"][gi])
                for gi in holding:
                    par = cont_parent[gi]
                    if par == r:
                        break               # r is this park's own flagship
                    if sep_pair(r, par):
                        continue
                    edges.append((r, par, "bigpark"))
                    break

    # 3c) PARK SUB-FEATURE fold (park only): a pin named like an amenity *inside* a
    #     park (dog run / community garden / skate park / trail staging area / an
    #     entrance) folds into the nearest real park pin that shares a distinctive
    #     name word (within PARK_SUB_FOLD_M). Name overlap is required so a dog
    #     park only ever folds into ITS park (e.g. "Buena Vista Dog Play Area" ->
    #     "Buena Vista Park"), never into an unrelated neighbour. Non-namesake
    #     cases (e.g. a dog run named for its street) are handled by explicit
    #     overrides instead. Generalises the reviewer's dog-park/garden decisions.
    if cat == "park":
        absorbed = {c for c, _, _ in edges}
        standing = [r for r in after_name if r not in absorbed]
        subs = [r for r in standing if PARK_SUBFEATURE_RE.search(names[r])]
        real = [r for r in standing if not PARK_SUBFEATURE_RE.search(names[r])]
        for r in subs:
            cw = distinctive(names[r]) - FOLD_WEAK
            cand = [(hav(pts[r][0], pts[r][1], pts[q][0], pts[q][1]), q)
                    for q in real if cw & (distinctive(names[q]) - FOLD_WEAK)]
            cand = [(d, q) for d, q in cand if d <= PARK_SUB_FOLD_M]
            if not cand:
                continue
            _, par = min(cand, key=lambda t: (t[0], -rev[t[1]]))
            if sep_pair(r, par):
                continue
            edges.append((r, par, "bigpark"))

    # 4) manual reviewer overrides: force each [child -> parent] merge. The
    #    parent is resolved to its current final representative; any automatic
    #    parenting of the child is dropped so it lands only where the reviewer
    #    put it. Children of a forced-merged rep follow it via the parent chain.
    if forced_merge:
        _, root = final_parent(edges)
        for child_i, parent_i in forced_merge:
            proot = root(parent_i)
            if proot == child_i:
                continue
            edges = [(c, p, s) for (c, p, s) in edges if c != child_i]
            edges.append((child_i, proot, "manual"))

    child_set = {c for c, _, _ in edges}
    final_kept = sorted([i for i in after_name if i not in child_set],
                        key=lambda i: -rev[i])
    return {
        "kept": final_kept, "names": names, "rev": rev, "pts": pts,
        "edges": edges,
    }


def final_parent(edges):
    """child -> immediate parent map, plus resolve to ultimate final rep."""
    parent = {c: p for c, p, _ in edges}

    def root(i):
        seen = set()
        while i in parent and i not in seen:
            seen.add(i)
            i = parent[i]
        return i
    return parent, root


def load_overrides(places, key, overrides, closed_names=frozenset()):
    """Resolve override names for a category to (forced_merge, forced_sep) on indices.
    closed_names = names auto-dropped as CLOSED_*; overrides targeting them are
    silently skipped (the pin is intentionally gone, so it's not a real warning)."""
    ov = overrides.get(key, {})
    fm, fs, rn, dn = [], [], [], set()
    revs = [p.get("userRatingCount") or 0 for p in places]
    def is_closed(nm):
        return match_norm(nm) in closed_names
    for entry in ov.get("merge", []):
        child_name, parent_name = entry[0], entry[1]
        # optional trailing [lat, lon] pins the exact PARENT pin when the parent
        # name is ambiguous (e.g. two same-named peaks 'Telegraph Hill') so the
        # reviewer can choose which duplicate survives.
        pcoord = (entry[2], entry[3]) if len(entry) >= 4 else None
        ci, pi = resolve_name(places, child_name), resolve_name(places, parent_name)
        if not pi:
            print(f"WARN [{key}] merge override parent not found: "
                  f"{parent_name!r} (child {child_name!r})")
            continue
        if pcoord is not None:
            parent_idx = resolve_near(places, parent_name, pcoord[0], pcoord[1])
            if parent_idx is None:
                print(f"WARN [{key}] merge override parent coord unresolved: "
                      f"{parent_name!r} {pcoord}")
                continue
        else:
            # parent name may match duplicate pins -> the most-reviewed is the survivor
            parent_idx = max(pi, key=lambda i: revs[i])
        # child name may match multiple pins (true duplicates) -> absorb all of them
        targets = [i for i in dict.fromkeys(ci) if i != parent_idx]
        if not targets:
            if not is_closed(child_name):
                print(f"WARN [{key}] merge override child unresolved: "
                      f"{child_name!r}({ci})->{parent_name!r}({pi})")
            continue
        for t in targets:
            fm.append((t, parent_idx))
    for a_name, b_name in ov.get("separate", []):
        ai, bi = resolve_name(places, a_name), resolve_name(places, b_name)
        if len(ai) == 1 and len(bi) == 1:
            fs.append(frozenset((ai[0], bi[0])))
        else:
            print(f"WARN [{key}] separate override unresolved: "
                  f"{a_name!r}({ai}) / {b_name!r}({bi})")
    for entry in ov.get("rename", []):
        old_name, new_name = entry[0], entry[1]
        coord = (entry[2], entry[3]) if len(entry) >= 4 else None
        oi = resolve_name(places, old_name)
        if len(oi) == 1:
            rn.append((oi[0], new_name, coord))
        else:
            print(f"WARN [{key}] rename override unresolved: {old_name!r}({oi})")
    # drop = remove a pin entirely (reviewer confirmed it doesn't exist). Each
    # entry is [name, lat, lon]: coords pin the exact pin so chains (several
    # same-named locations) drop only the one the reviewer flagged.
    for entry in ov.get("drop", []):
        name = entry[0]
        if len(entry) >= 3:
            di = resolve_near(places, name, entry[1], entry[2])
        else:
            cands = resolve_name(places, name)
            di = cands[0] if len(cands) == 1 else None
        if di is None:
            if not is_closed(name):
                print(f"WARN [{key}] drop override unresolved: {name!r} ({entry[1:]})")
        else:
            dn.add(di)
    return fm, fs, rn, dn


def main():
    curated = json.load(open(SRC))
    ovr_path = os.path.join(HERE, "poi_dedup_overrides.json")
    overrides = {k: v for k, v in json.load(open(ovr_path)).items()
                 if not k.startswith("_")} if os.path.exists(ovr_path) else {}
    out = {}
    md = [f"# POI de-dup review — name + OSM footprint\n",
          f"NAME_D={NAME_D:.0f}m (same-name merge), SUB_D={SUB_D:.0f}m (sub-part absorb), "
          f"then pins inside the SAME OSM hospital/park footprint collapse. "
          f"Representative kept = most-reviewed / best name match.\n"]
    table = ["| Category | before | after | name-merged | osm-merged | bigpark | manual |",
             "|---|---|---|---|---|---|---|"]
    viz = {}

    pa_raw, pa_buf = load_play_area()
    oop_total = 0   # POIs dropped for falling outside the play area

    for key in [k for k in LABEL if k in curated]:
        # Clip to the play area (union of transit-served city polygons). Natural
        # categories (park/mountain) must be strictly inside; others get a small
        # shoreline buffer so in-city pier pins survive. See build_play_area.py.
        n_before_clip = len(curated[key]["places"])
        curated[key]["places"] = [p for p in curated[key]["places"]
                                  if in_play(p, key, pa_raw, pa_buf)]
        oop_total += n_before_clip - len(curated[key]["places"])

        # auto-drop pins whose name marks them as never-valid for the category
        # (e.g. high-school / Little Free "libraries"). Runs every audit.
        adre = AUTO_DROP_NAME_RE.get(key)
        if adre:
            n_pre = len(curated[key]["places"])
            curated[key]["places"] = [p for p in curated[key]["places"]
                                      if not adre.search(p["name"])]
            n_auto = n_pre - len(curated[key]["places"])
            if n_auto:
                print(f"[{key}] auto-dropped {n_auto} by name rule "
                      f"(high-school / Little Free libraries)")

        # auto-drop only places Google reports CLOSED_PERMANENTLY. Backfilled pins
        # (authoritative/OSM) arrive without a status until refresh_business_status.py
        # fills it in -- this catches those plus any place perm-closed since the pull.
        # CLOSED_TEMPORARILY is intentionally NOT auto-dropped: Google's temp-closed
        # flag is often stale (many "temp closed" places are actually open), so those
        # are kept for manual review and dropped by override only when confirmed gone.
        closed_names = {match_norm(p["name"]) for p in curated[key]["places"]
                        if p.get("businessStatus") == "CLOSED_PERMANENTLY"}
        places = [p for p in curated[key]["places"]
                  if p.get("businessStatus") != "CLOSED_PERMANENTLY"]
        osm = load_osm(key)
        fm, fs, rn, dn = load_overrides(places, key, overrides, closed_names)
        r = dedup_category(places, osm, forced_merge=fm, forced_sep=fs,
                           campus=key in CAMPUS_CATS, cat=key)
        for idx, new_name, coord in rn:
            places[idx]["name"] = new_name
            if coord:
                places[idx]["lat"], places[idx]["lon"] = coord
        kept = [i for i in r["kept"] if i not in dn]
        kept_places = [places[i] for i in kept]
        out[key] = {"count": len(kept_places), "places": kept_places}
        # dropped pins vanish entirely -- also strip any merge spoke touching them
        # so a deleted pin never lingers as a child/parent on the review map.
        edges = [(c, p, s) for (c, p, s) in r["edges"] if c not in dn and p not in dn]
        _, root = final_parent(edges)
        n_name = sum(1 for _, _, s in edges if s == "name")
        n_osm = sum(1 for _, _, s in edges if s == "osm")
        n_bigpark = sum(1 for _, _, s in edges if s == "bigpark")
        n_manual = sum(1 for _, _, s in edges if s == "manual")
        man = f" −{n_manual} manual" if n_manual else ""
        bp = f" −{n_bigpark} bigpark" if n_bigpark else ""
        table.append(f"| {LABEL[key]} | {len(places)} | {len(kept_places)} "
                     f"| {n_name} | {n_osm} | {n_bigpark} | {n_manual} |")

        # group every absorbed child under its FINAL representative
        children = defaultdict(list)   # final rep -> [(child, source)]
        for c, _, s in edges:
            children[root(c)].append((c, s))

        rev = r["rev"]
        md.append(f"\n## {LABEL[key]} — {len(places)} → {len(kept_places)} "
                  f"(name −{n_name}, osm −{n_osm}{bp}{man})\n")
        rep_lines = []
        for rep in sorted(children, key=lambda i: -rev[i]):
            kids = children[rep]
            p = places[rep]
            head = f"- **[{p['name']}]({maps_link(p)})** ({rev[rep]} rev) absorbs:"
            kid_s = "; ".join(
                f"[{places[c]['name']}]({maps_link(places[c])})({rev[c]}"
                f"{',osm' if s=='osm' else ',park' if s=='bigpark' else ',manual' if s=='manual' else ''})"
                for c, s in sorted(kids, key=lambda cs: -rev[cs[0]]))
            rep_lines.append(head + " " + kid_s)
        md.append((f"\n**Merged ({len(rep_lines)} groups):**\n" + "\n".join(rep_lines) + "\n")
                   if rep_lines else "\n_No merges._\n")

        # viz payload: groups (rep + colored child spokes) and untouched singles
        absorbed_set = {c for c, _, _ in edges}
        groups = []
        for rep in sorted(children, key=lambda i: -rev[i]):
            groups.append({
                "rep": {"n": places[rep]["name"], "lat": places[rep]["lat"],
                        "lon": places[rep]["lon"], "r": rev[rep],
                        "id": places[rep].get("id")},
                "kids": [{"n": places[c]["name"], "lat": places[c]["lat"],
                          "lon": places[c]["lon"], "r": rev[c], "src": s,
                          "id": places[c].get("id")}
                         for c, s in sorted(children[rep], key=lambda cs: -rev[cs[0]])],
            })
        singles = [{"n": places[i]["name"], "lat": places[i]["lat"],
                    "lon": places[i]["lon"], "r": rev[i], "id": places[i].get("id")}
                   for i in kept if i not in children and i not in absorbed_set]
        viz[key] = {"label": LABEL[key], "groups": groups, "singles": singles,
                    "before": len(places), "after": len(kept_places)}

    md = [md[0], md[1], "\n".join(table), "\n"] + md[2:]
    open(os.path.join(HERE, "poi_dedup_review.md"), "w").write("\n".join(md))
    json.dump(out, open(os.path.join(HERE, "poi_deduped.json"), "w"), indent=1)
    with open(os.path.join(HERE, "poi_merge_viz.js"), "w") as f:
        f.write("window.VIZ=")
        json.dump(viz, f)
        f.write(";")
    print("\n".join(table))
    if pa_raw is not None:
        print(f"\nplay-area clip: dropped {oop_total} POIs outside the city polygons")
    print("\nwrote poi_deduped.json + poi_dedup_review.md + poi_merge_viz.js")


if __name__ == "__main__":
    main()
