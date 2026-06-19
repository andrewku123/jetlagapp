#!/usr/bin/env python3
"""Generate the Jet Lag: Hide & Seek (Medium) reference card PDF.

Front page: the question deck in 3 columns (2 categories each), with draw/keep
and comprehensive photo conditions. Back: comprehensive play-area reference lists
(airports, counties, cities, water, mountains, golf, amusement parks, hospitals)
plus a vertical histogram of stations by altitude and a horizontal histogram of
stations by station-name length.
"""
import json, collections, html, subprocess, os, re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ST = json.load(open(f"{REPO}/src/data/stations.json"))
POI = json.load(open("/tmp/poi.json"))
M2FT = 3.28084

# ---------- station-derived data ----------
def clean_city(c):
    return re.sub(r"\s+(city|town|CDP)$", "", c).strip()

counties = sorted({s["county"] for s in ST if s.get("county")})
cities = sorted({clean_city(s["city"]) for s in ST if s.get("city")})

# altitude histogram (feet), vertical
elevs_ft = [s["elevation"] * M2FT for s in ST if s.get("elevation") is not None]
ALT_BINS = list(range(0, 550, 50))  # 0..500 ft in 50-ft bins
alt_counts = [0] * (len(ALT_BINS) - 1)
for e in elevs_ft:
    idx = min(int(e // 50), len(alt_counts) - 1)
    alt_counts[idx] += 1
alt_labels = [f"{ALT_BINS[i]}\u2013{ALT_BINS[i+1]}" for i in range(len(alt_counts))]

# name-length histogram, horizontal
nl = collections.Counter(s["nameLength"] for s in ST)
nl_min, nl_max = min(nl), max(nl)
nl_rows = [(L, nl.get(L, 0)) for L in range(nl_min, nl_max + 1)]

# ---------- POI curation ----------
peaks = []  # (name, ele_ft)
water = {"bay": set(), "lake": set(), "reservoir": set(), "lagoon": set()}
golf, theme, hospital, zoos = set(), set(), set(), set()
for el in POI["elements"]:
    t = el.get("tags", {}); n = t.get("name")
    if not n:
        continue
    if t.get("natural") == "peak":
        ele = t.get("ele")
        try:
            ele = float(ele) * M2FT
        except (TypeError, ValueError):
            ele = None
        peaks.append((n, ele))
    elif t.get("leisure") == "golf_course":
        golf.add(n)
    elif t.get("tourism") == "theme_park":
        theme.add(n)
    elif t.get("amenity") == "hospital":
        hospital.add(n)
    elif t.get("tourism") == "zoo":
        zoos.add(n)
    elif t.get("natural") == "bay":
        water["bay"].add(n)
    elif t.get("water") in ("lake", "reservoir", "lagoon") or t.get("natural") == "water":
        ws = t.get("water")
        if ws in water:
            water[ws].add(n)

# mountains: named peaks >= 1500 ft, sorted by elevation desc (notable summits)
peaks_named = sorted({(n, e) for n, e in peaks if e is not None and e >= 1500},
                     key=lambda p: -p[1])
mountains = [f"{n} ({int(e):,} ft)" for n, e in peaks_named]

# bodies of water: drop minor coves/sloughs/harbors/ponds; keep bays, straits,
# named lakes, lagoons and reservoirs.
DROP = re.compile(r"(Cove|Slough|Harbor|Harbour|Channel|Basin|Forebay|Pond|Dam|"
                  r"Arroyo|River|Strait Yacht|Yacht|Marina|estuarial)", re.I)
bodies = set()
for n in water["bay"]:
    if not DROP.search(n) and ("Bay" in n or "Strait" in n or "Break" in n or "Lagoon" in n):
        bodies.add(n)
for n in water["lake"] | water["lagoon"]:
    if not DROP.search(n):
        bodies.add(n)
for n in water["reservoir"]:
    if not DROP.search(n) and ("Reservoir" in n or "Lake" in n):
        bodies.add(n)
bodies = sorted(bodies)
golf = sorted(golf)
theme = sorted(theme)
hospital = sorted(hospital)
zoos = sorted(zoos)

AIRPORTS = [
    ("SFO \u2014 San Francisco Intl", "37.619083, -122.381597"),
    ("OAK \u2014 SF Bay Oakland Intl", "37.719016, -122.219595"),
    ("SJC \u2014 San Jose Mineta Intl", "37.363510, -121.928648"),
]

# ---------- SVG histograms ----------
def svg_vertical(counts, labels, caption, color="#2563eb", w=520, h=210, pad_l=24, pad_b=42, pad_t=14):
    n = len(counts); mx = max(counts) or 1
    plot_w = w - pad_l - 8; plot_h = h - pad_b - pad_t
    bw = plot_w / n
    bars = []
    for i, c in enumerate(counts):
        bh = plot_h * c / mx
        x = pad_l + i * bw + bw * 0.12
        y = pad_t + (plot_h - bh)
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.76:.1f}" height="{bh:.1f}" fill="{color}"/>')
        if c:
            bars.append(f'<text x="{x+bw*0.38:.1f}" y="{y-2:.1f}" font-size="8" text-anchor="middle" fill="#444">{c}</text>')
        bars.append(f'<text x="{x+bw*0.38:.1f}" y="{h-pad_b+12:.1f}" font-size="7.5" text-anchor="end" fill="#555" transform="rotate(-45 {x+bw*0.38:.1f} {h-pad_b+12:.1f})">{labels[i]}</text>')
    axis = (f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+plot_h:.1f}" stroke="#999"/>'
            f'<line x1="{pad_l}" y1="{pad_t+plot_h:.1f}" x2="{w-8}" y2="{pad_t+plot_h:.1f}" stroke="#999"/>')
    cap = f'<text x="{w/2:.0f}" y="{h-4}" font-size="9" text-anchor="middle" fill="#333">{caption}</text>'
    return f'<svg viewBox="0 0 {w} {h}" width="100%" >{axis}{"".join(bars)}{cap}</svg>'

