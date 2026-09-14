"""results paketi — nəticələr səhifəsinin «Qrup» seçimləri (kohort + reyestr qrupu).

2026-09-14 (W5 `w5left`, tapşırıq 1; W4 hesabatı «qalanlar» 2). Müəllim
nəticələrində qrup filtri və «qrupa ikinci şans» seçicisi yalnız köhnə kohortu
(`StudentGroup`, int id) tanıyırdı — reyestr qrupuna (`Exam.allowed_units`,
`OrgUnit` GROUP, UUID) təyin olunmuş imtahanda seçici boş qalırdı.

İki mənbə TƏK siyahıda birləşir; seçicidə dəyər kohort üçün `"<int>"`,
reyestr qrupu üçün `"unit:<uuid>"`-dur (`unit_scope_filters.unit_filter_value`),
ona görə şablon və URL parametri dəyişmir. Tələbənin reyestr qrupuna
mənsubluğu `unit_assignment` ilə eyni şərtdən (cari aktiv `enrolled` qeyd)
oxunur.
"""

from dataclasses import dataclass

from django.db.models import Q

from apps.exams.domain.unit_assignment import unit_student_record_filter
from apps.exams.domain.unit_scope_filters import parse_unit_value, unit_filter_value
from apps.exams.models import StudentGroup
from apps.organizations.models import OrgUnit
from core.constants import OrgUnitType

KIND_COHORT = "cohort"
KIND_UNIT = "unit"


@dataclass(frozen=True)
class GroupOption:
    """Şablonun gözlədiyi `id` / `name` cütü + mənbə növü."""

    id: str
    name: str
    kind: str
    pk: object

    @property
    def is_unit(self) -> bool:
        return self.kind == KIND_UNIT


def _cohort_queryset(exam, attempt_user_ids):
    qs = StudentGroup.objects.filter(Q(exams=exam) | Q(students__id__in=attempt_user_ids))
    org_id = getattr(exam, "organization_id", None)
    if org_id:
        qs = qs.filter(organization_id=org_id)
    return qs.distinct().order_by("name")


def _unit_queryset(exam, attempt_user_ids):
    """İmtahana təyin olunmuş reyestr qrupları + cəhd edən tələbələrin cari qrupları."""
    record_path = "student_records__"
    qs = OrgUnit.objects.filter(unit_type=OrgUnitType.GROUP).filter(
        Q(assigned_exams=exam)
        | Q(**{f"{record_path}student_id__in": attempt_user_ids}, **unit_student_record_filter(record_path))
    )
    org_id = getattr(exam, "organization_id", None)
    if org_id:
        qs = qs.filter(organization_id=org_id)
    return qs.distinct().order_by("name")


def available_group_options(exam) -> list[GroupOption]:
    """Kohortlar + reyestr qrupları, ada görə sıralı (tenant-scoped, 2 sorğu)."""
    attempt_user_ids = exam.attempts.values_list("user_id", flat=True)
    options = [
        GroupOption(id=str(group.id), name=group.name, kind=KIND_COHORT, pk=group.id)
        for group in _cohort_queryset(exam, attempt_user_ids)
    ]
    options += [
        GroupOption(id=unit_filter_value(unit.pk), name=unit.name, kind=KIND_UNIT, pk=unit.pk)
        for unit in _unit_queryset(exam, attempt_user_ids)
    ]
    return sorted(options, key=lambda option: (option.name.casefold(), option.kind))


def normalize_group_value(raw) -> str:
    """GET/POST dəyəri → seçici dəyəri (`"<int>"` / `"unit:<uuid>"`); tanınmayan → ""."""
    value = str(raw or "").strip()
    if not value or value.lower() == "all":
        return ""
    if value.isdigit():
        return str(int(value))
    unit_id = parse_unit_value(value)
    return unit_filter_value(unit_id) if unit_id else ""


def resolve_group_option(exam, raw) -> GroupOption | None:
    """Yalnız bu imtahanın seçim siyahısındakı dəyər qəbul olunur (yad id → None)."""
    value = normalize_group_value(raw)
    if not value:
        return None
    return next((option for option in available_group_options(exam) if option.id == value), None)


def attempts_in_group_q(option: GroupOption, *, prefix: str = "user__") -> Q:
    """Cəhd/istifadəçi queryset-i üçün «bu qrupun üzvüdür» şərti."""
    if option.is_unit:
        record_path = f"{prefix}academic_records__"
        return Q(**{f"{record_path}group_id": option.pk}, **unit_student_record_filter(record_path))
    return Q(**{f"{prefix}student_groups_as_student__id": option.pk})


def group_names_by_user(options: list[GroupOption], user_ids) -> dict[int, list[str]]:
    """Export üçün: istifadəçi → üzv olduğu qrup adları (kohort + reyestr; 2 sorğu)."""
    user_ids = set(user_ids)
    names: dict[int, list[str]] = {}
    if not options or not user_ids:
        return names
    cohort_pks = [option.pk for option in options if not option.is_unit]
    unit_pks = [option.pk for option in options if option.is_unit]
    if cohort_pks:
        for user_id, name in (
            StudentGroup.objects.filter(id__in=cohort_pks, students__id__in=user_ids)
            .values_list("students__id", "name")
            .order_by("name")
        ):
            names.setdefault(user_id, []).append(name)
    if unit_pks:
        record_path = "student_records__"
        for user_id, name in (
            OrgUnit.objects.filter(pk__in=unit_pks)
            .filter(**{f"{record_path}student_id__in": user_ids}, **unit_student_record_filter(record_path))
            .values_list(f"{record_path}student_id", "name")
            .order_by("name")
        ):
            names.setdefault(user_id, []).append(name)
    for user_id in names:
        names[user_id] = sorted(set(names[user_id]), key=str.casefold)
    return names


__all__ = [
    "GroupOption",
    "KIND_COHORT",
    "KIND_UNIT",
    "attempts_in_group_q",
    "available_group_options",
    "group_names_by_user",
    "normalize_group_value",
    "resolve_group_option",
]
