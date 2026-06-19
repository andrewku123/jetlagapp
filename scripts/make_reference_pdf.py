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
golf, theme, hospital = set(), set(), set()
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

AIRPORTS = [
    ("SFO \u2014 San Francisco Intl", "37.619083, -122.381597"),
    ("OAK \u2014 SF Bay Oakland Intl", "37.719016, -122.219595"),
    ("SJC \u2014 San Jose Mineta Intl", "37.363510, -121.928648"),
]

# ---------- SVG histograms ----------
def svg_vertical(counts, labels, w=520, h=230, pad_l=28, pad_b=46, pad_t=14):
    n = len(counts); mx = max(counts) or 1
    plot_w = w - pad_l - 8; plot_h = h - pad_b - pad_t
    bw = plot_w / n
    bars = []
    for i, c in enumerate(counts):
        bh = plot_h * c / mx
        x = pad_l + i * bw + bw * 0.12
        y = pad_t + (plot_h - bh)
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.76:.1f}" height="{bh:.1f}" fill="#c2410c"/>')
        if c:
            bars.append(f'<text x="{x+bw*0.38:.1f}" y="{y-2:.1f}" font-size="8" text-anchor="middle" fill="#444">{c}</text>')
        bars.append(f'<text x="{x+bw*0.38:.1f}" y="{h-pad_b+12:.1f}" font-size="7.5" text-anchor="end" fill="#555" transform="rotate(-45 {x+bw*0.38:.1f} {h-pad_b+12:.1f})">{labels[i]}</text>')
    axis = (f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+plot_h:.1f}" stroke="#999"/>'
            f'<line x1="{pad_l}" y1="{pad_t+plot_h:.1f}" x2="{w-8}" y2="{pad_t+plot_h:.1f}" stroke="#999"/>')
    cap = f'<text x="{w/2:.0f}" y="{h-6}" font-size="9" text-anchor="middle" fill="#333">elevation (ft above sea level)</text>'
    return f'<svg viewBox="0 0 {w} {h}" width="100%" >{axis}{"".join(bars)}{cap}</svg>'

def svg_horizontal(rows, w=520, rh=11, pad_l=24, pad_r=26, pad_t=6):
    mx = max(c for _, c in rows) or 1
    h = pad_t * 2 + rh * len(rows) + 14
    plot_w = w - pad_l - pad_r
    out = []
    for i, (L, c) in enumerate(rows):
        y = pad_t + i * rh
        bw = plot_w * c / mx
        out.append(f'<text x="{pad_l-3}" y="{y+rh-2:.1f}" font-size="8" text-anchor="end" fill="#555">{L}</text>')
        out.append(f'<rect x="{pad_l}" y="{y+1:.1f}" width="{bw:.1f}" height="{rh-3:.1f}" fill="#2563eb"/>')
        if c:
            out.append(f'<text x="{pad_l+bw+3:.1f}" y="{y+rh-2:.1f}" font-size="7.5" fill="#444">{c}</text>')
    out.append(f'<text x="{pad_l+plot_w/2:.0f}" y="{h-2}" font-size="9" text-anchor="middle" fill="#333">station-name length (characters)</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%">{"".join(out)}</svg>'

alt_svg = svg_vertical(alt_counts, alt_labels)
nl_svg = svg_horizontal(nl_rows)

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
    ("Sea level (altitude)", True), ("A body of water", False),
    ("A coastline", False), ("A mountain", False), ("A park", False),
    ("An amusement park", False), ("A zoo", False), ("An aquarium", False),
    ("A golf course", False), ("A museum", False), ("A movie theater", False),
    ("A hospital", False), ("A library", False), ("A foreign consulate", False),
]
RADAR = ["\u00bc", "\u00bd", "1", "3", "5", "10", "25", "50", "100"]
THERMO = ["\u00bd", "3", "10"]
TENTACLES = ["Museums", "Libraries", "Movie theaters", "Hospitals"]
# photo: (label, endgame_blocked?) for Medium = All-Games + Medium/Large set
PHOTO = [
    ("A tree", False), ("The sky", False), ("You", False),
    ("The widest street", False), ("The tallest structure in your sightline", False),
    ("Any building visible from your station", True),
    ("The tallest building visible from your station", True),
    ("Trace the nearest street / path", False), ("Two buildings", False),
    ("A restaurant interior", True), ("A train platform", True),
    ("A park", True), ("A grocery store aisle", True), ("A place of worship", True),
]

