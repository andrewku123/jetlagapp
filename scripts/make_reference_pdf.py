#!/usr/bin/env python3
"""Generate the Jet Lag: Hide & Seek reference card PDF for a game size + region.

Page 1 is the question deck: every question card for the chosen size, with its
draw/keep cost, answer window and checkbox subject list. Page 2 is the play-area
reference: station profiles (altitude, name length, nearest airport, line),
counties, cities, airports and the in-play POI inventory.

Rules that apply to every question (answer window consequences, what to send the
hider, tie-breaks, the end-game escape hatch) live once in the header strip
instead of being repeated on each card.

    python3 scripts/make_reference_pdf.py --region bay
"""
import argparse, json, collections, html, os, re, sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
from poi_geo import load_play, make_in_play

# ---------- region ----------
# A map carries its game size, so the deck follows from `--region` alone. The
# size itself is a judgement call made with the user (never derived from station
# count or area) and lives in src/data/region-sizes.json, which the app reads
# too — printing a deck the app doesn't agree with would be worse than useless.
REGIONS = {
    "bay": {"label": "Bay Area", "prefix": "", "app_id": "bayarea"},
    "la": {"label": "LA Metro", "prefix": "la.", "app_id": "la"},
    "sfmuni": {"label": "SF Muni", "prefix": "sfmuni.", "app_id": "sfmuni"},
    "dc": {"label": "Washington DC", "prefix": "dc.", "app_id": "dc"},
}
REGION_SIZES = json.load(
    open(os.path.join(REPO, "src", "data", "region-sizes.json")))
SIZES = ("small", "medium", "large")

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--region", default="bay", choices=sorted(REGIONS),
                help="which map to print; also sets the game size (default bay)")
ap.add_argument("--size", default=None, choices=SIZES,
                help="override the map's own size (rarely needed)")
ap.add_argument("--out", default=None, help="output PDF path")
ARGS = ap.parse_args()
REGION = REGIONS[ARGS.region]
SIZE = ARGS.size or REGION_SIZES[REGION["app_id"]]
BIG = SIZE in ("medium", "large")  # "add for Medium & Large"
LARGE = SIZE == "large"


def data(name):
    return os.path.join(REPO, "src", "data", REGION["prefix"] + name)


ST = json.load(open(data("stations.json")))
POI = json.load(open(data("poi.json")))
M2FT = 3.28084

# ---------- station-derived data ----------
def clean_city(c):
    return re.sub(r"\s+(city|town|CDP)$", "", c).strip()


county_counts = collections.Counter(s["county"] for s in ST if s.get("county"))
city_counts = collections.Counter(clean_city(s["city"]) for s in ST if s.get("city"))
airport_counts = collections.Counter(s["nearestAirport"] for s in ST if s.get("nearestAirport"))
line_counts = collections.Counter(l for s in ST for l in s.get("lines", []))

