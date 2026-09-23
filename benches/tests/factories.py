import datetime
from decimal import Decimal

from benches.models import Adoption, Bench, Donor

_n = 0


def bench(**kw):
    global _n
    _n += 1
    defaults = dict(
        plaque_code=f"T-{_n:04d}", area="Parade Ground", location_description="Test path",
        latitude=Decimal("40.890000"), longitude=Decimal("-73.895000"),
    )
    return Bench.objects.create(**{**defaults, **kw})


def donor(**kw):
    defaults = dict(full_name="Pat Private", email="pat.private@example.org", public_display_name="The Park Fans")
    return Donor.objects.create(**{**defaults, **kw})


def adoption(b, start: datetime.date, end: datetime.date, **kw):
    return Adoption.objects.create(bench=b, donor=kw.pop("donor", None) or donor(), start_date=start, end_date=end, **kw)


DONOR_DATA = {
    "full_name": "Ana Lopez",
    "email": "ana.lopez@example.org",
    "public_display_name": "Ana L.",
    "dedication_text": "For my mother.",
}
