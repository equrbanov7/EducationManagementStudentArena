"""RİM jurnal bağlama/açma + bağlanma xəbərdarlığı formaları (kabinet bölməsi).

``organization`` forma sahəsi DEYİL — ``__init__`` kwarg-ı kimi ötürülür; view
yadda saxlamadan əvvəl ``organization``/``created_by`` təyin edir
(``kollokvium_windows`` pattern-i ilə eyni).
"""

from django import forms
from django.utils.translation import pgettext_lazy

from apps.registrar.models import JournalCloseNotice, JournalCloseScope

_CTX = "registrar.journal_close"


def _period_queryset(organization):
    from apps.organizations.models import AcademicPeriod

    return AcademicPeriod.objects.filter(organization=organization).order_by("-start_date")


def _unit_queryset(organization):
    from apps.organizations.models import OrgUnit

    return OrgUnit.objects.filter(organization=organization, is_active=True).order_by("unit_type", "name")


def _validate_scope_unit(form, cleaned):
    """Əhatə ↔ bölmə tipi uyğunluğu (org / fakültə / kafedra)."""
    from core.constants import OrgUnitType

    scope = cleaned.get("scope")
    org_unit = cleaned.get("org_unit")
    if scope in (JournalCloseScope.FACULTY, JournalCloseScope.DEPARTMENT) and org_unit is None:
        form.add_error("org_unit", pgettext_lazy(_CTX, "Fakültə/kafedra əhatəsi üçün bölmə seçilməlidir."))
        return cleaned
    if org_unit is not None:
        kafedra_types = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
        if scope == JournalCloseScope.FACULTY and org_unit.unit_type != OrgUnitType.FACULTY:
            form.add_error("org_unit", pgettext_lazy(_CTX, "Fakültə əhatəsi üçün fakültə seçilməlidir."))
        elif scope == JournalCloseScope.DEPARTMENT and org_unit.unit_type not in kafedra_types:
            form.add_error("org_unit", pgettext_lazy(_CTX, "Kafedra əhatəsi üçün kafedra seçilməlidir."))
    if scope == JournalCloseScope.ORGANIZATION:
        cleaned["org_unit"] = None
    return cleaned


class JournalCloseActionForm(forms.Form):
    """Toplu bağlama/açma əməliyyatının hədəfi: dövr + əhatə (+ səbəb).

    Sətir YAZMIR — yalnız servis çağırışının girişini validasiya edir, ona görə
    qəsdən ``ModelForm`` deyil.
    """

    period = forms.ModelChoiceField(queryset=None, label=pgettext_lazy(_CTX, "Semestr"))
    scope = forms.ChoiceField(choices=JournalCloseScope.choices, label=pgettext_lazy(_CTX, "Əhatə"))
    org_unit = forms.ModelChoiceField(queryset=None, required=False, label=pgettext_lazy(_CTX, "Fakültə / kafedra"))
    reason = forms.CharField(required=False, max_length=1000, label=pgettext_lazy(_CTX, "Səbəb"))

    def __init__(self, *args, organization=None, require_reason=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.require_reason = require_reason
        self.fields["period"].queryset = _period_queryset(organization)
        self.fields["org_unit"].queryset = _unit_queryset(organization)

    def clean(self):
        cleaned = _validate_scope_unit(self, super().clean())
        if self.require_reason and not (cleaned.get("reason") or "").strip():
            # Açma (reopen) üçün səbəb MƏCBURİDİR — servis qatında da yenidən
            # yoxlanılır (yalnız UI məcburiyyəti kifayət deyil).
            self.add_error("reason", pgettext_lazy(_CTX, "Jurnalı açmaq üçün səbəb yazılmalıdır."))
        return cleaned


class JournalCloseNoticeForm(forms.ModelForm):
    """«Jurnallar DD.MM.YYYY tarixindən sonra bağlanacaq» xəbərdarlığı."""

    class Meta:
        model = JournalCloseNotice
        fields = ["period", "scope", "org_unit", "closes_on", "message", "is_active"]
        widgets = {"closes_on": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["period"].queryset = _period_queryset(organization)
        self.fields["org_unit"].queryset = _unit_queryset(organization)
        self.fields["org_unit"].required = False
        self.fields["message"].required = False
        self.fields["is_active"].required = False

    def clean(self):
        return _validate_scope_unit(self, super().clean())
