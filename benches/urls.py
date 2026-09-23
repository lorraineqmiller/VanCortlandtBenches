from django.urls import path

from . import views

urlpatterns = [
    path("", views.bench_list, name="bench_list"),
    path("benches.geojson", views.benches_geojson, name="benches_geojson"),
    path("benches/<str:code>/", views.bench_detail, name="bench_detail"),
    path("adoptions/<int:pk>/confirmed/", views.adoption_confirmed, name="adoption_confirmed"),
]
