"""Build benches/data/park.json from OpenStreetMap.

Fetches the Van Cortlandt Park boundary and its footpaths from the Overpass API, keeps
path pieces inside the boundary, and groups them into named areas by nearest landmark.
The seed command places synthetic benches along these paths.

    python scripts/build_park_data.py

Map data © OpenStreetMap contributors, ODbL.
"""

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "benches" / "data" / "park.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = """[out:json][timeout:90];
way["leisure"="park"]["name"="Van Cortlandt Park"]->.park;
.park map_to_area->.a;
(.park; way(area.a)["highway"~"^(footway|path|track|cycleway|pedestrian|bridleway)$"];);
out geom;"""

# Areas are named for landmarks; each path piece goes to the nearest one.
# Positions are OSM centers of the landmark (lat, lon).
AREAS = {
    "Parade Ground": (40.8872, -73.8948),
    "Van Cortlandt House": (40.8911, -73.8945),
    "Van Cortlandt Lake": (40.8925, -73.8905),
    "Vault Hill": (40.8960, -73.8923),
    "Van Cortlandt Golf Course": (40.8982, -73.8876),
    "Northwest Forest": (40.9045, -73.8935),
    "Old Croton Aqueduct": (40.9011, -73.8829),
    "Indian Field": (40.8965, -73.8780),
    "Northeast Forest": (40.9065, -73.8790),
    "Jerome Avenue Fields": (40.9005, -73.8715),
    "Sachkerah Woods": (40.8845, -73.8810),
    "Mosholu Parkway": (40.8900, -73.8860),
}


def fetch():
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(OVERPASS, data=body, headers={"User-Agent": "vc-bench-seed/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["elements"]


def in_ring(lat, lon, ring):
    inside = False
    for (y1, x1), (y2, x2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def dist(a, b):
    # Equirectangular meters; plenty accurate at park scale.
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def nearest_area(p):
    return min(AREAS, key=lambda name: dist(p, AREAS[name]))


def main():
    elements = fetch()
    park = next(e for e in elements if e.get("tags", {}).get("leisure") == "park")
    boundary = [(round(g["lat"], 6), round(g["lon"], 6)) for g in park["geometry"]]

    paths = []  # {"area", "name", "points"}
    for way in elements:
        if way is park or "highway" not in way.get("tags", {}):
            continue
        name = way["tags"].get("name", "")
        pts = [(g["lat"], g["lon"]) for g in way["geometry"]]
        # Split the way wherever it leaves the park or crosses into another area.
        current, current_area = [], None
        for a, b in zip(pts, pts[1:]):
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            inside = in_ring(*a, boundary) and in_ring(*b, boundary)
            area = nearest_area(mid) if inside else None
            if area != current_area and current:
                if current_area:
                    paths.append({"area": current_area, "name": name, "points": current})
                current = []
            current_area = area
            if area:
                current = current or [a]
                current.append(b)
        if current and current_area:
            paths.append({"area": current_area, "name": name, "points": current})

    for p in paths:
        p["points"] = [[round(lat, 6), round(lon, 6)] for lat, lon in p["points"]]

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "attribution": "Map data © OpenStreetMap contributors, ODbL",
        "boundary": boundary,
        "paths": paths,
    }, separators=(",", ":")))
    lengths = {}
    for p in paths:
        lengths[p["area"]] = lengths.get(p["area"], 0) + sum(dist(a, b) for a, b in zip(p["points"], p["points"][1:]))
    for area, m in sorted(lengths.items(), key=lambda kv: -kv[1]):
        print(f"{area:28s} {m / 1000:6.1f} km")
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(paths)} path pieces)")


if __name__ == "__main__":
    main()