# altitude histogram (feet)
elevs_ft = [s["elevation"] * M2FT for s in ST if s.get("elevation") is not None]
BIN = 50
nbins = max(1, int(max(elevs_ft) // BIN) + 1) if elevs_ft else 1
alt_counts = [0] * nbins
for e in elevs_ft:
    alt_counts[min(int(e // BIN), nbins - 1)] += 1
alt_labels = [f"{i*BIN}\u2013{(i+1)*BIN}" for i in range(nbins)]

# name-length histogram
nl = collections.Counter(s["nameLength"] for s in ST)
nl_rows = [(L, nl.get(L, 0)) for L in range(min(nl), max(nl) + 1)]

# airports: mirrors AIRPORT_SITES in src/data/regions.ts. "Anything outside the
# play area doesn't exist", so an airport is only a valid answer on maps whose
# polygon contains it — stations carry airportDist to every site regardless.
AIRPORT_SITES = {
    "SFO": ("San Francisco Intl", 37.619083, -122.381597),
    "OAK": ("SF Bay Oakland Intl", 37.719016, -122.219595),
    "SJC": ("San Jose Mineta Intl", 37.363510, -121.928648),
    "LAX": ("Los Angeles Intl", 33.942560, -118.408530),
    "LGB": ("Long Beach", 33.817650, -118.152270),
}
in_play = make_in_play(load_play(path=data("play-area.geojson.json")))
AIRPORTS = [(f"{c} \u2014 {name}", f"{lat:.6f}, {lon:.6f}")
            for c, (name, lat, lon) in sorted(
                AIRPORT_SITES.items(), key=lambda kv: (-airport_counts[kv[0]], kv[0]))
            if in_play(lon, lat)]

# extremes: the stations that bound the play area, useful for sanity-checking a
# radar circle or a thermometer bisector before committing to it. Ties are all
# printed — naming one of two equally-short stations would be a lie.
def _ext(key, top=False, fmt=None):
    vals = [s for s in ST if s.get(key) is not None]
    best = (max if top else min)(s[key] for s in vals)
    tied = sorted((s["name"] for s in vals if s[key] == best))
    shown = " \u00b7 ".join(tied[:3]) + (f" +{len(tied)-3}" if len(tied) > 3 else "")
    return f"{shown} ({fmt(best)})" if fmt else shown


EXTREMES = [
    ("Highest", _ext("elevation", True, lambda v: f"{v*M2FT:,.0f} ft")),
    ("Lowest", _ext("elevation", False, lambda v: f"{v*M2FT:,.0f} ft")),
    ("Longest name", _ext("nameLength", True, str)),
    ("Shortest name", _ext("nameLength", False, str)),
    ("Northernmost", _ext("lat", True)),
    ("Southernmost", _ext("lat")),
    ("Easternmost", _ext("lon", True)),
    ("Westernmost", _ext("lon")),
]

POI_LABELS = [
    ("park", "Parks"), ("museum", "Museums"), ("library", "Libraries"),
    ("movie_theater", "Movie theaters"), ("hospital", "Hospitals"),
    ("golf_course", "Golf courses"), ("consulate", "Foreign consulates"),
    ("mountain", "Mountains"), ("amusement_park", "Amusement parks"),
    ("stadium", "Sports stadiums"), ("zoo", "Zoos"), ("aquarium", "Aquariums"),
]

# ---------- question deck ----------
# gate: 'all' = every size, 'ml' = medium & large, 'lg' = large only,
# 'own' = our own question, not in the official book -> every size.
ALL, ML, LG, OWN = "all", "ml", "lg", "own"


def keep(gate):
    return gate in (ALL, OWN) or (gate == ML and BIG) or (gate == LG and LARGE)


def gated(items):
    return [i for i in items if keep(i[-1])]


MATCHING = gated([
    ("Commercial airport", ALL), ("Transit line", ALL),
    ("Station name length", ALL), ("Street or path", ALL),
    ("1st admin div. (state)", ALL), ("2nd admin div. (county)", ALL),
    ("3rd admin div. (city)", ALL), ("4th admin div. (neighborhood)", ALL),
    ("Mountain", ALL), ("Landmass", ALL), ("Park", ALL),
    ("Amusement park", ALL), ("Zoo", ALL), ("Aquarium", ALL),
    ("Golf course", ALL), ("Museum", ALL), ("Movie theater", ALL),
    ("Sports stadium", OWN), ("Hospital", ALL), ("Library", ALL),
    ("Foreign consulate", ALL),
])
MEASURING = gated([
    ("A commercial airport", ALL), ("A high-speed train line", ALL),
    ("A rail station", ALL), ("An international border", ALL),
    ("A 1st admin. div. border (state)", ALL),
    ("A 2nd admin. div. border (county)", ALL),
    ("A coastline", ALL), ("Sea level (altitude)", ALL),
    ("A body of water", ALL), ("A mountain", ALL), ("A park", ALL),
    ("An amusement park", ALL), ("A zoo", ALL), ("An aquarium", ALL),
    ("A golf course", ALL), ("A museum", ALL), ("A movie theater", ALL),
    ("A sports stadium", OWN), ("A hospital", ALL), ("A library", ALL),
    ("A foreign consulate", ALL),
    ("ZIP code (smaller / larger)", OWN), ("Temperature (hotter / colder)", OWN),
])
RADAR = ["\u00bc", "\u00bd", "1", "3", "5", "10", "25", "50", "100"]
THERMO = [v for v, g in [("\u00bd", ALL), ("3", ALL), ("10", ML), ("50", LG)] if keep(g)]
TENTACLES_1MI = ["Museums", "Libraries", "Movie theaters", "Hospitals"] if BIG else []
TENTACLES_15MI = ["Metro lines", "Zoos", "Aquariums", "Amusement parks"] if LARGE else []

# (title, requirement, blocked in the end game?, gate) — requirements verbatim
# from the investigation book.
PHOTO = gated([
    ("Tree", "Must include the entire tree.", False, ALL),
    ("The sky", "Place phone on ground, shoot directly up, no zoom.", False, ALL),
    ("You", "Selfie mode, perpendicular to ground, arm extended, default lens, no zoom.", False, ALL),
    ("Widest street", "Must include both sides of the street; background not required.", False, ALL),
    ("Tallest structure in your sightline", "Tallest building from your perspective (not objectively tallest). Include top and both sides; top in the top 1/3 of the frame.", False, ALL),
    ("Any building visible from transit station", "Stand directly outside a station entrance (pick one if several). Include roof and both sides; top of building in the top 1/3 of the frame.", True, ALL),
    ("Longest sightline", "Longest line of sight from your perspective, not the objectively longest. If not frozen, you choose where to stand, but from there it must be the longest sightline in any direction. Ground fills at least the bottom 1/3 of the frame; the terminus \u2014 the horizon, or the base of whatever cuts it off \u2014 sits in at least the top 1/3 and must be visible.", False, OWN),
    ("Darkest area", "Darkest 2'\u00d72' section in your current sightline. Must contain 3 distinct elements. Litmus test: can someone match it if they visit the spot, allowing for lighting differences across times of day? (Screens / temporary lights don\u2019t count.)", False, OWN),
    ("Tallest building visible from transit station", "As above, standing directly outside a station entrance. The station itself can\u2019t count unless unrelated (e.g. MetLife building atop Grand Central).", True, ML),
    ("Trace nearest street / path", "Street/path must be visible on a mapping app; trace intersection to intersection (photo-editing app or trace on paper).", False, ML),
    ("2 buildings", "Bottom up to four stories.", False, ML),
    ("Restaurant interior", "No zoom. Take the picture through the window from outside.", True, ML),
    ("Train platform", "5'\u00d75' section with 3 distinct elements.", True, ML),
    ("Park", "No zoom, perpendicular to ground. Must stand 5 feet from any obstruction.", True, ML),
    ("Grocery store aisle", "No zoom. Stand at the end of the aisle, shoot directly down.", True, ML),
    ("Place of worship", "5'\u00d75' section with 3 distinct elements (litmus test: could someone match it by visiting the spot?).", True, ML),
    ("\u00bd mile of streets traced", "Must be continuous, include 5 turns, no doubling back. North\u2013south oriented. Must be traceable on a map.", False, LG),
    ("Tallest mountain visible from transit station", "Tallest from your perspective. Max 3\u00d7 zoom; top in the top 1/3 of the frame.", True, LG),
    ("Biggest body of water in your zone", "Max 3\u00d7 zoom. Must include both sides or the horizon. Counts partially if only a portion is inside.", False, LG),
    ("5 buildings", "Bottom up to four stories.", False, LG),
])
INSIDE = [
    ("Floor in a building", "Higher or lower floor than mine? Both players must be in the same building; a tie answers <b>lower</b>. Send your floor.", False),
    ("Traffic (5-min foot count)", "Count the people passing within 15 ft of you over 5 minutes, rounded to 2 significant figures (137 \u2192 140). Send your own count.", False),
]
PHOTO_WINDOW = "20 min" if LARGE else "10 min"

# ---------- HTML helpers ----------
def boxes(items):
    lis = "".join(f'<li><span class="cb"></span>{html.escape(label)}</li>'
                  for label, _ in items)
    return f'<ul class="chk">{lis}</ul>'


def detail_boxes(items):
    """Checkbox + bold title with its requirement underneath (photo & inside)."""
    lis = []
    for title, req, eg in ((i[0], i[1], i[2]) for i in items):
        mark = ' <span class="egm">&dagger;</span>' if eg else ''
        lis.append(f'<li><span class="cb"></span><span class="pt">'
                   f'<b>{html.escape(title)}</b>{mark}<br>'
                   f'<span class="pd">{req}</span></span></li>')
    return f'<ul class="chk detail">{"".join(lis)}</ul>'


def scale(items, unit="mi", custom=False):
    cells = "".join(f'<div class="sc"><span class="cb"></span>'
                    f'<span class="num">{v}</span></div>' for v in items)
    extra = ('<div class="sc"><span class="cb"></span>'
             '<span class="num">Custom</span></div>') if custom else ''
    return f'<div class="scale">{cells}<div class="sc unit">{unit}</div>{extra}</div>'


def card(title, cost, window, body, prompt=None, slim=False):
    p = f'<p class="prompt">{prompt}</p>' if prompt else ''
    return (f'<div class="card{" slim" if slim else ""}">'
            f'<h2>{title} <span class="dk">{cost}</span>'
            f'<span class="tm">&le; {window}</span></h2>{p}{body}</div>')


cards = []
cards.append(card("Matching", "draw 3, keep 1", "5 min", boxes(MATCHING),
                  prompt='"Is your nearest ___ the same as mine?"'))
cards.append(card("Measuring", "draw 3, keep 1", "5 min", boxes(MEASURING),
                  prompt='"Compared to me, are you closer to or further from ___?"'))
cards.append(card("Radar", "draw 2, keep 1", "5 min", scale(RADAR, custom=True), slim=True,
                  prompt='"Are you within ___ of me?" Yes = keep inside the circle, '
                         'No = keep outside. <b>Custom</b>: seekers may name any distance.'))
cards.append(card("Thermometer", "draw 2, keep 1", "5 min", scale(THERMO), slim=True,
                  prompt='"I\u2019ve just traveled (at least) ___ &mdash; am I hotter or colder?"'))
if TENTACLES_1MI:
    body = ('<p class="grp">Within 1 mile</p>' + boxes([(t, None) for t in TENTACLES_1MI]))
    if TENTACLES_15MI:
        body += ('<p class="grp">Within 15 miles</p>'
                 + boxes([(t, None) for t in TENTACLES_15MI]))
    cards.append(card("Tentacles", "draw 4, keep 2", "5 min", body, slim=True,
                      prompt='"Of all the ___ within ___ of you, which are you closest to?" '
                             '(The hider must also be within that distance.)'))
cards.append(card("Photo", "draw 1", PHOTO_WINDOW, detail_boxes(PHOTO)))
cards.append(card("Inside", "draw 3, keep 1", "5 min", detail_boxes(INSIDE), slim=True,
                  prompt='Both players must be indoors. If the hider is outdoors '
                         '(or, for Floor, in another building) they answer '
                         '<b>"I can\u2019t answer"</b>.'))
# number the cards in the order they print
cards = [c.replace("<h2>", f"<h2>{i} &middot; ", 1) for i, c in enumerate(cards, 1)]

# ---------- reference page ----------
def hgrid(rows, caption, nrows=3):
    cells = [f'<span class="lab">{html.escape(str(a))}</span><span class="val">{c}</span>'
             for a, c in rows]
    ncols = -(-len(cells) // nrows)
    cells += [""] * (nrows * ncols - len(cells))
    body = "".join("<tr>" + "".join(f"<td>{cells[r*ncols+col]}</td>" for col in range(ncols))
                   + "</tr>" for r in range(nrows))
    return f'<table class="hg"><caption>{caption}</caption><tbody>{body}</tbody></table>'


def tblcard(title, badge, body):
    return (f'<div class="card tbl"><h2>{title} <span class="dk">{badge}</span></h2>'
            f'{body}</div>')


def rblock(title, count, body):
    return (f'<div class="rblock"><h3>{title} <span class="cnt">{count}</span></h3>'
            f'{body}</div>')


def counted_list(counter):
    lis = "".join(f'<li>{html.escape(k)} <span class="n">{v}</span></li>'
                  for k, v in sorted(counter.items()))
    return f'<ul class="cols cnts">{lis}</ul>'


nstat = len(ST)
alt_card = tblcard("Stations by altitude", f"{nstat} stations",
                   hgrid([(a, c) for a, c in zip(alt_labels, alt_counts) if c],
                         "Elevation band (ft) &rarr; stations"))
nl_card = tblcard("Stations by name length", f"{nstat} stations",
                  hgrid([(L, c) for L, c in nl_rows if c], "Name length &rarr; stations"))
# no airport in play -> the airport questions are log-only in the app, so
# neither airport block is printed (mirrors HAS_AIRPORTS in regions.ts).
air_card = tblcard(
    "Stations by nearest airport", f"{len(AIRPORTS)} airports",
    hgrid([(c, airport_counts[c]) for c, _ in
           ((a.split(" \u2014 ")[0], b) for a, b in AIRPORTS)],
          "Airport &rarr; stations", nrows=1)) if AIRPORTS else ""

airports_html = ('<ul class="plain air">' + "".join(
    f'<li><span class="aname">{html.escape(a)}</span><span class="coord">{c}</span></li>'
    for a, c in AIRPORTS) + '</ul>')

poi_rows = [(lab, len(POI.get(k, []))) for k, lab in POI_LABELS]
poi_html = ('<ul class="cols cnts">' + "".join(
    f'<li>{lab} <span class="n">{n}</span></li>' for lab, n in poi_rows) + '</ul>')

extremes_html = ('<ul class="plain ext">' + "".join(
    f'<li><span class="elab">{k}</span><span class="eval">{html.escape(v)}</span></li>'
    for k, v in EXTREMES) + '</ul>')

# blank grid to keep the running board on paper: what was asked, what came back.
log_rows = "".join(
    "<tr>" + f'<td class="num">{i}</td>' + "<td></td>" * 3 + "</tr>" for i in range(1, 15))
log_html = (f'<table class="log"><thead><tr><th></th><th>Question asked</th>'
            f'<th>Answer</th><th>Suspects left</th></tr></thead>'
            f'<tbody>{log_rows}</tbody></table>')

ref = "".join([
    alt_card, nl_card, air_card,
    rblock("Stations per line", len(line_counts), counted_list(line_counts)),
    rblock("Counties (in play)", len(county_counts), counted_list(county_counts)),
    rblock("Commercial airports", len(AIRPORTS), airports_html) if AIRPORTS else "",
    rblock("POIs in play", sum(n for _, n in poi_rows), poi_html),
    rblock("Edges of the play area", len(EXTREMES), extremes_html),
    rblock("Cities / municipalities", len(city_counts), counted_list(city_counts)),
])

doc = f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
@page {{ size: letter; margin: 0.5in; }}
* {{ box-sizing: border-box; }}
body {{ font-family: 'IBM Plex Sans', -apple-system, Helvetica, Arial, sans-serif; color:#1a1a1a; margin:0; }}
h1 {{ font-size:19px; margin:0 0 4px; }}
/* rules that apply to every question, stated once */
.rules {{ display:flex; gap:6px; margin:0 0 6px; }}
.rules div {{ flex:1; font-size:8.6px; line-height:1.25; color:#333; background:#f4f4f5;
  border:1px solid #e4e4e7; border-radius:5px; padding:3px 6px; }}
.rules b {{ color:#111; }}
.p1 {{ column-count:2; column-gap:12px; }}
.card {{ break-inside:avoid; border:1px solid #e2e2e2; border-radius:6px; padding:6px 8px;
  margin:0 0 5px; background:#fafafa; width:100%; }}
.ref .card.tbl {{ background:#fff; }}
.card h2 {{ font-size:13px; margin:0 0 4px; color:#111; }}
.dk {{ float:right; font-size:9.5px; font-weight:600; background:#111; color:#fff;
  padding:1px 6px; border-radius:8px; }}
.tm {{ float:right; font-size:9.5px; font-weight:600; color:#111; background:#fff;
  border:1px solid #cbcbcb; padding:0 6px; border-radius:8px; margin-right:4px; }}
.prompt {{ font-size:9.8px; margin:1px 0 2px; color:#222; }}
.grp {{ font-size:8.8px; font-weight:600; color:#555; margin:4px 0 0; }}
.egm {{ color:#c2410c; font-weight:700; }}
/* checkbox subject lists */
ul.chk {{ list-style:none; margin:4px 0 0; padding:0; columns:2; column-gap:10px; }}
ul.chk li {{ font-size:9.4px; margin:1px 0; break-inside:avoid; display:flex;
  align-items:flex-start; gap:4px; }}
.cb {{ display:inline-block; width:10px; height:10px; min-width:10px; border:1px solid #555;
  border-radius:2px; margin-top:1px; }}
ul.chk.detail {{ columns:1; }}
ul.chk.detail li {{ margin:1.5px 0; }}
.pt {{ display:block; font-size:9.3px; line-height:1.2; }}
.pd {{ color:#444; font-size:8.6px; font-weight:400; }}
/* radar / thermometer scales: checkbox above the number */
.scale {{ display:flex; flex-wrap:wrap; gap:9px; margin:3px 0 1px; }}
.sc {{ display:flex; flex-direction:column; align-items:center; }}
.sc .num {{ font-size:11px; margin-top:3px; color:#222; }}
.sc.unit {{ justify-content:flex-end; font-size:9.5px; color:#777; align-self:flex-end; }}
.page-break {{ break-before:page; }}
/* station-profile grids */
table.hg {{ width:100%; border-collapse:collapse; margin-top:4px; table-layout:fixed; }}
table.hg caption {{ caption-side:top; text-align:left; font-size:9px; color:#666; margin-bottom:3px; }}
table.hg td {{ border:1px solid #e2e2e2; padding:3px 2px; text-align:center; vertical-align:middle; }}
table.hg .lab {{ display:block; font-size:8.3px; color:#555; line-height:1.1; }}
table.hg .val {{ display:block; font-size:11px; font-weight:600; font-variant-numeric:tabular-nums; }}
/* reference lists */
.ref {{ column-count:2; column-gap:16px; }}
.rblock {{ break-inside:avoid; margin-bottom:9px; }}
.rblock h3 {{ font-size:12px; margin:0 0 4px; color:#111; border-bottom:1px solid #ddd;
  padding-bottom:2px; break-after:avoid; }}
.card.tbl {{ break-inside:avoid; }}
.cnt {{ float:right; font-size:9px; color:#fff; background:#c2410c; padding:0 6px; border-radius:8px; }}
ul.cols {{ columns:2; column-gap:10px; margin:0; padding-left:15px; }}
ul.cols li {{ font-size:9px; margin:1px 0; break-inside:avoid; }}
ul.cnts {{ list-style:none; padding-left:0; }}
ul.cnts li {{ display:flex; justify-content:space-between; gap:6px; border-bottom:1px dotted #e5e5e5; }}
ul.cnts .n {{ font-variant-numeric:tabular-nums; color:#444; font-weight:600; }}
ul.plain {{ list-style:none; margin:0; padding:0; }}
ul.plain li {{ font-size:10px; margin:0 0 4px; }}
ul.plain.air li {{ display:flex; flex-wrap:wrap; justify-content:space-between; gap:2px 8px;
  align-items:baseline; }}
.aname {{ font-weight:700; font-size:10px; }}
ul.plain.ext li {{ display:flex; justify-content:space-between; gap:8px; font-size:9px;
  border-bottom:1px dotted #e5e5e5; margin:0 0 2px; }}
.elab {{ color:#666; }}
.eval {{ font-weight:600; text-align:right; }}
/* running board: blank rows to fill in during play */
table.log {{ width:100%; border-collapse:collapse; margin-top:2px; }}
table.log th {{ font-size:8.5px; color:#666; font-weight:600; text-align:left;
  border-bottom:1px solid #ddd; padding:1px 4px; }}
table.log td {{ border:1px solid #e2e2e2; height:15px; }}
table.log td.num {{ width:16px; font-size:8px; color:#999; text-align:center; }}
table.log th:nth-child(2) {{ width:52%; }} table.log th:nth-child(4) {{ width:16%; }}
.coord {{ font-size:9px; color:#555; font-family:'IBM Plex Mono', monospace; }}
footer {{ font-size:8px; color:#888; margin-top:8px; }}
</style></head><body>
<h1>Jet Lag: Hide &amp; Seek &mdash; Question Deck ({SIZE.title()}) &middot; {REGION['label']}</h1>
<div class="rules">
  <div><b>Answer window</b> is on each card. Miss it and the hider\u2019s clock pauses
    until they answer &mdash; and they draw <b>no</b> card.</div>
  <div><b>Send the hider coordinates</b>, never place names: your position, your
    nearest subject, your start and stop points.</div>
  <div><b>Ties go to the lower answer</b> &mdash; equal distance is <b>closer</b>,
    the same floor is <b>lower</b>.</div>
  <div><span class="egm">&dagger;</span> <b>End game:</b> needs the station or a set
    venue. If the hider can\u2019t reach it, \u201cI cannot answer\u201d is valid and they
    <b>still draw a card</b>.</div>
</div>
<div class="p1">{"".join(cards)}</div>
<div class="ref page-break">{ref}</div>
<div class="rblock"><h3>Question log</h3>{log_html}</div>
<footer>Question subjects, draw/keep costs, answer windows &amp; end-game rules from the
official Jet Lag: Hide &amp; Seek investigation book and quick start guide. Station and POI
figures are this map\u2019s own data.</footer>
</body></html>"""

open("/tmp/reference.html", "w").write(doc)
print(f"size={SIZE} region={ARGS.region} cards={len(cards)} "
      f"matching={len(MATCHING)} measuring={len(MEASURING)} thermo={len(THERMO)} "
      f"tentacles={len(TENTACLES_1MI)+len(TENTACLES_15MI)} photo={len(PHOTO)} "
      f"stations={nstat} pois={sum(n for _, n in poi_rows)}")

OUT = ARGS.out or os.path.join(REPO, f"jetlag_reference_{ARGS.region}_{SIZE}.pdf")
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://localhost:29229")
    ctx = b.contexts[0] if b.contexts else b.new_context()
    pg = ctx.new_page()
    pg.goto("file:///tmp/reference.html", wait_until="networkidle")
    pg.evaluate("document.fonts.ready")  # ensure IBM Plex Sans is loaded
    pg.emulate_media(media="print")
    pg.pdf(path=OUT, print_background=True, prefer_css_page_size=True)
    pg.close()
print("wrote", OUT, os.path.getsize(OUT), "bytes")