def svg_horizontal(rows, caption, color="#c2410c", w=520, rh=12, pad_l=44, pad_r=26, pad_t=6):
    mx = max(c for _, c in rows) or 1
    h = pad_t * 2 + rh * len(rows) + 16
    plot_w = w - pad_l - pad_r
    out = []
    for i, (L, c) in enumerate(rows):
        y = pad_t + i * rh
        bw = plot_w * c / mx
        out.append(f'<text x="{pad_l-3}" y="{y+rh-2:.1f}" font-size="7.5" text-anchor="end" fill="#555">{L}</text>')
        out.append(f'<rect x="{pad_l}" y="{y+1:.1f}" width="{bw:.1f}" height="{rh-3:.1f}" fill="{color}"/>')
        if c:
            out.append(f'<text x="{pad_l+bw+3:.1f}" y="{y+rh-2:.1f}" font-size="7.5" fill="#444">{c}</text>')
    out.append(f'<text x="{pad_l+plot_w/2:.0f}" y="{h-3}" font-size="9" text-anchor="middle" fill="#333">{caption}</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%">{"".join(out)}</svg>'

# station profiles rendered as tables (not graphs), per request
def html_table(rows, h1, h2, split=1):
    cells = [f"<td>{html.escape(str(a))}</td><td>{c}</td>" for a, c in rows]
    if split <= 1:
        body = "".join(f"<tr>{c}</tr>" for c in cells)
        head = f"<tr><th>{h1}</th><th>{h2}</th></tr>"
    else:
        per = -(-len(cells) // split)
        cols = [cells[i * per:(i + 1) * per] for i in range(split)]
        rows_out = []
        for r in range(per):
            tds = "".join(cols[c][r] if r < len(cols[c]) else "<td></td><td></td>"
                          for c in range(split))
            rows_out.append(f"<tr>{tds}</tr>")
        body = "".join(rows_out)
        head = "<tr>" + (f"<th>{h1}</th><th>{h2}</th>" * split) + "</tr>"
    return f'<table class="dt"><thead>{head}</thead><tbody>{body}</tbody></table>'

alt_rows = [(a, c) for a, c in zip(alt_labels, alt_counts) if c]
alt_table = html_table(alt_rows, "Elevation band (ft)", "Stations")
nl_table = html_table([(L, c) for L, c in nl_rows if c], "Name length", "Stations", split=2)

# ---------- HTML ----------
def ul(items, cls="cols"):
    lis = "".join(f"<li>{html.escape(i)}</li>" for i in items)
    return f'<ul class="{cls}">{lis}</ul>'

# ---------- question deck (Medium) ----------
# subjects: (label, app_supported); source = official Investigation Book.
MATCHING = [
    ("Commercial airport", True), ("Transit line", True),
    ("Station name length", True), ("Street or path", False),
    ("1st admin div. (state)", False), ("2nd admin div. (county)", True),
    ("3rd admin div. (city)", True), ("4th admin div. (neighborhood)", False),
    ("Mountain", False), ("Landmass", False), ("Park", False),
    ("Amusement park", False), ("Zoo", False), ("Aquarium", False),
    ("Golf course", False), ("Museum", False), ("Movie theater", False),
    ("Hospital", False), ("Library", False), ("Foreign consulate", False),
]
MEASURING = [
    ("A commercial airport", True), ("A high-speed train line", False),
    ("A rail station", False), ("An international border", False),
    ("A 1st admin. div. border (state)", False), ("A 2nd admin. div. border (county)", False),
    ("A 3rd admin. div. border (city)", False), ("A 4th admin. div. border (neighborhood)", False),
    ("Sea level (altitude)", True), ("A body of water", False),
    ("A coastline", False), ("A mountain", False), ("A park", False),
    ("An amusement park", False), ("A zoo", False), ("An aquarium", False),
    ("A golf course", False), ("A museum", False), ("A movie theater", False),
    ("A hospital", False), ("A library", False), ("A foreign consulate", False),
]
RADAR = ["\u00bc", "\u00bd", "1", "3", "5", "10", "25", "50", "100"]
THERMO = ["\u00bd", "3", "10"]
TENTACLES = ["Museums", "Libraries", "Movie theaters", "Hospitals"]
# photo (Medium = All-Games + Medium/Large set): (title, requirement, endgame_blocked?)
# requirements are verbatim from the official photo cards.
PHOTO = [
    ("Tree", "Must include the entire tree.", False),
    ("The sky", "Place phone on ground, shoot directly up, no zoom.", False),
    ("You", "Selfie mode, perpendicular to ground, arm extended, default lens, no zoom.", False),
    ("Widest street", "Must include both sides of the street; background not required.", False),
    ("Tallest structure in your sightline", "Tallest building from your perspective (not objectively tallest). Include top and both sides; top in the top 1/3 of the frame.", False),
    ("Any building visible from transit station", "Stand directly outside a station entrance (pick one if several). Include roof and both sides; top of building in the top 1/3 of the frame.", True),
    ("Tallest building visible from transit station", "As above, standing directly outside a station entrance. The station itself can\u2019t count unless unrelated (e.g. MetLife building atop Grand Central).", True),
    ("Trace nearest street / path", "Street/path must be visible on a mapping app; trace intersection to intersection (photo-editing app or trace on paper).", False),
    ("2 buildings", "Bottom up to four stories.", False),
    ("Restaurant interior", "No zoom. Take the picture through the window from outside.", True),
    ("Train platform", "5'\u00d75' section with 3 distinct elements.", True),
    ("Park", "No zoom, perpendicular to ground. Must stand 5 feet from any obstruction.", True),
    ("Grocery store aisle", "No zoom. Stand at the end of the aisle, shoot directly down.", True),
    ("Place of worship", "5'\u00d75' section with 3 distinct elements (litmus test: could someone match it by visiting the spot?).", True),
]

def boxes(items):
    out = []
    for label, app in items:
        badge = ' <span class="app ok">app</span>' if app else ''
        out.append(f'<li><span class="cb"></span>{html.escape(label)}{badge}</li>')
    return "<ul class=\"chk\">" + "".join(out) + "</ul>"

def photo_boxes(items):
    out = []
    for title, req, eg in items:
        mark = ' <span class="egm">&dagger;</span>' if eg else ''
        out.append(f'<li><span class="cb"></span><span class="pt">'
                   f'<b>{html.escape(title)}</b>{mark}<br>'
                   f'<span class="pd">{html.escape(req)}</span></span></li>')
    return "<ul class=\"chk photo\">" + "".join(out) + "</ul>"

def scale(items, unit="mi", custom=False):
    cells = "".join(
        f'<div class="sc"><span class="cb"></span><span class="num">{v}</span></div>'
        for v in items)
    custom_cell = ('<div class="sc"><span class="cb"></span>'
                   '<span class="num">Custom</span></div>') if custom else ''
    return (f'<div class="scale">{cells}<div class="sc unit">{unit}</div>'
            f'{custom_cell}</div>')

# per-card meta lines
META_FAIL = ('<p class="meta"><b>Answer window</b> &le; 5 min &middot; '
             'fail to answer in time &rarr; hider\u2019s clock pauses until answered '
             '&amp; they draw <b>no</b> card.</p>')
META_FAIL_PHOTO = ('<p class="meta"><b>Answer window</b> &le; 10 min (Medium) &middot; '
                   'fail to answer in time &rarr; hider\u2019s clock pauses until answered '
                   '&amp; they draw <b>no</b> card.</p>')

CARD_MATCHING = f"""
<div class="card">
  <h2>1 &middot; Matching <span class="dk">draw 3, keep 1</span></h2>
  <p class="prompt">"Is your nearest ___ the same as mine?" &rarr; <b>Yes / No</b></p>
  <p class="send"><b>Send hider:</b> your own nearest ___ (the matching subject).</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {boxes(MATCHING)}
</div>"""
CARD_MEASURING = f"""
<div class="card">
  <h2>2 &middot; Measuring <span class="dk">draw 3, keep 1</span></h2>
  <p class="prompt">"Compared to me, are you closer to or further from ___?" &rarr; <b>Closer / Further</b></p>
  <p class="send"><b>Send hider:</b> your own distance to ___ (the measured feature).</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {boxes(MEASURING)}
</div>"""
CARD_RADAR = f"""
<div class="card slim">
  <h2>3 &middot; Radar <span class="dk">draw 2, keep 1</span></h2>
  <p class="prompt">"Are you within ___ of me?" &rarr; <b>Yes / No</b> &middot; Yes = keep inside circle, No = keep outside. <b>Custom</b> radius allowed <b>once per game</b>.</p>
  <p class="send"><b>Send hider:</b> your location pin (circle center) + the radius.</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {scale(RADAR, custom=True)}
  <p class="app ok inline">app: radar + custom radius, eliminated-area shading</p>
</div>"""
CARD_THERMO = f"""
<div class="card slim">
  <h2>4 &middot; Thermometer <span class="dk">draw 2, keep 1</span></h2>
  <p class="prompt">"I've just traveled (at least) ___ &mdash; am I hotter or colder?" hotter = closer, colder = further; eliminates the colder half (perpendicular bisector).</p>
  <p class="send"><b>Send hider:</b> where you started and where you stopped.</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {scale(THERMO)}
  <p class="app ok inline">app: thermometer + boundary line &amp; shading</p>
</div>"""
CARD_TENTACLES = f"""
<div class="card slim">
  <h2>5 &middot; Tentacles <span class="dk">draw 4, keep 2</span></h2>
  <p class="prompt">"Of all the ___ within 1 mi of you, which are you closest to?" (Hider must also be within 1 mi of one.)</p>
  <p class="send"><b>Send hider:</b> &mdash; (question is about the hider).</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {boxes([(t, False) for t in TENTACLES])}
  <p class="app no inline">app: not implemented</p>
</div>"""
CARD_PHOTO = f"""
<div class="card">
  <h2>6 &middot; Photo <span class="dk">draw 1</span></h2>
  <p class="prompt">Hider sends a photo meeting the stated condition (no zoom / no obscuring). Reveals surroundings without coordinates.</p>
  <p class="send"><b>Send hider:</b> &mdash; (the hider sends the photo).</p>
  <p class="eg warn"><b>End game:</b> conditions marked <span class="egm">&dagger;</span> need the station / a specific venue &mdash; if the hider can\u2019t reach it, \u201cI cannot answer\u201d is valid and they <b>still draw a card</b>.</p>
  {META_FAIL_PHOTO}
  {photo_boxes(PHOTO)}
  <p class="app ok inline">app: logged only (no auto-eliminate, by design)</p>
</div>"""

alt_card = f"""
<div class="card tbl">
  <h2>Stations by altitude <span class="dk">{len(ST)} stations</span></h2>
  {alt_table}
</div>"""
nl_card = f"""
<div class="card tbl">
  <h2>Stations by name length <span class="dk">{len(ST)} stations</span></h2>
  {nl_table}
</div>"""

def rblock(title, count, body):
    return (f'<div class="rblock"><h3>{title} <span class="cnt">{count}</span></h3>'
            f'{body}</div>')

airports_html = ('<ul class="plain air">' + "".join(
    f'<li><span class="aname">{html.escape(a)}</span>'
    f'<span class="coord">{c}</span></li>' for a, c in AIRPORTS) + '</ul>')

ref_air = rblock("Commercial airports", 3, airports_html)
ref_counties = rblock("Counties (in play)", len(counties), ul(counties))
ref_zoos = rblock("Zoos", len(zoos), ul(zoos))
ref_theme = rblock("Amusement parks", len(theme), ul(theme))
ref_cities = rblock("Cities / municipalities", len(cities), ul(cities))
ref_water = rblock("Bodies of water", len(bodies), ul(bodies))

# page 1: questions in two columns (Q1-3 | Q4-6)
page1_cols = f"""
<div class="p1">
  <div class="col col1">{CARD_MATCHING}{CARD_MEASURING}{CARD_RADAR}</div>
  <div class="col col2">{CARD_THERMO}{CARD_TENTACLES}{CARD_PHOTO}</div>
</div>"""

# page 2: both station tables + reference lists (golf & mountains removed)
page2_ref = f"""
<div class="ref">{alt_card}{nl_card}{ref_air}{ref_counties}{ref_zoos}{ref_theme}{ref_cities}{ref_water}</div>"""


doc = f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
@page {{ size: letter; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ font-family: 'IBM Plex Sans', -apple-system, Helvetica, Arial, sans-serif; color:#1a1a1a; margin:0; }}
h1 {{ font-size:19px; margin:0 0 3px; }}
.sub {{ font-size:10px; color:#666; margin:0 0 6px; }}
/* page 1: two columns */
.p1 {{ display:flex; gap:12px; align-items:flex-start; }}
.col {{ display:flex; flex-direction:column; flex:1; }}
.card {{ break-inside:avoid; border:1px solid #e2e2e2; border-radius:6px; padding:7px 9px; margin:0 0 7px; background:#fafafa; width:100%; }}
.ref .card.tbl {{ background:#fff; }}
.card h2 {{ font-size:13.5px; margin:0 0 5px; color:#111; }}
.dk {{ float:right; font-size:9.5px; font-weight:600; background:#111; color:#fff; padding:1px 6px; border-radius:8px; }}
.prompt {{ font-size:10px; margin:2px 0; color:#222; }}
.send {{ font-size:9.5px; margin:2px 0; color:#0c4a6e; background:#e0f2fe; border-radius:4px; padding:2px 5px; }}
.eg {{ font-size:9.3px; margin:2px 0; padding:2px 5px; border-radius:4px; }}
.eg.ok {{ color:#166534; background:#f0fdf4; }}
.eg.warn {{ color:#9a3412; background:#fff7ed; }}
.meta {{ font-size:9px; margin:2px 0 3px; color:#555; }}
.egm {{ color:#c2410c; font-weight:700; }}
/* checkbox subject lists */
ul.chk {{ list-style:none; margin:4px 0 0; padding:0; columns:2; column-gap:10px; }}
ul.chk li {{ font-size:9.6px; margin:1.5px 0; break-inside:avoid; display:flex; align-items:flex-start; gap:4px; }}
.cb {{ display:inline-block; width:10px; height:10px; min-width:10px; border:1px solid #555; border-radius:2px; margin-top:1px; }}
/* photo conditions: full requirement under each title, single column */
ul.chk.photo {{ columns:1; }}
ul.chk.photo li {{ margin:2.5px 0; }}
.pt {{ display:block; font-size:9.6px; line-height:1.3; }}
.pd {{ color:#444; font-size:9px; font-weight:400; }}
/* radar/thermometer scale: checkbox above number */
.scale {{ display:flex; flex-wrap:wrap; gap:9px; margin:5px 0 2px; }}
.sc {{ display:flex; flex-direction:column; align-items:center; }}
.sc .num {{ font-size:11px; margin-top:3px; color:#222; }}
.sc.unit {{ justify-content:flex-end; font-size:9.5px; color:#777; align-self:flex-end; }}
.app {{ font-size:8.5px; padding:0 5px; border-radius:6px; margin-left:3px; }}
.app.ok {{ background:#dcfce7; color:#166534; }}
.app.no {{ background:#f1f1f1; color:#999; }}
.app.inline {{ display:inline-block; margin:5px 0 0; }}
.page-break {{ break-before:page; }}
/* station-profile tables */
table.dt {{ width:100%; border-collapse:collapse; margin-top:4px; font-size:9.5px; }}
table.dt th {{ text-align:left; background:#f0f0f0; border-bottom:1px solid #bbb; padding:3px 6px; font-size:9px; }}
table.dt td {{ padding:2px 6px; border-bottom:1px solid #eee; }}
table.dt td:nth-child(2n) {{ text-align:right; font-variant-numeric:tabular-nums; }}
/* reference lists */
.ref {{ column-count:2; column-gap:16px; }}
.rblock {{ break-inside:auto; margin-bottom:9px; }}
.rblock h3 {{ font-size:12px; margin:0 0 4px; color:#111; border-bottom:1px solid #ddd; padding-bottom:2px; break-after:avoid; }}
.card.tbl {{ break-inside:avoid; }}
.cnt {{ float:right; font-size:9px; color:#fff; background:#c2410c; padding:0 6px; border-radius:8px; }}
ul.cols {{ columns:2; column-gap:10px; margin:0; padding-left:15px; }}
ul.cols li {{ font-size:9px; margin:1px 0; break-inside:avoid; }}
ul.plain {{ list-style:none; margin:0; padding:0; }}
ul.plain li {{ font-size:10px; margin:0 0 4px; }}
/* airports: name left, coords on the right, wrapping below if tight */
ul.plain.air li {{ display:flex; flex-wrap:wrap; justify-content:space-between; gap:2px 8px; align-items:baseline; }}
.aname {{ font-weight:700; font-size:10px; }}
.coord {{ font-size:9px; color:#555; font-family:'IBM Plex Mono', monospace; }}
footer {{ font-size:8px; color:#888; margin-top:8px; }}
</style></head><body>
<h1>Jet Lag: Hide &amp; Seek &mdash; Question Deck (Medium)</h1>
<p class="sub">Seeker asks; hider answers truthfully &amp; then draws/keeps cards. <b>Send hider</b> = the minimum you must reveal for the question to be answerable. <span class="egm">&dagger;</span> = may be impossible in the end game. "app" = the Bay Area seeker tool auto-eliminates for it.</p>
{page1_cols}
<div class="page-break"></div>
<h1>Bay Area play-area reference (continued)</h1>
<p class="sub">In-play counties: {", ".join(counties)}. POI lists from OpenStreetMap within those counties.</p>
{page2_ref}
<footer>Question subjects, draw/keep, answer windows &amp; end-game rules from the official Jet Lag: Hide &amp; Seek Investigation Book + Quick Start guide. Bodies of water limited to bays/straits, lakes, lagoons &amp; named reservoirs (minor coves/sloughs/ponds omitted). POIs from OpenStreetMap.</footer>
</body></html>"""

open("/tmp/reference.html", "w").write(doc)
print("counts: cities", len(cities), "water", len(bodies), "mountains", len(mountains),
      "golf", len(golf), "theme", len(theme), "hospital", len(hospital))

OUT = os.path.join(REPO, "jetlag_reference_medium.pdf")
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://localhost:29229")
    ctx = b.contexts[0] if b.contexts else b.new_context()
    pg = ctx.new_page()
    pg.goto("file:///tmp/reference.html", wait_until="networkidle")
    pg.evaluate("document.fonts.ready")  # ensure IBM Plex Sans is loaded
    pg.emulate_media(media="print")
    pg.pdf(path=OUT, format="Letter", print_background=True,
           margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"})
    pg.close()
print("wrote", OUT, os.path.getsize(OUT), "bytes")
