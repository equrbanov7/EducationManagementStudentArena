"""Midterm/kollokvium bal-yazma pəncərəsi + əlavə gün formaları (İmtahan Mərkəzi kabineti).

``organization`` hər iki formaya __init__ kwarg kimi ötürülür (model sahəsi
DEYİL) — view yadda saxlamadan əvvəl ``organization``/``created_by`` təyin edir
(``superadmin_exam_rooms`` pattern-i ilə eyni).

``KollokviumWindowForm.k_index`` seçimləri GÖNDƏRİLƏN semestrin aralıq
qiymətləndirmə rejimindən gəlir (``registrar.interim_assessment`` — tək mənbə):
midterm (2026/2027-dən) → yalnız ``0`` «Midterm»; kollokvium (keçmiş dövrlər) →
``0/1/2`` «K1/K2/K3». Midterm semestrinə göndərilən (crafted) ``k_index>0``
server-side rədd edilir — həm seçim validasiyası, həm ``clean()`` invariantı ilə.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import pgettext_lazy

from apps.registrar.models import KollokviumExtraGrant, KollokviumWindow
from apps.registrar.public import interim_assessment

_CTX = "registrar.kollokvium_window"

#: Semestr hələ məlum deyilsə (boş/yanlış ``period``) — ən geniş (köhnə) seçim dəsti;
#: belə formada ``period`` xətası onsuz da birinci göstərilir.
_ALL_K_CHOICES = [(index, f"K{index + 1}") for index in range(interim_assessment.KOLLOKVIUM_COUNT)]

MIDTERM_ONLY_MESSAGE = pgettext_lazy(
    _CTX,
    "Bu semestr midterm rejimindədir: K1/K2/K3 kollokviumları əvəzinə yalnız bir «Midterm» pəncərəsi təyin olunur.",
)


class KollokviumWindowForm(forms.ModelForm):
    """Semestrin rejiminə görə Midterm və ya K1/K2/K3 bal-yazma aralığı (org + period başına)."""

    k_index = forms.TypedChoiceField(
        choices=_ALL_K_CHOICES,
        coerce=int,
        label=pgettext_lazy(_CTX, "Kollokvium"),
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
        #: Semestrin rejim təsviri (``InterimSpec``); ``clean()`` onu validasiya
        #: olunmuş semestrdən yenidən təyin edir — view K-sıra qaydasını buna görə tətbiq edir.
        self.interim_spec = None
        period = self._submitted_period()
        if period is not None:
            self._apply_mode(interim_assessment.spec_for_period(period, organization))

    def _submitted_period(self):
        """Göndərilən (və ya ilkin) ``period`` — yalnız bu təşkilatın dövrləri arasında; tapılmasa None."""
        raw = self.data.get(self.add_prefix("period")) if self.is_bound else self.initial.get("period")
        raw = getattr(raw, "pk", raw)
        if not raw:
            return None
        try:
            return self.fields["period"].queryset.filter(pk=raw).first()
        except (ValidationError, ValueError, TypeError):  # UUID olmayan dəyər → sahə xətası validasiyada
            return None

    def _apply_mode(self, spec):
        """``k_index`` seçimlərini rejimə uyğunlaşdır: midterm → [0 «Midterm»], kollokvium → K1/K2/K3."""
        self.interim_spec = spec
        field = self.fields["k_index"]
        field.choices = [(index, spec.label_for(index)) for index in range(spec.count)]
        field.label = spec.title
        if spec.is_midterm:
            field.error_messages["invalid_choice"] = MIDTERM_ONLY_MESSAGE

    def clean(self):
        cleaned = super().clean()
        opens, closes = cleaned.get("opens_on"), cleaned.get("closes_on")
        if opens and closes and closes < opens:
            self.add_error(
                "closes_on",
                pgettext_lazy(_CTX, "Bağlanış tarixi açılışdan sonra olmalıdır."),
            )
        period, k_index = cleaned.get("period"), cleaned.get("k_index")
        if period is not None:
            self.interim_spec = interim_assessment.spec_for_period(period, self.organization)
            # İnvariant (seçim validasiyasından asılı olmadan): midterm semestrində tək pəncərə.
            if self.interim_spec.is_midterm and k_index is not None and k_index >= self.interim_spec.count:
                self.add_error("k_index", MIDTERM_ONLY_MESSAGE)
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
