"""Qrupun NÖVÜ — «Adi qrup» / «Əcnəbi tələbələr qrupu» (sahib 2026-11-25: «qrup yaradarkən seçmək olsun əcnəbi qrupu»).

Dəyər ``OrgUnit.settings["group_kind"]``-dadır (sxem dəyişmir — dil sektoru, forma kimi). Köhnə qruplarda açar yoxdur:
adında «əcnəbi» olan qrup əcnəbi sayılır (``01-əcnəbilər2026``), qalanı adi.

Əcnəbi qrupu nəyi dəyişir:

* «Əcnəbi tələbələrlə iş şöbəsi» əhatəni avtomatik alır (qrup yaradılanda / növü dəyişəndə ``foreign_office_sync``);
* müəllim eyni saatda bir neçə əcnəbi qrupunda dərsi başlada bilir (``registrar`` dərs toqquşması qaydası).
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

GROUP_KIND_KEY = "group_kind"
KIND_REGULAR = ""
KIND_FOREIGN = "foreign"

_CTX = "accounts.groups"

GROUP_KIND_CHOICES = (
    (KIND_REGULAR, pgettext_lazy(_CTX, "Adi qrup")),
    (KIND_FOREIGN, pgettext_lazy(_CTX, "Əcnəbi tələbələr qrupu")),
)
_KNOWN = {value for value, _label in GROUP_KIND_CHOICES}


def kind_options() -> list:
    return [{"value": value, "label": str(label)} for value, label in GROUP_KIND_CHOICES]


def kind_of(unit) -> str:
    """Qrupun növü — açıq seçim, yoxdursa ad qaydası (``default_roles_foreign_office.is_foreign_group``)."""
    from .default_roles_foreign_office import is_foreign_group

    settings = unit.settings if isinstance(getattr(unit, "settings", None), dict) else {}
    value = settings.get(GROUP_KIND_KEY)
    if value in _KNOWN and GROUP_KIND_KEY in settings:
        return value
    return KIND_FOREIGN if is_foreign_group(getattr(unit, "name", ""), getattr(unit, "unit_type", "group")) else ""


def is_foreign(unit) -> bool:
    return unit is not None and kind_of(unit) == KIND_FOREIGN


def kind_label(value: str) -> str:
    return next((str(label) for key, label in GROUP_KIND_CHOICES if key == value), "")


def foreign_group_ids(organization) -> frozenset:
    """Təşkilatın aktiv əcnəbi qruplarının id-ləri — ``organization`` obyektində yaddaşda (sorğu başına bir dəfə)."""
    cached = getattr(organization, "_ems_foreign_group_ids", None)
    if cached is not None:
        return cached
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    units = OrgUnit.objects.filter(organization=organization, unit_type="group", is_active=True).only(
        "id", "name", "unit_type", "settings"
    )
    result = frozenset(str(unit.pk) for unit in units if is_foreign(unit))
    try:
        organization._ems_foreign_group_ids = result
    except AttributeError:  # pragma: no cover — immutable obyekt
        pass
    return result


def apply_kind(settings_blob: dict, post) -> None:
    """Formada sahə VARSA yazılır (köhnə forma göndərmirsə dəyər qalır)."""
    if GROUP_KIND_KEY not in post:
        return
    value = (post.get(GROUP_KIND_KEY) or "").strip()
    settings_blob[GROUP_KIND_KEY] = value if value in _KNOWN else KIND_REGULAR


__all__ = [
    "GROUP_KIND_CHOICES",
    "GROUP_KIND_KEY",
    "KIND_FOREIGN",
    "KIND_REGULAR",
    "apply_kind",
    "foreign_group_ids",
    "is_foreign",
    "kind_label",
    "kind_of",
    "kind_options",
]
