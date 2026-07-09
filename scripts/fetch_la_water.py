#!/usr/bin/env python3
"""Fetch OSM water for the LA play area (rivers/canals as lines, lakes/reservoirs/
riverbanks as polygons, and the coastline) into a raw dump for build_la_water.py."""
import json
import time
import urllib.request

# padded past the play-area bbox to catch the coast (SW) and river mouths
S, W, N, E = 33.60, -118.78, 34.42, -117.62
Q = f"""
[out:json][timeout:180];
(
  way["waterway"~"^(river|canal)$"]({S},{W},{N},{E});
  way["natural"="water"]({S},{W},{N},{E});
  relation["natural"="water"]({S},{W},{N},{E});
  way["waterway"="riverbank"]({S},{W},{N},{E});
  way["natural"="coastline"]({S},{W},{N},{E});
);
out geom;
"""
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
for i, ep in enumerate(ENDPOINTS):
    try:
        print("trying", ep)
        req = urllib.request.Request(ep, data=("data=" + Q).encode(), headers={"User-Agent": "jetlag-la-water/1.0"})
        raw = urllib.request.urlopen(req, timeout=200).read()
        data = json.loads(raw)
        print("elements:", len(data.get("elements", [])))
        json.dump(data, open("/home/ubuntu/_la_water_raw.json", "w"))
        print("saved /home/ubuntu/_la_water_raw.json")
        break
    except Exception as e:
        print("failed:", e)
        time.sleep(5 * (i + 1))
