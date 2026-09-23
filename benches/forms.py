from django import forms

from .services import TERM_CHOICES


class AdoptionForm(forms.Form):
    full_name = forms.CharField(label="Your full name", max_length=120)
    email = forms.EmailField(label="Email", help_text="Kept private. Staff use it to contact you.")
    public_display_name = forms.CharField(
        label="Public display name", max_length=80, help_text="Shown on the site, e.g. “The Rivera Family”."
    )
    dedication_text = forms.CharField(
        label="Dedication (optional)",
        max_length=120,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "maxlength": 120}),
        help_text="Up to 120 characters.",
    )
    term_years = forms.TypedChoiceField(
        label="Term",
        choices=list(TERM_CHOICES.items()),
        coerce=int,
        initial=1,
        widget=forms.RadioSelect,
    )

    def clean(self):
        data = super().clean()
        for key in ("full_name", "public_display_name", "dedication_text"):
            if key in data:
                data[key] = data[key].strip()
        return data
