"""`ExamForm` — «istisna edilən tələbələr» (`excluded_users`) süzgəci.

2026-09-14 (W5 `w5left`, tapşırıq 2; W4 hesabatı «qalanlar» 3). Forma
`excluded_users`-i yalnız kohort (`allowed_groups`) üzvləri ilə süzürdü:
reyestr qrupu (`allowed_units`, OrgUnit GROUP) ilə təyinatda sehrbazda
«unchecked» edilmiş tələbə istisna siyahısına DÜŞMÜRDÜ — imtahan ona yenə
açıq qalırdı. İcazəli çoxluq indi kohort üzvləri ∪ reyestr qrupu tələbələri
(`unit_assignment` ilə eyni şərt: cari aktiv `enrolled` qeyd, tenant-scoped).

Reyestr qrupu forma sahəsi deyil (W4 qərarı — view qatında yoxlanıb yazılır);
burada yalnız göndərilmiş id-lər (+ redaktədə imtahanın mövcud qrupları)
oxunur ki, əhatədən kənar qrupun tələbəsi redaktədə istisnadan çıxmasın.
"""

from django.db.models import Q

from apps.exams.domain.unit_assignment import unit_student_record_filter
from apps.exams.domain.unit_scope_filters import parse_unit_value
from core.constants import OrgUnitType

#: Sehrbazın POST-da göndərdiyi reyestr qrupu sahəsi (`views…unit_assignment.UNITS_FIELD_NAME`).
UNITS_FIELD_NAME = "allowed_units"


def requested_unit_ids(data) -> list[str]:
    """Bağlı formanın datasından reyestr qrupu UUID-ləri (zibil atılır, təkrarsız)."""
    if hasattr(data, "getlist"):
        raw_values = data.getlist(UNITS_FIELD_NAME)
    else:  # adi dict (testlər / proqramatik çağırış): list və ya tək dəyər
        raw_values = (data or {}).get(UNITS_FIELD_NAME) or []
        if isinstance(raw_values, str):
            raw_values = [raw_values]
    ids: list[str] = []
    for raw in raw_values:
        for piece in str(raw or "").split(","):
            unit_id = parse_unit_value(piece)
            if unit_id and unit_id not in ids:
                ids.append(unit_id)
    return ids


def excluded_users_within_assignment(excluded_users, *, allowed_groups, unit_ids, organization, instance=None):
    """`excluded_users`-i təyin olunmuş kohort/reyestr qrupu tələbələri ilə məhdudlaşdırır."""
    from apps.organizations.models import OrgUnit

    condition = Q()
    if allowed_groups:
        condition |= Q(student_groups_as_student__in=allowed_groups)

    unit_qs = OrgUnit.objects.none()
    unit_condition = Q()
    if unit_ids:
        unit_condition |= Q(pk__in=unit_ids)
    if instance is not None and getattr(instance, "pk", None):
        unit_condition |= Q(assigned_exams=instance)
    if unit_condition:
        unit_qs = OrgUnit.objects.filter(unit_type=OrgUnitType.GROUP).filter(unit_condition)
        if organization is not None:
            unit_qs = unit_qs.filter(organization=organization)
        record_path = "academic_records__"
        condition |= Q(
            **{f"{record_path}group__in": unit_qs.values("pk")},
            **unit_student_record_filter(record_path),
        )

    if not condition:
        return excluded_users.none()
    return excluded_users.filter(condition).distinct()


__all__ = ["UNITS_FIELD_NAME", "excluded_users_within_assignment", "requested_unit_ids"]
