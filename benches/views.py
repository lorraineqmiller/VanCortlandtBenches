from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from . import services
from .forms import AdoptionForm
from .models import Adoption, Bench


def _filters(request):
    return {
        "area": request.GET.get("area", "").strip(),
        "available_only": request.GET.get("available") == "1",
    }


def bench_list(request):
    filters = _filters(request)
    qs = services.filter_benches(services.benches_with_status(), **filters)
    page = Paginator(qs, 100).get_page(request.GET.get("page"))
    for bench in page:
        bench.status = services.status_label(bench)
    areas = (
        Bench.objects.exclude(condition=Bench.Condition.REMOVED)
        .order_by("area").values_list("area", flat=True).distinct()
    )
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "benches/bench_list.html", {
        "page": page,
        "areas": areas,
        "filters": filters,
        "filter_query": query.urlencode(),
    })


def benches_geojson(request):
    """Map data. Public fields only: never donor names beyond display name, never contact info."""
    qs = services.filter_benches(services.benches_with_status(), **_filters(request))
    features = []
    for b in qs:
        status = services.status_label(b)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(b.longitude), float(b.latitude)]},
            "properties": {
                "code": b.plaque_code,
                "area": b.area,
                "status": status,
                "adopter": b.adopter_name if b.is_adopted else None,
                "term_end": b.term_end.isoformat() if b.is_adopted else None,
                "url": reverse("bench_detail", args=[b.plaque_code]),
            },
        })
    return JsonResponse({"type": "FeatureCollection", "features": features})


def bench_detail(request, code):
    bench = get_object_or_404(Bench.objects.exclude(condition=Bench.Condition.REMOVED), plaque_code=code)
    conflict = None
    form = AdoptionForm()

    if request.method == "POST":
        form = AdoptionForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                adoption = services.adopt(bench, data, data["term_years"])
            except services.BenchUnavailable as exc:
                conflict = str(exc)
            else:
                return redirect("adoption_confirmed", pk=adoption.pk)

    current = services.current_adoption(bench)
    available = services.is_available(bench)
    return render(request, "benches/bench_detail.html", {
        "bench": bench,
        "current": current,
        "available": available,
        "form": form,
        "conflict": conflict,
    }, status=409 if conflict else 200)


def adoption_confirmed(request, pk):
    adoption = get_object_or_404(Adoption.objects.select_related("bench", "donor"), pk=pk)
    return render(request, "benches/confirmation.html", {"adoption": adoption})
