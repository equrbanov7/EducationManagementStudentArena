"""Reyestr qrupu (`OrgUnit` GROUP) üzrə statistika / nəticə filtrləri — paylaşılan parçalar.

2026-09-14 (W5 `w5left`, tapşırıq 1; W4 hesabatı «Orkestrator üçün qalanlar» 2).
`Exam.allowed_units` gələndən sonra imtahan mərkəzi statistikası, apellyasiya
statistikası, «yenidən şans» bölməsi və müəllim nəticələri qrup/fakültə/kafedra
filtrlərini HƏLƏ yalnız köhnə kohortun (`StudentGroup.org_unit`) üzərindən
qururdu — reyestr qrupuna təyin olunmuş imtahan bu filtrlərdə görünmürdü.

Buradakı köməkçilər `Q` parçası qaytarır ki, çağıran onları mövcud kohort
şərti ilə `|` ilə birləşdirsin (`Q(kohort) | Q(reyestr)`) və sorğu sayı
seçilmiş filtr sayından asılı olmayaraq sabit qalsın:

* `split_group_filter_values` — `groups=` CSV-də kohort int id-ləri ilə reyestr
  UUID-lərini ayırır (`unit:<uuid>` prefiksi də qəbul olunur);
* `descendant_unit_pks` — verilmiş vahidlər + bütün alt-ağac (materialized
  `path` prefiksi): fakültə seçiləndə onun altındakı qruplar da düşür
  (Fakültə → Kafedra → İxtisas → Qrup). 1 sorğu (path-lar) + subquery;
* `allowed_units_prefetch` / `unit_ancestor_name` — cədvəl sətrində «qrup /
  kafedra / fakültə» sütunları üçün valideyn zənciri select_related ilə
  gəlir (sətir başına əlavə sorğu yoxdur).
"""

from uuid import UUID

from django.db.models import Prefetch, Q

from core.constants import OrgUnitType

#: `groups=` parametrində reyestr qrupu dəyərinin ixtiyari prefiksi.
UNIT_VALUE_PREFIX = "unit:"

#: Sətir sütunları üçün yüklənən valideyn zəncirinin dərinliyi
#: (Qrup → İxtisas → Kafedra → Fakültə = 3 addım). Daha dərinə getmək
#: sətir başına sorğu yaradardı, ona görə gəzinti bu dərinlikdə dayanır.
UNIT_ANCESTOR_DEPTH = 3

FACULTY_UNIT_TYPES = (OrgUnitType.FACULTY, OrgUnitType.DEANERY)
KAFEDRA_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)


def _as_uuid(value: str) -> str | None:
    try:
        return str(UUID(value))
    except (TypeError, ValueError):
        return None


def parse_unit_value(raw) -> str | None:
    """`unit:<uuid>` və ya çılpaq UUID → normallaşdırılmış UUID mətni; əks halda None."""
    value = str(raw or "").strip()
    if value.lower().startswith(UNIT_VALUE_PREFIX):
        value = value[len(UNIT_VALUE_PREFIX) :]
    return _as_uuid(value)


def unit_filter_value(unit_pk) -> str:
    """Seçicidə reyestr qrupunun dəyəri (`unit:<uuid>`) — kohort int id-ləri ilə qarışmır."""
    return f"{UNIT_VALUE_PREFIX}{unit_pk}"


def split_group_filter_values(raw) -> tuple[list[int], list[str]]:
    """`groups=` CSV → `(kohort_int_idləri, reyestr_uuidləri)`; zibil atılır."""
    cohort_ids: list[int] = []
    unit_ids: list[str] = []
    for piece in (raw or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        if piece.isdigit():
            cohort_ids.append(int(piece))
            continue
        unit_id = parse_unit_value(piece)
        if unit_id and unit_id not in unit_ids:
            unit_ids.append(unit_id)
    return cohort_ids, unit_ids


def descendant_unit_pks(organization, ancestor_ids):
    """Verilmiş vahidlər + alt-ağacları (`path` prefiksi) — `pk` subquery-si.

    Yalnız təşkilatın öz vahidləri; başqa tenantın id-si heç nəyə uyğun gəlmir.
    """
    from apps.organizations.models import OrgUnit

    ids = [value for value in (str(v) for v in ancestor_ids) if _as_uuid(value)]
    if not ids:
        return OrgUnit.objects.none().values("pk")
    paths = list(OrgUnit.objects.filter(organization=organization, pk__in=ids).values_list("path", flat=True))
    condition = Q(pk__in=ids)
    for path in paths:
        if path:
            condition |= Q(path__startswith=f"{path}/")
    return OrgUnit.objects.filter(organization=organization).filter(condition).values("pk")


def allowed_units_q(unit_ids, *, prefix: str = "exam__") -> Q:
    """İmtahan bilavasitə bu reyestr qruplarına təyin olunub (`groups=` filtri)."""
    return Q(**{f"{prefix}allowed_units__id__in": list(unit_ids)})


def allowed_units_under_q(organization, ancestor_ids, *, prefix: str = "exam__") -> Q:
    """İmtahanın reyestr qrupu verilmiş fakültə/kafedra/vahidin alt-ağacındadır."""
    return Q(**{f"{prefix}allowed_units__in": descendant_unit_pks(organization, ancestor_ids)})


def allowed_units_prefetch(*, prefix: str = "exam__") -> Prefetch:
    """Sətir sütunları üçün `allowed_units` + valideyn zənciri (UNIT_ANCESTOR_DEPTH)."""
    from apps.organizations.models import OrgUnit

    chain = "__".join(["parent"] * UNIT_ANCESTOR_DEPTH)
    return Prefetch(f"{prefix}allowed_units", queryset=OrgUnit.objects.select_related(chain).order_by("name"))


def unit_ancestor_name(unit, unit_types) -> str:
    """Prefetch olunmuş zəncirdə ilk uyğun tipli valideynin adı (yoxdursa "")."""
    node = unit
    for _ in range(UNIT_ANCESTOR_DEPTH):
        if getattr(node, "parent_id", None) is None:
            return ""
        node = node.parent
        if node is None:
            return ""
        if node.unit_type in unit_types:
            return node.name or ""
    return ""


def unit_row_labels(units) -> dict[str, list[str]]:
    """Cədvəl sətri üçün `{"groups": [...], "kafedras": [...], "faculties": [...]}` (təkrarsız, sıra ilə)."""
    groups: list[str] = []
    kafedras: list[str] = []
    faculties: list[str] = []
    for unit in units:
        _append_unique(groups, unit.name)
        _append_unique(kafedras, unit_ancestor_name(unit, KAFEDRA_UNIT_TYPES))
        _append_unique(faculties, unit_ancestor_name(unit, FACULTY_UNIT_TYPES))
    return {"groups": groups, "kafedras": kafedras, "faculties": faculties}


def _append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


__all__ = [
    "FACULTY_UNIT_TYPES",
    "KAFEDRA_UNIT_TYPES",
    "UNIT_ANCESTOR_DEPTH",
    "UNIT_VALUE_PREFIX",
    "allowed_units_prefetch",
    "allowed_units_q",
    "allowed_units_under_q",
    "descendant_unit_pks",
    "parse_unit_value",
    "split_group_filter_values",
    "unit_ancestor_name",
    "unit_filter_value",
    "unit_row_labels",
]
