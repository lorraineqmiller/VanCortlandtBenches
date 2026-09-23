import datetime

from django.test import TestCase
from django.urls import reverse

from benches import services
from benches.models import Adoption, Donor

from . import factories as f

DAY = datetime.timedelta(days=1)


class PublicPagesTests(TestCase):
    def setUp(self):
        self.today = services.today()
        self.free = f.bench(plaque_code="VC-001", area="Van Cortlandt Lake")
        self.taken = f.bench(plaque_code="VC-002", area="Parade Ground")
        f.adoption(self.taken, self.today - DAY, self.today + 30 * DAY,
                   donor=f.donor(full_name="Secret Person", email="secret@example.org", public_display_name="The Okafor Family"))

    def test_list_shows_status_and_filters(self):
        r = self.client.get(reverse("bench_list"))
        self.assertContains(r, "VC-001")
        self.assertContains(r, "The Okafor Family")
        r = self.client.get(reverse("bench_list"), {"available": "1"})
        self.assertContains(r, "VC-001")
        self.assertNotContains(r, "VC-002")
        r = self.client.get(reverse("bench_list"), {"area": "Parade Ground"})
        self.assertNotContains(r, "VC-001")

    def test_geojson_uses_same_filters(self):
        data = self.client.get(reverse("benches_geojson"), {"available": "1"}).json()
        self.assertEqual([x["properties"]["code"] for x in data["features"]], ["VC-001"])
        taken = self.client.get(reverse("benches_geojson"), {"area": "Parade Ground"}).json()["features"][0]
        self.assertEqual(taken["properties"]["adopter"], "The Okafor Family")
        self.assertEqual(taken["properties"]["status"], "Adopted")

    def test_no_private_contact_info_on_public_pages(self):
        pages = [
            reverse("bench_list"),
            reverse("benches_geojson"),
            reverse("bench_detail", args=["VC-002"]),
        ]
        for url in pages:
            body = self.client.get(url).content.decode()
            self.assertNotIn("secret@example.org", body, url)
            self.assertNotIn("Secret Person", body, url)

    def test_detail_of_adopted_bench_has_no_form(self):
        r = self.client.get(reverse("bench_detail", args=["VC-002"]))
        self.assertContains(r, "The Okafor Family")
        self.assertNotContains(r, "Adopt this bench")


class AdoptFlowTests(TestCase):
    def setUp(self):
        self.bench = f.bench(plaque_code="VC-100")
        self.url = reverse("bench_detail", args=["VC-100"])
        self.form = {**f.DONOR_DATA, "term_years": "5"}

    def test_successful_adoption(self):
        r = self.client.post(self.url, self.form, follow=True)
        self.assertContains(r, "VC-100")
        self.assertContains(r, "Ana L.")
        a = Adoption.objects.get(bench=self.bench)
        self.assertEqual(a.end_date, services.add_years(services.today(), 5))
        self.assertNotContains(self.client.get(self.url), "Adopt this bench")
        self.assertNotContains(r, "ana.lopez@example.org")

    def test_conflict_shows_message_and_saves_nothing(self):
        # Simulate the bench being taken while the visitor filled out the form.
        page = self.client.get(self.url)
        self.assertContains(page, "Adopt this bench")
        services.adopt(self.bench, {**f.DONOR_DATA, "email": "first@example.org"}, 1)
        donors = Donor.objects.count()
        r = self.client.post(self.url, {**self.form, "email": "second@example.org"})
        self.assertEqual(r.status_code, 409)
        self.assertContains(r, "no longer available", status_code=409)
        self.assertEqual(Donor.objects.count(), donors)
        self.assertEqual(Adoption.objects.filter(bench=self.bench).count(), 1)

    def test_invalid_input_shows_field_errors(self):
        bad = {**self.form, "full_name": "", "email": "not-an-email", "dedication_text": "x" * 121}
        r = self.client.post(self.url, bad)
        self.assertEqual(r.status_code, 200)
        form = r.context["form"]
        self.assertIn("full_name", form.errors)
        self.assertIn("email", form.errors)
        self.assertIn("dedication_text", form.errors)
        self.assertEqual(Adoption.objects.count(), 0)
        self.assertEqual(Donor.objects.count(), 0)

    def test_unsupported_term_is_field_error(self):
        r = self.client.post(self.url, {**self.form, "term_years": "3"})
        self.assertIn("term_years", r.context["form"].errors)
        self.assertEqual(Adoption.objects.count(), 0)
