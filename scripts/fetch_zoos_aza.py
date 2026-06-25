"""Authoritative zoos + aquariums -> auth_lists/zoo_aquarium.csv.

Source: AZA (Association of Zoos & Aquariums) current accreditation list — the
authoritative roster of accredited US zoos/aquariums. Each entry is an institution
name + city. We keep those in the play-area metro and split zoo vs aquarium by
name. `authoritative_candidates.py` gap-filters; the icon-check geocodes via
Google searchText + the in_play polygon test (types zoo / aquarium).

Per-metro input: METRO_CITIES. Requires network access to aza.org.
"""
import os, re, csv, html, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.aza.org/current-accreditation-list"
METRO_CITIES = {
    "san francisco", "san jose", "palo alto", "sunnyvale", "mountain view",
    "oakland", "berkeley", "santa clara", "san mateo", "burlingame",
    "foster city", "menlo park", "fremont", "milpitas", "redwood city",
    "cupertino", "los altos", "san rafael", "walnut creek", "hayward",
    "south san francisco", "emeryville", "san bruno", "vallejo", "richmond"}


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = html.unescape(r.read().decode("utf-8", "replace"))
    lines = [x.strip().replace("\xa0", " ").strip()
             for x in re.sub(r"<[^>]+>", "\n", raw).splitlines()]
    lines = [x for x in lines if x]

    rows = []
    for i, l in enumerate(lines[:-1]):
        if not l.endswith(","):                 # institution names end with a comma
            continue
        name = l.rstrip(",").strip()
        city = lines[i + 1].strip()
        # the line after the city should confirm an accreditation entry
        nxt = lines[i + 2] if i + 2 < len(lines) else ""
        if "Accredited" not in nxt:
            continue
        if city.lower() not in METRO_CITIES:
            continue
        cat = "aquarium" if "aquarium" in name.lower() else "zoo"
        rows.append((cat, name, city))

    seen, final = set(), []
    for r_ in rows:
        if r_ not in seen:
            seen.add(r_); final.append(r_)

    os.makedirs(os.path.join(HERE, "auth_lists"), exist_ok=True)
    out = os.path.join(HERE, "auth_lists", "zoo_aquarium.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "name", "city", "state"])
        for cat, name, city in final:
            w.writerow([cat, name, city, "CA"])
    print(f"wrote {out}: {len(final)} AZA institutions in the metro")
    for cat, name, city in final:
        print(f"  {cat:8s} {name} ({city})")


if __name__ == "__main__":
    main()
