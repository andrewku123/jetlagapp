"""Authoritative diplomatic-post list -> auth_lists/consulate.csv.

Source: the U.S. Government Congressional Directory "Foreign Diplomatic Offices in
the United States" (published on govinfo.gov). Two kinds of post are listed per
country and both count as the game's `consulate` category (Google icon `embassy`):
  * the **embassy** itself — always in Washington, DC, so it only matters for a
    play area that contains the capital;
  * the **consular offices**, listed as `<State>, <City>` lines.
We emit one candidate per post in the play area; `authoritative_candidates.py`
gap-filters them and the icon-check geocodes each via Google searchText + the
in_play polygon test.

City-agnostic: the in-metro test is the region's own Census places file
(`places` in poi_geo.REGIONS) and its states, so a new city needs no edits —
never a hand-typed city list, which silently under-covers a metro.

The PDF is two-column; we crop each page into halves so the country blocks read
in order. Requires: pdfplumber.

    python3 fetch_consulates_fco.py --region dc
"""
import os, re, csv, json, urllib.request
import pdfplumber

import poi_geo

HERE = os.path.dirname(os.path.abspath(__file__))
PDF_URL = ("https://www.govinfo.gov/content/pkg/CDIR-2022-10-26/pdf/"
           "CDIR-2022-10-26-DIPLOMATICOFFICES.pdf")
REGION = poi_geo.region_from_argv()

# The directory heads each consular list with a state name, so we need the play
# area's states; the abbreviation is only cosmetic (it lands in the CSV).
STATE_ABBR = {
    "district of columbia": "DC", "maryland": "MD", "virginia": "VA",
    "california": "CA", "new york": "NY", "illinois": "IL", "texas": "TX",
    "florida": "FL", "massachusetts": "MA", "washington": "WA", "oregon": "OR",
    "georgia": "GA", "pennsylvania": "PA", "michigan": "MI", "ohio": "OH",
    "colorado": "CO", "arizona": "AZ", "nevada": "NV", "hawaii": "HI",
    "alaska": "AK", "louisiana": "LA", "minnesota": "MN", "missouri": "MO",
    "utah": "UT", "north carolina": "NC", "tennessee": "TN", "new mexico": "NM",
    "kentucky": "KY", "puerto rico": "PR", "guam": "GU",
}
US_STATES = set(STATE_ABBR)                  # state names that head a consular list
STOP = ("Embassy", "Ambassador", "His Excellency", "Her Excellency", "Mr.", "Ms.",
        "Mrs.", "Charge", "Counselor", "Delegation", "Minister", "phone", "fax")
LSAD = re.compile(r"\s+(city|town|village|borough|CDP|municipality)$", re.I)


def metro(region):
    """(city names in the play area, state names it spans) — both lowercased."""
    places = json.load(open(poi_geo.repo_path(region, "places")))
    cities = {LSAD.sub("", f["properties"]["name"]).strip().lower()
              for f in places["features"]}
    states = {name.lower() for _, name in poi_geo.REGIONS[region].get(
        "states", [])} or US_STATES
    return cities, states


def col_text(pdf_path):
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            for x0, x1 in [(0, p.width / 2), (p.width / 2, p.width)]:
                out.append(p.crop((x0, 0, x1, p.height)).extract_text() or "")
    return "\n".join(out)


def is_country(l):
    return bool(re.fullmatch(r"[A-Z][A-Z .,'’()\-]{2,}", l)) and l not in ("NW", "US")


def main():
    cities, states = metro(REGION)
    # The embassies all sit in Washington, DC, so they are only in play for a
    # capital-region map.
    want_embassies = "washington" in cities and "district of columbia" in states

    pdf_path = os.path.join(HERE, "consular_directory.pdf")
    if not os.path.exists(pdf_path):
        print("downloading", PDF_URL)
        req = urllib.request.Request(PDF_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as r, open(pdf_path, "wb") as f:
            f.write(r.read())

    rows, country, collecting, state, embassy_done = [], None, False, None, set()
    for l in (ln.strip() for ln in col_text(pdf_path).splitlines()):
        if not l:
            continue
        if want_embassies and country and country not in embassy_done and \
                re.match(r"Embassy of ", l):
            # Name it from the country heading, not the line: the PDF wraps long
            # official names ("Embassy of the Democratic and Popular Republic" /
            # "of Algeria") and a truncated name geocodes to nothing.
            embassy_done.add(country)
            rows.append((f"Embassy of {country}", "Washington", "DC"))
        if l.startswith("Consular Offices"):
            collecting, state = True, None
            continue
        if is_country(l):
            country, collecting = l.title(), False
            continue
        if not collecting:
            continue
        if any(l.startswith(s) for s in STOP):
            collecting = False
            continue
        if re.search(r"\d|VerDate|Jkt|Frm|Fmt|BOJ|PO 0", l):     # page-break junk
            continue
        m = re.fullmatch(r"([A-Za-z .]+),\s*([A-Za-z .'\-]+)", l)
        if m and m.group(1).strip().lower() in US_STATES:
            state, city = m.group(1).strip(), m.group(2).strip()
        elif l.endswith(":") and l[:-1].strip().lower() in US_STATES:
            state = l[:-1].strip()
            continue
        elif re.fullmatch(r"[A-Za-z .'\-]+", l) and state:
            city = l
        else:
            continue
        if state.lower() in states and city.lower() in cities and country:
            rows.append((f"Consulate General of {country}", city,
                         STATE_ABBR.get(state.lower(), state)))

    seen, final = set(), []
    for r in rows:
        if r not in seen:
            seen.add(r); final.append(r)

    os.makedirs(os.path.join(HERE, "auth_lists"), exist_ok=True)
    out = os.path.join(HERE, "auth_lists", "consulate.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "name", "city", "state"])
        for name, city, st in final:
            w.writerow(["consulate", name, city, st])
    print(f"wrote {out}: {len(final)} diplomatic posts in the {REGION} play area "
          f"({sum(1 for n, *_ in final if n.startswith('Embassy'))} embassies)")


if __name__ == "__main__":
    main()
