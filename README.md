# Van Cortlandt Park Bench Adoption

A small Django app that is the single source of truth for the park's bench adoption program. Anyone can see which of the 500+ benches are adopted, by whom, and until when, on a list and a map, and can adopt an available bench themselves. Staff manage records in the Django admin.

## Run it

```bash
docker compose up --build
```

This starts PostgreSQL, runs migrations, seeds 520 synthetic benches with adoptions, creates a staff login, and serves the app.

- Public site: http://localhost:8000/
- Staff admin: http://localhost:8000/admin/ (login `admin` / `admin`, local development only)

Reseed from scratch with `docker compose exec web python manage.py seed --reset`.

### Tests

```bash
docker compose exec web python manage.py test
```

Without Docker: create a virtualenv, `pip install -r requirements.txt`, point `POSTGRES_HOST` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` at a PostgreSQL 14+ server whose user may create extensions, then `python manage.py migrate && python manage.py seed && python manage.py runserver`.

### Deploy to Vercel

1. Add a Postgres database to the project (Vercel dashboard → Storage, e.g. Neon). It sets `DATABASE_URL`.
2. Set `DJANGO_SECRET_KEY` to a long random string in the project's environment variables.
3. Create the tables and seed data once from your machine, pointing at that database:
   `DATABASE_URL="<the Vercel value>" python manage.py migrate && DATABASE_URL="<same>" python manage.py seed`
4. Create a staff login the same way: `DATABASE_URL="<same>" python manage.py createsuperuser`.

On Vercel, `DEBUG` is off by default and the deployment's hostnames are allowed automatically. For a custom domain, add it to `DJANGO_ALLOWED_HOSTS` (comma-separated).

## Pages

| URL | What it does |
| --- | --- |
| `/` | Map and table of every bench, filterable by area and "available only", 100 rows per page |
| `/benches.geojson` | Map data, same filters as the list, public fields only |
| `/benches/<code>/` | Bench detail; adoption form when the bench is available |
| `/adoptions/<id>/confirmed/` | Confirmation with bench code and term dates |
| `/admin/` | Staff: correct records, cancel adoptions, add or retire benches |

## Data model

| Table | Fields | Notes |
| --- | --- | --- |
| Bench | plaque_code (unique), area, location_description, latitude, longitude, condition (active / under repair / removed) | `plaque_code` is the ID people use, e.g. VC-214 |
| Donor | full_name, email, public_display_name | Contact fields are never shown publicly |
| Adoption | bench, donor, start_date, end_date, dedication_text (≤120), status (active / cancelled), created_at | Covers the half-open range `[start_date, end_date)` |

A bench is **available** on a date if its condition is active and no active adoption's range contains that date. Status is computed by query (`benches/services.py`), never stored on the bench, so it can't go stale and expiry needs no background job. Past adoptions stay on record.

Removed benches are hidden from public pages. Benches under repair are listed but can't be adopted.

## Key decisions

**The database prevents double adoption.** Two visitors can submit for the same bench at the same moment, and "check, then insert" in the app would let both through. A PostgreSQL exclusion constraint (`no_overlapping_adoptions`, declared on `Adoption.Meta` and created in migration `0001`) rejects any second active adoption whose date range overlaps an existing one for the same bench:

```sql
EXCLUDE USING gist (bench_id WITH =, daterange(start_date, end_date) WITH &&)
WHERE (status = 'active')
```

`services.adopt()` catches that specific violation and raises `BenchUnavailable`, and the page shows an "already adopted" message with nothing saved (the donor row is rolled back too). Because ranges are half-open, a new term may start the same day the previous one ends. The admin validates the same constraint, so staff get a form error instead of a crash.

**Business logic lives in `benches/services.py`.** `is_available`, `benches_with_status`, and `adopt` hold the rules; views stay thin and tests exercise the rules without HTTP.

**Server-rendered pages, Leaflet map.** The map uses Leaflet with OpenStreetMap tiles and marker clustering, loaded from cdnjs, with no API key. It reads `/benches.geojson`, which applies the same filters as the table. Available benches are deep sage, adopted or under-repair benches muted gray, and every popup and table row also states the status in words.

**UI.** Sage theme and Bellefair type, defined once as CSS variables in `benches/static/benches/site.css`. Body text is 18px at 1.6 line height. The PRD's muted gray (#8A8F85) is below AA contrast for small text on the page background, so it is used only for map markers and a darker variant (#5E6359) is used for secondary text.

## Assumptions

1. Adoption takes effect immediately on submit; there is no staff approval step.
2. One adopter per bench at a time. Terms can't overlap; back-to-back terms are fine.
3. Terms are 1, 2, or 5 years starting the day of adoption. The model already supports arbitrary dates.
4. The public sees the display name, dedication, and term end date, never full name or email.
5. No user accounts. Adopters give a name and email; staff handle changes and cancellations in the admin.
6. Bench data is synthetic, since real records were not provided. Benches are placed along real park footpaths taken from OpenStreetMap and always fall inside the park boundary (checked by a test), so the map looks plausible. Areas are named for the nearest landmark (Parade Ground, Van Cortlandt Lake, Northwest Forest, and so on). Donor names and emails are made up (`@example.org`).
7. Payment is out of scope.

## Project layout

- `benches/models.py`: Bench, Donor, Adoption, and the exclusion constraint
- `benches/services.py`: availability and adoption rules
- `benches/views.py`, `benches/urls.py`, `benches/forms.py`: list, map data, detail and adopt, confirmation
- `benches/templates/benches/`, `benches/static/benches/`: pages, stylesheet, map script
- `benches/admin.py`: staff admin with a "cancel selected adoptions" action
- `benches/management/commands/seed.py`: 520 synthetic benches and a mix of active, expiring, expired, cancelled, and never-adopted records
- `benches/data/park.json`: park boundary and footpaths from OpenStreetMap, regenerated with `python scripts/build_park_data.py`
- `benches/tests/`: service tests (including a concurrent-submission test), view tests, and seed tests

## Next steps

In rough priority order for a real rollout:

1. Import the park's existing adoption records and real bench coordinates, and reconcile conflicts.
2. Staff approval before an adoption becomes active.
3. Renewal flow with first right of renewal for current adopters.
4. Expiry reminder emails and a staff report of terms ending in 30, 60, and 90 days.
5. Future-dated reservations and a waitlist for adopted benches.
6. Payment integration.
7. Moderation rules for dedication text.
8. Production hardening: gunicorn, static file serving, a real secret key, and an unguessable confirmation URL.

---

Park boundary and path data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, available under the ODbL.
