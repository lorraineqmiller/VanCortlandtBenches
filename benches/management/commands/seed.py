"""Seed synthetic benches and adoptions.

Benches are placed along real Van Cortlandt Park footpaths from OpenStreetMap
(benches/data/park.json, built by scripts/build_park_data.py), always inside the park
boundary, so the map looks plausible. Bench positions, names, and records are made up.
"""

import datetime
import json
import math
import random
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from benches.models import Adoption, Bench, Donor
from benches.services import add_years, today

PARK_DATA = Path(__file__).resolve().parents[2] / "data" / "park.json"
BENCH_COUNT = 520

FIRST = ["Maria", "James", "Aisha", "Wei", "Carmen", "David", "Priya", "Luis", "Grace", "Samuel", "Nadia", "Kevin",
         "Rosa", "Omar", "Helen", "Tomás", "Yuki", "Frank", "Esther", "Andre", "Leah", "Victor", "Joan", "Malik"]
LAST = ["Rivera", "O'Connor", "Johnson", "Chen", "Delgado", "Goldberg", "Patel", "Santos", "Kim", "Okafor",
        "Haddad", "Murphy", "Nguyen", "Cohen", "Brennan", "Alvarez", "Walsh", "Mendez", "Fischer", "Baptiste"]
GROUPS = ["Riverdale Running Club", "Friends of Tibbetts Brook", "Kingsbridge Garden Society", "PS 81 Class of 2004",
          "Bronx Birders", "Manhattan College Alumni", "Woodlawn Heights Neighbors", "Van Cortlandt Track Club"]
DEDICATIONS = ["In loving memory of Grandma Ruth, who walked here every morning.",
               "For Dad, who taught us to love these trails.",
               "Sit, rest, and enjoy the park.",
               "In honor of 40 years of Saturday runs.",
               "For Sam and Eli. Keep exploring.",
               "Dedicated to the volunteers who keep this park green.",
               "Remembering Frank, who fed every bird in the Bronx.",
               "", "", ""]


def _meters(a, b):
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def path_length(points):
    return sum(_meters(a, b) for a, b in zip(points, points[1:]))


def point_along(points, t):
    """Point at fraction t (0..1) of the polyline's length."""
    target = t * path_length(points)
    for a, b in zip(points, points[1:]):
        seg = _meters(a, b)
        if target <= seg:
            f = target / seg if seg else 0
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        target -= seg
    return tuple(points[-1])


