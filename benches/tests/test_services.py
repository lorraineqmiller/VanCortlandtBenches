import datetime
import threading

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.test import TestCase, TransactionTestCase

from benches import services
from benches.models import Adoption, Bench, Donor

from . import factories as f

TODAY = datetime.date(2026, 9, 23)
DAY = datetime.timedelta(days=1)


class AvailabilityTests(TestCase):
    def test_adoption_ended_yesterday_is_available(self):
        b = f.bench()
        f.adoption(b, datetime.date(2025, 9, 22), TODAY - DAY)
        self.assertTrue(services.is_available(b, TODAY))

    def test_adoption_ending_today_is_available_today(self):
        # Ranges are half-open: end_date is the first day the bench is free again.
        b = f.bench()
        f.adoption(b, datetime.date(2025, 9, 23), TODAY)
        self.assertTrue(services.is_available(b, TODAY))
        self.assertFalse(services.is_available(b, TODAY - DAY))

    def test_current_adoption_makes_bench_unavailable(self):
        b = f.bench()
        f.adoption(b, TODAY - 10 * DAY, TODAY + 10 * DAY)
        self.assertFalse(services.is_available(b, TODAY))

    def test_cancelled_adoption_does_not_count(self):
        b = f.bench()
        f.adoption(b, TODAY - 10 * DAY, TODAY + 10 * DAY, status=Adoption.Status.CANCELLED)
        self.assertTrue(services.is_available(b, TODAY))

    def test_under_repair_is_not_available(self):
        b = f.bench(condition=Bench.Condition.UNDER_REPAIR)
        self.assertFalse(services.is_available(b, TODAY))

    def test_annotated_status_matches_is_available(self):
        free, taken, expired = f.bench(), f.bench(), f.bench()
        f.adoption(taken, TODAY - DAY, TODAY + DAY, donor=f.donor(public_display_name="Rivera Family"))
        f.adoption(expired, TODAY - 400 * DAY, TODAY - DAY)
        rows = {b.plaque_code: b for b in services.benches_with_status(TODAY)}
        self.assertFalse(rows[free.plaque_code].is_adopted)
        self.assertFalse(rows[expired.plaque_code].is_adopted)
        self.assertTrue(rows[taken.plaque_code].is_adopted)
        self.assertEqual(rows[taken.plaque_code].adopter_name, "Rivera Family")
        self.assertEqual(rows[taken.plaque_code].term_end, TODAY + DAY)

    def test_removed_benches_are_hidden(self):
        b = f.bench(condition=Bench.Condition.REMOVED)
        self.assertNotIn(b, services.benches_with_status(TODAY))

    def test_available_filter(self):
        free, taken = f.bench(area="Lake"), f.bench(area="Lake")
        f.bench(area="Other")
        f.adoption(taken, TODAY - DAY, TODAY + DAY)
        qs = services.filter_benches(services.benches_with_status(TODAY), area="Lake", available_only=True)
        self.assertEqual(list(qs), [free])


class AdoptTests(TestCase):
    def test_adopt_available_bench(self):
        b = f.bench()
        a = services.adopt(b, f.DONOR_DATA, 2, start=TODAY)
        self.assertEqual((a.start_date, a.end_date), (TODAY, datetime.date(2028, 9, 23)))
        self.assertEqual(a.donor.public_display_name, "Ana L.")
        self.assertFalse(services.is_available(b, TODAY))

    def test_adopt_defaults_to_today(self):
        b = f.bench()
        a = services.adopt(b, f.DONOR_DATA, 1)
        self.assertEqual(a.start_date, services.today())
        self.assertFalse(services.is_available(b))

    def test_overlapping_adoption_rejected(self):
        b = f.bench()
        services.adopt(b, f.DONOR_DATA, 1, start=TODAY)
        with self.assertRaises(services.BenchUnavailable):
            services.adopt(b, f.DONOR_DATA, 1, start=TODAY + 100 * DAY)
        self.assertEqual(Adoption.objects.filter(bench=b).count(), 1)

    def test_failed_adoption_saves_no_donor(self):
        b = f.bench()
        services.adopt(b, f.DONOR_DATA, 1, start=TODAY)
        donors_before = Donor.objects.count()
        with self.assertRaises(services.BenchUnavailable):
            services.adopt(b, {**f.DONOR_DATA, "email": "late@example.org"}, 1, start=TODAY)
        self.assertEqual(Donor.objects.count(), donors_before)

    def test_back_to_back_terms_allowed(self):
        b = f.bench()
        first = services.adopt(b, f.DONOR_DATA, 1, start=TODAY)
        second = services.adopt(b, f.DONOR_DATA, 1, start=first.end_date)
        self.assertEqual(second.start_date, first.end_date)

    def test_adopt_under_repair_rejected(self):
        b = f.bench(condition=Bench.Condition.UNDER_REPAIR)
        with self.assertRaises(services.BenchUnavailable):
            services.adopt(b, f.DONOR_DATA, 1, start=TODAY)

    def test_unsupported_term_rejected(self):
        with self.assertRaises(ValueError):
            services.adopt(f.bench(), f.DONOR_DATA, 3, start=TODAY)

    def test_database_rejects_overlap_directly(self):
        b = f.bench()
        f.adoption(b, TODAY, TODAY + 30 * DAY)
        with self.assertRaises(IntegrityError):
            f.adoption(b, TODAY + 10 * DAY, TODAY + 40 * DAY)

    def test_model_validation_reports_overlap(self):
        # The admin runs full_clean, so staff see a form error rather than a crash.
        b = f.bench()
        f.adoption(b, TODAY, TODAY + 30 * DAY)
        clash = Adoption(bench=b, donor=f.donor(), start_date=TODAY + 5 * DAY, end_date=TODAY + 9 * DAY)
        with self.assertRaises(ValidationError):
            clash.full_clean()

    def test_add_years_leap_day(self):
        self.assertEqual(services.add_years(datetime.date(2028, 2, 29), 1), datetime.date(2029, 2, 28))


class ConcurrentAdoptTests(TransactionTestCase):
    def test_simultaneous_requests_only_one_wins(self):
        b = f.bench()
        n = 6
        barrier = threading.Barrier(n)
        results = []
        lock = threading.Lock()

        def attempt(i):
            try:
                barrier.wait()
                services.adopt(b, {**f.DONOR_DATA, "email": f"racer{i}@example.org"}, 1, start=TODAY)
                outcome = "ok"
            except services.BenchUnavailable:
                outcome = "conflict"
            finally:
                connection.close()
            with lock:
                results.append(outcome)

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(sorted(results), ["conflict"] * (n - 1) + ["ok"])
        self.assertEqual(Adoption.objects.filter(bench=b, status="active").count(), 1)
