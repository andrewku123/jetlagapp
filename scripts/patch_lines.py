"""Add canonical BART line membership to the enriched station file.

BART GTFS route long-names are per-direction; collapse them to the six BART
color lines so the 'transit line' matching question is sensible.
"""
import json

ENRICHED = '/home/ubuntu/repos/bayarea-hideandseek/src/data/stations.json'
BART_LINES = 'bart_lines.json'


def canon(name: str) -> str:
    n = name.replace('BART ', '')
    has = lambda *t: all(x in n for x in t)
    if has('Berryessa', 'Daly City'):
        return 'BART Green (Berryessa–Daly City)'
    if has('Berryessa', 'Richmond'):
        return 'BART Orange (Berryessa–Richmond)'
    if has('Dublin'):
        return 'BART Blue (Dublin/Pleasanton–Daly City)'
    if has('Antioch') and ('Millbrae' in n or 'SFO' in n):
        return 'BART Yellow (Antioch–SFO/Millbrae)'
    if has('Richmond') and ('Millbrae' in n or 'SFO' in n):
        return 'BART Red (Richmond–Millbrae/SFO)'
    if 'OAK' in n or 'Oakland Int' in n:
        return 'BART Beige (Coliseum–OAK)'
    return 'BART ' + n


def main():
    st = json.load(open(ENRICHED))
    bl = json.load(open(BART_LINES))
    # map by station name
    by_name = {s['name']: s for s in st}
    for name, lines in bl.items():
        s = by_name.get(name)
        if not s:
            continue
        canon_lines = sorted({canon(l) for l in lines})
        merged = sorted(set(s.get('lines', [])) | set(canon_lines))
        s['lines'] = merged
    json.dump(st, open(ENRICHED, 'w'), indent=1)
    print('patched BART lines into', ENRICHED)
    # quick check
    for s in st:
        if 'BART' in s['systems']:
            print(s['name'], '->', s['lines'])
            break


if __name__ == '__main__':
    main()
