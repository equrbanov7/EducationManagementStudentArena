"""«Bütün müraciətlər» (RİM nəzarəti) — şöbə / göndərən bölməsi süzgəcləri.

Tabın özü ``queries.list_applications``-dən keçir (eyni sorğu, səhifələmə, sətir payload-u);
burada YALNIZ bu taba xas iki süzgəc var:

* **Şöbə (ünvan)** — müraciətin CARİ şöbəsi (``ApplicationUnit.code``: dekanlıq, RİM, …).
* **Göndərənin bölməsi** — göndərənin ``sender_scope_unit``-i seçilmiş ``OrgUnit``-in
  ALT-AĞACINDADIR (fakültə seçiləndə onun kafedra/ixtisas/qrupları da daxildir) —
  materiallaşdırılmış ``path`` prefiksi ilə, rekursiv sorğusuz.

Görünüş qapısı (``access.can_oversee``) burada DEYİL, tab sorğusunda və endpoint-dədir —
süzgəclər yalnız artıq görünən dəstə tətbiq olunur.
"""

from __future__ import annotations

import uuid

from django.apps import apps as django_apps
from django.db.models import Q
from django.utils.translation import pgettext

from core.constants import OrgUnitType

from . import access

_CTX = "applications"

#: Göndərən süzgəcinin seçimləri — strukturun «oxunan» səviyyələri. Qrup/ixtisas
#: siyahını yüzlərlə sətrə şişirdərdi; onlar fakültə/kafedra alt-ağacına onsuz da düşür.
_SENDER_GROUPS = (
    ("faculty", (OrgUnitType.FACULTY,)),
    ("chair", (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)),
    (
        "other",
        (OrgUnitType.INSTITUTE, OrgUnitType.CENTER, OrgUnitType.RECTORATE, OrgUnitType.VICE_RECTORATE),
    ),
)


def _group_label(key: str) -> str:
    if key == "faculty":
        return pgettext(_CTX, "Fakültələr")
    if key == "chair":
        return pgettext(_CTX, "Kafedralar")
    return pgettext(_CTX, "Mərkəz və digər bölmələr")


def _org_unit_model():
    # Modul sərhədi: model app registry ilə (``routing.sender_scope_unit_for`` naxışı).
    return django_apps.get_model("organizations", "OrgUnit")


def sender_unit_options(user, organization) -> list:
    """Göndərən bölməsi seçicisi: ``[{"label", "units": [{"id", "name"}]}]`` — yalnız nəzarətçiyə.

    TƏK sorğu (``only`` ilə dar sütunlar); nəzarətçi olmayana heç bir sorğu getmir.
    """
    if not access.can_oversee(user, organization):
        return []
    type_to_group = {unit_type: key for key, types in _SENDER_GROUPS for unit_type in types}
    rows = (
        _org_unit_model()
        .objects.filter(organization=organization, is_active=True, unit_type__in=list(type_to_group))
        .only("id", "name", "unit_type")
        .order_by("name")
    )
    grouped = {key: [] for key, _types in _SENDER_GROUPS}
    for unit in rows:
        grouped[type_to_group[unit.unit_type]].append({"id": str(unit.pk), "name": unit.name})
    return [{"label": _group_label(key), "units": grouped[key]} for key, _types in _SENDER_GROUPS if grouped[key]]


def unit_q(unit_code: str) -> Q:
    """Cari şöbə (``ApplicationUnit.code``) üzrə; boş → ``Q()``."""
    code = (unit_code or "").strip()
    return Q(current_unit__code=code) if code else Q()


def sender_unit_q(organization, raw_unit_id) -> Q:
    """Göndərənin bölməsi seçilmiş bölmə və ya onun ALT-AĞACIDIR; boş → ``Q()``.

    Yararsız / başqa təşkilatın / tapılmayan id → BOŞ nəticə (``pk__in=[]``): süzgəci
    səssizcə atmaq «bütün müraciətlər»i göstərib istifadəçini çaşdırardı.
    """
    raw = (raw_unit_id or "").strip() if isinstance(raw_unit_id, str) else raw_unit_id
    if not raw:
        return Q()
    try:
        unit_id = uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return Q(pk__in=[])
    path = (
        _org_unit_model().objects.filter(organization=organization, pk=unit_id).values_list("path", flat=True).first()
    )
    if path is None:
        return Q(pk__in=[])
    query = Q(sender_scope_unit_id=unit_id)
    if path:
        query |= Q(sender_scope_unit__path__startswith=f"{path}/")
    return query


__all__ = ["sender_unit_options", "sender_unit_q", "unit_q"]
