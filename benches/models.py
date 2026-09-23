from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q


class DateRange(Func):
    """SQL daterange(start, end), half-open [start, end) by default."""

    function = "daterange"
    output_field = DateRangeField()


class Bench(models.Model):
    class Condition(models.TextChoices):
        ACTIVE = "active", "Active"
        UNDER_REPAIR = "under_repair", "Under repair"
        REMOVED = "removed", "Removed"

    plaque_code = models.CharField(max_length=16, unique=True, help_text="Human-readable ID, e.g. VC-214.")
    area = models.CharField(max_length=80, db_index=True)
    location_description = models.CharField(max_length=200)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    condition = models.CharField(max_length=16, choices=Condition.choices, default=Condition.ACTIVE)

    class Meta:
        ordering = ["plaque_code"]
        verbose_name_plural = "benches"

    def __str__(self):
        return self.plaque_code


class Donor(models.Model):
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    public_display_name = models.CharField(max_length=80)

    def __str__(self):
        return f"{self.full_name} <{self.email}>"


class Adoption(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    bench = models.ForeignKey(Bench, on_delete=models.PROTECT, related_name="adoptions")
    donor = models.ForeignKey(Donor, on_delete=models.PROTECT, related_name="adoptions")
    start_date = models.DateField()
    end_date = models.DateField(help_text="Exclusive: the term covers [start_date, end_date).")
    dedication_text = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gt=F("start_date")),
                name="adoption_end_after_start",
            ),
            # Two active adoptions of one bench may never overlap in time. Enforced by
            # PostgreSQL itself, so it holds under concurrent requests.
            ExclusionConstraint(
                name="no_overlapping_adoptions",
                expressions=[
                    ("bench", RangeOperators.EQUAL),
                    (DateRange("start_date", "end_date"), RangeOperators.OVERLAPS),
                ],
                condition=Q(status="active"),
                violation_error_message="This bench is already adopted for part of that term.",
            ),
        ]

    def __str__(self):
        return f"{self.bench} {self.start_date}–{self.end_date}"
