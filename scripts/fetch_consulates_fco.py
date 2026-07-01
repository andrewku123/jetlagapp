"""Authoritative consulate list -> auth_lists/consulate.csv.

Source: the U.S. Government Congressional Directory "Foreign Diplomatic Offices in
the United States" (published on govinfo.gov), which lists, per country, the
cities where it maintains consular offices. We extract the consular cities that
fall in the play area's metro and emit one candidate per (country, city):
    Consulate General of <Country>, <City>, <STATE>
`authoritative_candidates.py` then gap-filters these and the icon-check geocodes
them via Google searchText + the in_play polygon test (consulates type=embassy).

The PDF is two-column; we crop each page into halves so the country blocks read
in order. Per-city input for a new metro: METRO_CITIES + STATE (+ a current PDF).
Requires: pdfplumber.
"""
import os, re, csv, urllib.request
import pdfplumber

HERE = os.path.dirname(os.path.abspath(__file__))
PDF_URL = ("https://www.govinfo.gov/content/pkg/CDIR-2022-10-26/pdf/"
           "CDIR-2022-10-26-DIPLOMATICOFFICES.pdf")
STATE = "California"                       # play-area state (full name as in PDF)
STATE_ABBR = "CA"
METRO_CITIES = {                          # Bay Area cities considered in-metro
    "san francisco", "san jose", "palo alto", "sunnyvale", "mountain view",
    "oakland", "berkeley", "santa clara", "san mateo", "burlingame",
    "foster city", "menlo park", "fremont", "milpitas", "redwood city",
    "cupertino", "los altos", "san rafael", "walnut creek", "hayward",
    "south san francisco", "emeryville", "san bruno"}
US_STATES = {  # state names that head a consular-office list in the directory
    "california", "alaska", "arizona", "colorado", "florida", "georgia", "guam",
    "hawaii", "illinois", "massachusetts", "michigan", "new york", "oregon",
    "texas", "washington", "louisiana", "district of columbia", "nevada",
    "puerto rico", "minnesota", "ohio", "pennsylvania", "missouri", "utah",
    "north carolina", "tennessee", "new mexico", "kentucky",
    "northern mariana islands", "american samoa", "virgin islands"}
STOP = ("Embassy", "Ambassador", "His Excellency", "Her Excellency", "Mr.", "Ms.",
        "Mrs.", "Charge", "Counselor", "Delegation", "Minister", "phone", "fax")


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
    pdf_path = os.path.join(HERE, "consular_directory.pdf")
    if not os.path.exists(pdf_path):
        print("downloading", PDF_URL)
        req = urllib.request.Request(PDF_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as r, open(pdf_path, "wb") as f:
            f.write(r.read())

    rows, country, collecting, state = [], None, False, None
    for l in (ln.strip() for ln in col_text(pdf_path).splitlines()):
        if not l:
            continue
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
        if state.lower() == STATE.lower() and city.lower() in METRO_CITIES and country:
            rows.append((country, city))

    seen, final = set(), []
    for c, city in rows:
        if (c, city) not in seen:
            seen.add((c, city)); final.append((c, city))

    os.makedirs(os.path.join(HERE, "auth_lists"), exist_ok=True)
    out = os.path.join(HERE, "auth_lists", "consulate.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "name", "city", "state"])
        for c, city in final:
            w.writerow(["consulate", f"Consulate General of {c}", city, STATE_ABBR])
    print(f"wrote {out}: {len(final)} consular offices in the metro")


if __name__ == "__main__":
    main()