def boxes(items):
    out = []
    for label, app in items:
        badge = ' <span class="app ok">app</span>' if app else ''
        out.append(f'<li><span class="cb"></span>{html.escape(label)}{badge}</li>')
    return "<ul class=\"chk\">" + "".join(out) + "</ul>"

def photo_boxes(items):
    out = []
    for label, eg in items:
        mark = ' <span class="egm">&dagger;</span>' if eg else ''
        out.append(f'<li><span class="cb"></span>{html.escape(label)}{mark}</li>')
    return "<ul class=\"chk\">" + "".join(out) + "</ul>"

def scale(items, unit="mi"):
    cells = "".join(
        f'<div class="sc"><span class="cb"></span><span class="num">{v}</span></div>'
        for v in items)
    return f'<div class="scale">{cells}<div class="sc unit">{unit}</div></div>'

# per-card meta lines
META_FAIL = ('<p class="meta"><b>Answer window</b> &le; 5 min &middot; '
             'fail to answer in time &rarr; hider\u2019s clock pauses until answered '
             '&amp; they draw <b>no</b> card.</p>')
META_FAIL_PHOTO = ('<p class="meta"><b>Answer window</b> &le; 10 min (Medium) &middot; '
                   'fail to answer in time &rarr; hider\u2019s clock pauses until answered '
                   '&amp; they draw <b>no</b> card.</p>')

deck_cards = f"""
<div class="card">
  <h2>1 &middot; Matching <span class="dk">draw 3, keep 1</span></h2>
  <p class="prompt">"Is your nearest ___ the same as mine?" &rarr; <b>Yes / No</b></p>
  <p class="send"><b>Send hider:</b> your own nearest ___ (the matching subject).</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {boxes(MATCHING)}
</div>
<div class="card">
  <h2>2 &middot; Measuring <span class="dk">draw 3, keep 1</span></h2>
  <p class="prompt">"Compared to me, are you closer to or further from ___?" &rarr; <b>Closer / Further</b></p>
  <p class="send"><b>Send hider:</b> your own distance to ___ (the measured feature).</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {boxes(MEASURING)}
</div>
<div class="card slim">
  <h2>3 &middot; Radar <span class="dk">draw 2, keep 1</span></h2>
  <p class="prompt">"Are you within ___ of me?" &rarr; <b>Yes / No</b> &middot; Yes = keep inside circle, No = keep outside. <b>Custom</b> radius allowed.</p>
  <p class="send"><b>Send hider:</b> your location pin (circle center) + the radius.</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {scale(RADAR)}
  <p class="app ok inline">app: radar + custom radius, eliminated-area shading</p>
</div>
<div class="card slim">
  <h2>4 &middot; Thermometer <span class="dk">draw 2, keep 1</span></h2>
  <p class="prompt">"I've just traveled (at least) ___ &mdash; am I hotter or colder?" hotter = closer, colder = further; eliminates the colder half (perpendicular bisector).</p>
  <p class="send"><b>Send hider:</b> where you started and where you stopped.</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {scale(THERMO)}
  <p class="app ok inline">app: thermometer + boundary line &amp; shading</p>
</div>
<div class="card slim">
  <h2>5 &middot; Tentacles <span class="dk">draw 4, keep 2</span></h2>
  <p class="prompt">"Of all the ___ within 1 mi of you, which are you closest to?" (Hider must also be within 1 mi of one.)</p>
  <p class="send"><b>Send hider:</b> &mdash; (question is about the hider).</p>
  <p class="eg ok"><b>End game:</b> completable.</p>
  {META_FAIL}
  {boxes([(t, False) for t in TENTACLES])}
  <p class="app no inline">app: not implemented</p>
</div>
<div class="card">
  <h2>6 &middot; Photo <span class="dk">draw 1</span></h2>
  <p class="prompt">Hider sends a photo of the subject (no zoom / no obscuring). Reveals surroundings without coordinates.</p>
  <p class="send"><b>Send hider:</b> &mdash; (the hider sends the photo).</p>
  <p class="eg warn"><b>End game:</b> subjects marked <span class="egm">&dagger;</span> need the station / a specific venue &mdash; if the hider can\u2019t reach it, \u201cI cannot answer\u201d is valid and they <b>still draw a card</b>.</p>
  {META_FAIL_PHOTO}
  {photo_boxes(PHOTO)}
  <p class="app ok inline">app: logged only (no auto-eliminate, by design)</p>
</div>
"""

