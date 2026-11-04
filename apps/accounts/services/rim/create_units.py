"""RİM «yeni hesab» — «Kafedra / bölmə» SEÇİCİSİNİN siyahısı və müəllim kafedrasının əhatə qapısı.

Sahib 2026-11-04: «bu yeni user yaradanda kafedra adları select option kimi gəlsin, search etmək də olsun».
Əvvəl sahə type-ahead mətn qutusu idi (adı yazmaq lazım idi, siyahı görünmürdü). Kafedra/bölmə sayı
qrupdan (700+) çox azdır, ona görə siyahı bölmə render-ində layihənin axtarışlı seçicisinə
(``data-bootstrap-select`` + ``data-live-search``) yazılır; hər variant hansı hesab növündə
(müəllim / əməkdaş) göstərildiyini daşıyır — JS növ dəyişəndə uyğun olmayanları gizlədir.

QAPILAR (server həmişə yenidən yoxlayır, siyahı yalnız UI-dır):

* müəllim — aktiv, kafedra tipli vahid, ``user.import_staff`` ƏHATƏSİNDƏ (``teacher_units``). 2026-11-04-ə
  qədər müəllim formu yalnız «kafedra tipli + aktiv» yoxlayırdı — kafedraya bağlı yaradıcı başqa kafedranı
  yaza bilirdi; indi əməkdaş formu ilə eyni əhatə qaydası;
* əməkdaş — ``create_staff.staff_units`` (təyin + idxal əhatəsinin kəsişməsi); seçicidə akademik «yarpaq»
  vahidlər (qrup / ixtisas / sinif) göstərilmir — vəzifə əhatəsi deyillər və siyahını yararsız edərdi.
"""

from __future__ import annotations

from core.constants import OrgUnitType

from ..intake.create import KIND_STAFF, KIND_TEACHER
from .create_staff import staff_units

#: Əməkdaş seçicisinə düşməyən vahid tipləri.
STAFF_PICKER_EXCLUDED_TYPES = (
    OrgUnitType.GROUP,
    OrgUnitType.SPECIALTY,
    OrgUnitType.CLASS,
    OrgUnitType.PARALLEL,
    OrgUnitType.GRADE_LEVEL,
)


def teacher_units(actor):
    """Müəllim hesabına yazıla bilən kafedralar (fail-closed: əhatə yoxdursa — boş)."""
    from apps.organizations.models import OrgUnit
    from apps.organizations.public import get_permission_scope, kafedra_unit_types

    organization = getattr(actor, "organization", None)
    if organization is None or getattr(actor, "user", None) is None:
        return OrgUnit.objects.none()
    queryset = OrgUnit.objects.filter(
        organization=organization,
        is_active=True,
        unit_type__in=kafedra_unit_types(organization),
    )
    scope = get_permission_scope(actor.user, organization, "user.import_staff")
    if scope.is_org_wide:
        return queryset
    if not scope.has_structure_access:
        return queryset.none()
    return queryset.filter(scope.unit_subtree_q())


def teacher_unit_allowed(actor, unit) -> bool:
    return unit is not None and teacher_units(actor).filter(pk=unit.pk).exists()


def unit_picker_options(actor, kinds) -> list[dict]:
    """``[{"id", "name", "parent", "code", "kinds"}]`` — seçicinin variantları (ada görə sıralı).

    ``kinds`` — aktorun yarada bildiyi hesab növləri; hər növ üçün BİR sorğu (valideyn adı ``select_related``).
    """
    sources = []
    if KIND_TEACHER in kinds:
        sources.append((KIND_TEACHER, teacher_units(actor)))
    if KIND_STAFF in kinds:
        sources.append((KIND_STAFF, staff_units(actor).exclude(unit_type__in=STAFF_PICKER_EXCLUDED_TYPES)))
    options: dict = {}
    for kind, queryset in sources:
        units = queryset.select_related("parent").only("id", "name", "code", "parent_id", "parent__name")
        for unit in units:
            item = options.setdefault(
                str(unit.pk),
                {
                    "id": str(unit.pk),
                    "name": unit.name,
                    "parent": unit.parent.name if unit.parent_id else "",
                    "code": unit.code or "",
                    "kinds": [],
                },
            )
            item["kinds"].append(kind)
    for item in options.values():
        item["kinds"] = " ".join(item["kinds"])
    return sorted(options.values(), key=lambda item: (item["name"].casefold(), item["parent"].casefold()))


__all__ = ["STAFF_PICKER_EXCLUDED_TYPES", "teacher_unit_allowed", "teacher_units", "unit_picker_options"]
