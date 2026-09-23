"""Bench availability and adoption rules. Views call these; tests exercise them directly."""

import datetime

from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, QuerySet, Subquery
from django.utils import timezone

from .models import Adoption, Bench, Donor

TERM_CHOICES = {1: "1 year", 2: "2 years", 5: "5 years"}
EXCLUSION_CONSTRAINT = "no_overlapping_adoptions"


class BenchUnavailable(Exception):
    """The bench is adopted, under repair, or removed for the requested term."""


def today() -> datetime.date:
    return timezone.localdate()


def add_years(d: datetime.date, years: int) -> datetime.date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29 in a non-leap target year
        return d.replace(year=d.year + years, day=28)


def _covering(on_date: datetime.date):
    """Active adoptions whose [start_date, end_date) contains on_date."""
    return Adoption.objects.filter(
        status=Adoption.Status.ACTIVE, start_date__lte=on_date, end_date__gt=on_date
    )


def current_adoption(bench: Bench, on_date: datetime.date | None = None) -> Adoption | None:
    on_date = on_date or today()
    return _covering(on_date).filter(bench=bench).select_related("donor").first()


def is_available(bench: Bench, on_date: datetime.date | None = None) -> bool:
    on_date = on_date or today()
    return bench.condition == Bench.Condition.ACTIVE and current_adoption(bench, on_date) is None


def benches_with_status(on_date: datetime.date | None = None) -> QuerySet[Bench]:
    """Public benches annotated with is_adopted, adopter_name, and term_end for on_date.

    Status is computed, never stored, so expiry needs no background job.
    """
    on_date = on_date or today()
    current = _covering(on_date).filter(bench=OuterRef("pk"))
    return (
        Bench.objects.exclude(condition=Bench.Condition.REMOVED)
        .annotate(
            is_adopted=Exists(current),
            adopter_name=Subquery(current.values("donor__public_display_name")[:1]),
            term_end=Subquery(current.values("end_date")[:1]),
        )
    )


def filter_benches(qs: QuerySet[Bench], area: str = "", available_only: bool = False) -> QuerySet[Bench]:
    if area:
        qs = qs.filter(area=area)
    if available_only:
        qs = qs.filter(is_adopted=False, condition=Bench.Condition.ACTIVE)
    return qs


def status_label(bench: Bench) -> str:
    """Label for a bench from benches_with_status()."""
    if bench.condition == Bench.Condition.UNDER_REPAIR:
        return "Under repair"
    return "Adopted" if bench.is_adopted else "Available"


def adopt(bench: Bench, donor_data: dict, term_years: int, start: datetime.date | None = None) -> Adoption:
    """Adopt a bench starting today (or `start`) for `term_years` years.

    donor_data needs full_name, email, public_display_name; dedication_text is optional.
    Raises BenchUnavailable if the bench cannot be adopted for that term, including when
    another request wins a race for it — the database exclusion constraint is the final word.
    """
    if term_years not in TERM_CHOICES:
        raise ValueError(f"Unsupported term: {term_years}")
    start = start or today()
    end = add_years(start, term_years)

    if bench.condition != Bench.Condition.ACTIVE:
        raise BenchUnavailable(f"{bench.plaque_code} is not currently open for adoption.")

    try:
        with transaction.atomic():
            donor = Donor.objects.create(
                full_name=donor_data["full_name"],
                email=donor_data["email"],
                public_display_name=donor_data["public_display_name"],
            )
            return Adoption.objects.create(
                bench=bench,
                donor=donor,
                start_date=start,
                end_date=end,
                dedication_text=donor_data.get("dedication_text", ""),
            )
    except IntegrityError as exc:
        if _constraint_name(exc) == EXCLUSION_CONSTRAINT:
            raise BenchUnavailable(f"{bench.plaque_code} was just adopted by someone else.") from exc
        raise


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)