back = f"""
<div class="ref">
  <div class="rblock"><h3>Commercial airports <span class="cnt">3</span></h3>
    <ul class="plain">{"".join(f"<li><b>{html.escape(a)}</b><br><span class=coord>{c}</span></li>" for a,c in AIRPORTS)}</ul></div>
  <div class="rblock"><h3>Counties (in play) <span class="cnt">{len(counties)}</span></h3>{ul(counties)}</div>
  <div class="rblock"><h3>Cities / municipalities <span class="cnt">{len(cities)}</span></h3>{ul(cities)}</div>
  <div class="rblock"><h3>Amusement parks <span class="cnt">{len(theme)}</span></h3>{ul(theme)}</div>
  <div class="rblock"><h3>Bodies of water <span class="cnt">{len(bodies)}</span></h3>{ul(bodies)}</div>
  <div class="rblock"><h3>Mountains &middot; named peaks &ge; 1,500 ft <span class="cnt">{len(mountains)}</span></h3>{ul(mountains)}</div>
  <div class="rblock"><h3>Golf courses <span class="cnt">{len(golf)}</span></h3>{ul(golf)}</div>
  <div class="rblock"><h3>Hospitals <span class="cnt">{len(hospital)}</span></h3>{ul(hospital)}</div>
</div>
<div class="charts">
  <div class="chart"><h3>Stations by altitude</h3>{alt_svg}</div>
  <div class="chart"><h3>Stations by name length</h3>{nl_svg}</div>
</div>
"""


doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: letter; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; color:#1a1a1a; margin:0; }}
h1 {{ font-size:17px; margin:0 0 2px; }}
.sub {{ font-size:9.5px; color:#666; margin:0 0 8px; }}
.deck {{ column-count:3; column-gap:12px; }}
.card {{ break-inside:avoid; border:1px solid #e2e2e2; border-radius:6px; padding:7px 9px; margin:0 0 9px; background:#fafafa; display:inline-block; width:100%; }}
.card h2 {{ font-size:11.5px; margin:0 0 4px; color:#111; }}
.dk {{ float:right; font-size:8px; font-weight:600; background:#111; color:#fff; padding:1px 5px; border-radius:8px; }}
.prompt {{ font-size:8.7px; margin:2px 0 3px; color:#222; }}
.send {{ font-size:8.2px; margin:2px 0; color:#0c4a6e; background:#e0f2fe; border-radius:4px; padding:2px 4px; }}
.eg {{ font-size:8px; margin:2px 0; padding:2px 4px; border-radius:4px; }}
.eg.ok {{ color:#166534; background:#f0fdf4; }}
.eg.warn {{ color:#9a3412; background:#fff7ed; }}
.meta {{ font-size:7.8px; margin:2px 0 4px; color:#555; }}
.egm {{ color:#c2410c; font-weight:700; }}
/* checkbox subject lists */
ul.chk {{ list-style:none; margin:3px 0 0; padding:0; columns:2; column-gap:8px; }}
ul.chk li {{ font-size:8.2px; margin:1.5px 0; break-inside:avoid; display:flex; align-items:flex-start; gap:3px; }}
.card.slim ul.chk {{ columns:1; }}
.cb {{ display:inline-block; width:8px; height:8px; min-width:8px; border:1px solid #555; border-radius:1.5px; margin-top:1px; }}
/* radar/thermometer scale: checkbox above number */
.scale {{ display:flex; flex-wrap:wrap; gap:6px; margin:4px 0 2px; }}
.sc {{ display:flex; flex-direction:column; align-items:center; }}
.sc .num {{ font-size:9px; margin-top:2px; color:#222; }}
.sc.unit {{ justify-content:flex-end; font-size:8px; color:#777; align-self:flex-end; }}
.app {{ font-size:7px; padding:0 4px; border-radius:6px; margin-left:3px; }}
.app.ok {{ background:#dcfce7; color:#166534; }}
.app.no {{ background:#f1f1f1; color:#999; }}
.app.inline {{ display:inline-block; margin:4px 0 0; }}
.page-break {{ break-before:page; }}
.ref {{ column-count:3; column-gap:12px; }}
.rblock {{ break-inside:avoid; margin-bottom:9px; }}
.rblock h3, .chart h3 {{ font-size:10px; margin:0 0 3px; color:#111; border-bottom:1px solid #ddd; padding-bottom:2px; }}
.cnt {{ float:right; font-size:8px; color:#fff; background:#c2410c; padding:0 5px; border-radius:8px; }}
ul.cols {{ columns:2; column-gap:8px; margin:0; padding-left:13px; }}
ul.cols li {{ font-size:7.6px; margin:0.5px 0; break-inside:avoid; }}
ul.plain {{ list-style:none; margin:0; padding:0; }}
ul.plain li {{ font-size:8.5px; margin:0 0 3px; }}
.coord {{ font-size:7.5px; color:#666; font-family:monospace; }}
.charts {{ display:flex; gap:14px; margin-top:6px; break-inside:avoid; }}
.chart {{ flex:1; border:1px solid #eee; border-radius:6px; padding:6px 8px; }}
footer {{ font-size:7px; color:#888; margin-top:6px; }}
</style></head><body>
<h1>Jet Lag: Hide &amp; Seek &mdash; Question Deck (Medium)</h1>
<p class="sub">Seeker asks; hider answers truthfully &amp; then draws/keeps cards. <b>Send hider</b> = the minimum you must reveal for the question to be answerable. <span class="egm">&dagger;</span> = may be impossible in the end game. "app" = the Bay Area seeker tool auto-eliminates for it.</p>
<div class="deck">{deck_cards}</div>
<div class="page-break"></div>
<h1>Bay Area play-area reference</h1>
<p class="sub">In-play counties: {", ".join(counties)}. POI lists from OpenStreetMap within those counties; histograms from the app's {len(ST)} stations.</p>
{back}
<footer>Question subjects, draw/keep, answer windows &amp; end-game rules from the official Jet Lag: Hide &amp; Seek Investigation Book + Quick Start guide. Mountains limited to named summits &ge; 1,500 ft; bodies of water limited to bays/straits, lakes, lagoons &amp; named reservoirs (minor coves/sloughs/ponds omitted). POIs from OpenStreetMap.</footer>
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
    pg.emulate_media(media="print")
    pg.pdf(path=OUT, format="Letter", print_background=True,
           margin={"top": "0.4in", "bottom": "0.4in", "left": "0.4in", "right": "0.4in"})
    pg.close()
print("wrote", OUT, os.path.getsize(OUT), "bytes")
