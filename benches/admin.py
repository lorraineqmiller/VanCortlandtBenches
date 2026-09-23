from django.contrib import admin

from .models import Adoption, Bench, Donor


class AdoptionInline(admin.TabularInline):
    model = Adoption
    extra = 0
    fields = ("donor", "start_date", "end_date", "status", "dedication_text")
    raw_id_fields = ("donor",)


@admin.register(Bench)
class BenchAdmin(admin.ModelAdmin):
    list_display = ("plaque_code", "area", "condition", "location_description")
    list_filter = ("condition", "area")
    search_fields = ("plaque_code", "location_description")
    inlines = [AdoptionInline]


@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "public_display_name", "email")
    search_fields = ("full_name", "public_display_name", "email")


@admin.register(Adoption)
class AdoptionAdmin(admin.ModelAdmin):
    list_display = ("bench", "donor", "start_date", "end_date", "status", "created_at")
    list_filter = ("status", "bench__area")
    search_fields = ("bench__plaque_code", "donor__full_name", "donor__email")
    raw_id_fields = ("bench", "donor")
    date_hierarchy = "end_date"
    actions = ["cancel_adoptions"]

    @admin.action(description="Cancel selected adoptions")
    def cancel_adoptions(self, request, queryset):
        n = queryset.update(status=Adoption.Status.CANCELLED)
        self.message_user(request, f"Cancelled {n} adoption(s).")
