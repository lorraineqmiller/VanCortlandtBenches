from django.core.management import call_command
from django.test import TestCase

from benches import services
from benches.management.commands.seed import in_park, load_park
from benches.models import Adoption, Bench


class SeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed", verbosity=0)

    def test_seeds_500_plus_benches_inside_the_park(self):
        boundary = load_park()["boundary"]
        benches = list(Bench.objects.all())
        self.assertGreaterEqual(len(benches), 500)
        outside = [b.plaque_code for b in benches if not in_park(float(b.latitude), float(b.longitude), boundary)]
        self.assertEqual(outside, [])

    def test_mix_of_statuses(self):
        rows = list(services.benches_with_status())
        adopted = sum(b.is_adopted for b in rows)
        self.assertGreater(adopted, 50)
        self.assertGreater(len(rows) - adopted, 50)
        self.assertTrue(Adoption.objects.filter(end_date__lt=services.today()).exists())
        self.assertTrue(Adoption.objects.filter(status=Adoption.Status.CANCELLED).exists())
        self.assertTrue(Bench.objects.filter(condition=Bench.Condition.UNDER_REPAIR).exists())

    def test_seed_is_idempotent(self):
        before = Bench.objects.count()
        call_command("seed", verbosity=0)
        self.assertEqual(Bench.objects.count(), before)