def in_park(lat, lon, boundary):
    """Ray-casting point-in-polygon test against the park boundary."""
    inside = False
    for (y1, x1), (y2, x2) in zip(boundary, boundary[1:] + boundary[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def load_park():
    return json.loads(PARK_DATA.read_text())


def _apportion(weights: dict, total: int) -> dict:
    """Split total across keys in proportion to weights (largest remainder)."""
    s = sum(weights.values())
    raw = {k: total * w / s for k, w in weights.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: total - sum(out.values())]:
        out[k] += 1
    return out


class Command(BaseCommand):
    help = "Create synthetic benches and adoptions. Does nothing if benches already exist, unless --reset."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete all benches, donors, and adoptions first.")
        parser.add_argument("--seed", type=int, default=214, help="Random seed for repeatable data.")

    @transaction.atomic
    def handle(self, *args, reset=False, seed=214, **options):
        if reset:
            Adoption.objects.all().delete()
            Donor.objects.all().delete()
            Bench.objects.all().delete()
        elif Bench.objects.exists():
            self.stdout.write("Benches already exist; skipping seed (use --reset to reseed).")
            return

        rng = random.Random(seed)
        benches = self._benches(rng)
        adoptions = self._adoptions(rng, benches)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(benches)} benches and {adoptions} adoptions."))

    def _benches(self, rng):
        park = load_park()
        by_area = {}
        for p in park["paths"]:
            by_area.setdefault(p["area"], []).append(p)
        counts = _apportion({a: sum(path_length(p["points"]) for p in ps) for a, ps in by_area.items()}, BENCH_COUNT)

        placed = []  # (area, path name, lat, lon)
        for area in sorted(by_area):
            paths = by_area[area]
            weights = [path_length(p["points"]) for p in paths]
            n = 0
            while n < counts[area]:
                path = rng.choices(paths, weights)[0]
                lat, lon = point_along(path["points"], rng.random())
                lat += rng.gauss(0, 0.00002)  # a couple of meters to the side of the path
                lon += rng.gauss(0, 0.00003)
                if not in_park(lat, lon, park["boundary"]):
                    continue
                placed.append((area, path["name"], lat, lon))
                n += 1

        benches = []
        per_area = {}
        for i, (area, path_name, lat, lon) in enumerate(placed, start=1):
            per_area[area] = per_area.get(area, 0) + 1
            where = f"On the {path_name}" if path_name else "On a park path"
            roll = rng.random()
            condition = (Bench.Condition.REMOVED if roll < 0.01
                         else Bench.Condition.UNDER_REPAIR if roll < 0.04
                         else Bench.Condition.ACTIVE)
            benches.append(Bench(
                plaque_code=f"VC-{i:03d}",
                area=area,
                location_description=f"{where} in the {area} area, bench {per_area[area]} of {counts[area]}",
                latitude=Decimal(f"{lat:.6f}"),
                longitude=Decimal(f"{lon:.6f}"),
                condition=condition,
            ))
        return Bench.objects.bulk_create(benches)

    def _donor(self, rng):
        if rng.random() < 0.2:
            group = rng.choice(GROUPS)
            full = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            display = group
        else:
            first, last = rng.choice(FIRST), rng.choice(LAST)
            full = f"{first} {last}"
            display = rng.choice([full, f"The {last} Family", f"{first} {last[0]}."])
        email = f"{full.lower().replace(' ', '.').replace(chr(39), '')}{rng.randint(1, 999)}@example.org"
        return Donor.objects.create(full_name=full, email=email, public_display_name=display)

    def _adoptions(self, rng, benches):
        now = today()
        created = 0
        for bench in benches:
            if bench.condition == Bench.Condition.REMOVED:
                continue
            roll = rng.random()
            terms = []  # (start, years, status)
            if roll < 0.08 and bench.condition == Bench.Condition.ACTIVE:
                # Active and expiring within 60 days: a renewal candidate.
                years = rng.choice([1, 2])
                end = now + datetime.timedelta(days=rng.randint(1, 60))
                terms.append((add_years(end, -years), years, Adoption.Status.ACTIVE))
            elif roll < 0.40 and bench.condition == Bench.Condition.ACTIVE:
                years = rng.choice([1, 1, 2, 5])
                start = now - datetime.timedelta(days=rng.randint(0, 365 * years - 61))
                terms.append((start, years, Adoption.Status.ACTIVE))
                if rng.random() < 0.3:  # an earlier, finished term that ended the day this one began
                    terms.append((add_years(start, -1), 1, Adoption.Status.ACTIVE))
            elif roll < 0.55:
                # Expired: ended between yesterday and three years ago, bench is available again.
                years = rng.choice([1, 2])
                end = now - datetime.timedelta(days=rng.choice([1, rng.randint(2, 365 * 3)]))
                terms.append((add_years(end, -years), years, Adoption.Status.ACTIVE))
            elif roll < 0.58:
                start = now - datetime.timedelta(days=rng.randint(10, 200))
                terms.append((start, 1, Adoption.Status.CANCELLED))

            for start, years, status in terms:
                Adoption.objects.create(
                    bench=bench,
                    donor=self._donor(rng),
                    start_date=start,
                    end_date=add_years(start, years),
                    dedication_text=rng.choice(DEDICATIONS),
                    status=status,
                )
                created += 1
        return created
