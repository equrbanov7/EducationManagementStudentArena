"""Kollokvium bal-yazma pəncərəsi + əlavə gün formaları (İmtahan Mərkəzi kabineti).

``organization`` hər iki formaya __init__ kwarg kimi ötürülür (model sahəsi
DEYİL) — view yadda saxlamadan əvvəl ``organization``/``created_by`` təyin edir
(``superadmin_exam_rooms`` pattern-i ilə eyni).
"""

from django import forms
from django.utils.translation import pgettext_lazy

from apps.registrar.models import KollokviumExtraGrant, KollokviumWindow


class KollokviumWindowForm(forms.ModelForm):
    """K1/K2/K3 üçün bal-yazma aralığı (org + period başına)."""

    k_index = forms.TypedChoiceField(
        choices=[(0, "K1"), (1, "K2"), (2, "K3")],
        coerce=int,
        label=pgettext_lazy("registrar.kollokvium_window", "Kollokvium"),
    )

    class Meta:
        model = KollokviumWindow
        fields = ["period", "k_index", "opens_on", "closes_on"]
        widgets = {
            "opens_on": forms.DateInput(attrs={"type": "date"}),
            "closes_on": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        from apps.organizations.models import AcademicPeriod

        self.fields["period"].queryset = AcademicPeriod.objects.filter(organization=organization).order_by(
            "-start_date"
        )

    def clean(self):
        cleaned = super().clean()
        opens, closes = cleaned.get("opens_on"), cleaned.get("closes_on")
        if opens and closes and closes < opens:
            self.add_error(
                "closes_on",
                pgettext_lazy("registrar.kollokvium_window", "Bağlanış tarixi açılışdan sonra olmalıdır."),
            )
        return cleaned


class KollokviumExtraGrantForm(forms.ModelForm):
    """Rəhbərin verdiyi əlavə gün — org / fakültə / kafedra əhatəsində."""

    class Meta:
        model = KollokviumExtraGrant
        fields = ["scope", "org_unit", "extra_days"]

    def __init__(self, *args, organization=None, window=None, include_unit_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.window = window
        from django.db.models import Q

        from apps.organizations.models import OrgUnit

        # Aktiv bölmələr + (redaktədə) qrantın hazırkı bölməsi deaktiv olsa belə —
        # onda mövcud fakültə/kafedra qrantının gün sayını dəyişmək mümkün olsun.
        unit_filter = Q(organization=organization, is_active=True)
        if include_unit_id:
            unit_filter |= Q(pk=include_unit_id)
        self.fields["org_unit"].queryset = OrgUnit.objects.filter(unit_filter).order_by("unit_type", "name")
        self.fields["org_unit"].required = False

    def clean(self):
        from core.constants import OrgUnitType

        cleaned = super().clean()
        scope = cleaned.get("scope")
        org_unit = cleaned.get("org_unit")
        if scope in (KollokviumExtraGrant.Scope.FACULTY, KollokviumExtraGrant.Scope.DEPARTMENT) and org_unit is None:
            self.add_error(
                "org_unit",
                pgettext_lazy("registrar.kollokvium_window", "Fakültə/kafedra əhatəsi üçün bölmə seçilməlidir."),
            )
        # Əhatə ↔ bölmə tipi uyğunluğu: fakültə əhatəsi ancaq fakültə, kafedra
        # əhatəsi ancaq kafedra (chair/department) seçə bilər.
        if org_unit is not None:
            kafedra_types = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
            if scope == KollokviumExtraGrant.Scope.FACULTY and org_unit.unit_type != OrgUnitType.FACULTY:
                self.add_error(
                    "org_unit",
                    pgettext_lazy("registrar.kollokvium_window", "Fakültə əhatəsi üçün fakültə seçilməlidir."),
                )
            elif scope == KollokviumExtraGrant.Scope.DEPARTMENT and org_unit.unit_type not in kafedra_types:
                self.add_error(
                    "org_unit",
                    pgettext_lazy("registrar.kollokvium_window", "Kafedra əhatəsi üçün kafedra seçilməlidir."),
                )
        if scope == KollokviumExtraGrant.Scope.ORGANIZATION:
            cleaned["org_unit"] = None
        days = cleaned.get("extra_days")
        if days is not None and days < 1:
            self.add_error("extra_days", pgettext_lazy("registrar.kollokvium_window", "Ən azı 1 gün olmalıdır."))
        elif days is not None and days > 30:
            # Client max=30-u server-side də məcburi et (crafted POST-a qarşı).
            self.add_error("extra_days", pgettext_lazy("registrar.kollokvium_window", "Ən çox 30 gün ola bilər."))
        return cleaned
