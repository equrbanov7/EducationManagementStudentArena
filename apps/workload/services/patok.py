"""Patok mühazirəsi — ikinci (üçüncü …) qrupun sətrində də görünsün (sahib 2026-11-07).

Sahib: «2 qrup birlikdə göstərilib 30 saat mühazirə yazılıbsa, hər 2 qrupda 30 saat mühazirə görünsün … patok
dərsidirsə 2-ci qrupun mühazirəsi 0 olmamalıdır, 3 qrupda olsa da 0 olmamalıdır, çünki eyni vaxtda keçirilib».

Yükdə patok qrup başına AYRI sətirdədirsə (seminar planları fərqlidir — sətirləri birləşdirmək olmur) mühazirə
saatı YALNIZ bir sətirdə yazılır, qalanlarında ``lecture_total = 0`` (müəllimin yükü ikiqat sayılmasın —
``fix_workload_overcount`` qaydası), ``lecture_plan`` isə qrupun saatı kimi qalır. Bu modul həmin «patok tərəfdaşı»
sətrinin mühazirəsini aparıcı sətirdən TANIYIR — heç nə yazmır, yükə saat əlavə etmir:

* tərəfdaş — tədris sətri, ``lecture_plan > 0`` və ``lecture_total = 0``;
* aparıcı — eyni tapşırıq + fənn + mövsüm/dövr, ``lecture_total > 0`` və müəllimli mühazirə bölgüsü olan sətir;
* mühazirəçi: aparıcıların müəllimlərindən tərəfdaş sətirdə də bölgüsü olan TƏK müəllim; belə yoxdursa bütün
  aparıcılarda TƏK müəllim; əks halda müəyyən deyil (``teacher_id`` boş — ad uydurulmur).
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Prefetch, Q

from ..constants import Activity, RowKind
from ..models import TeacherAssignment, TeachingTaskRow


def is_partner(row) -> bool:
    return row.row_kind == RowKind.TEACHING and int(row.lecture_plan or 0) > 0 and int(row.lecture_total or 0) == 0


def partner_q(prefix: str = "") -> Q:
    """Patok tərəfdaşı sətirlərin ``Q``-su (``prefix`` — sorğu modelindən sətrə gedən yol)."""
    return Q(**{f"{prefix}row_kind": RowKind.TEACHING, f"{prefix}lecture_plan__gt": 0, f"{prefix}lecture_total": 0})


def _key(row) -> tuple:
    return (row.task_id, row.subject_id, row.season, row.period_id)


def _leads(partners) -> dict:
    """``{açar: [aparıcı sətir …]}`` — TƏK sorğu (+ mühazirə bölgüləri prefetch)."""
    keys = {_key(row) for row in partners if row.subject_id}
    if not keys:
        return {}
    lectures = TeacherAssignment.objects.filter(activity=Activity.LECTURE, teacher__isnull=False, hours__gt=0)
    rows = (
        TeachingTaskRow.objects.filter(
            task_id__in={key[0] for key in keys},
            subject_id__in={key[1] for key in keys},
            row_kind=RowKind.TEACHING,
            lecture_total__gt=0,
        )
        .prefetch_related(
            "groups", Prefetch("assignments", queryset=lectures.select_related("teacher"), to_attr="patok_lectures")
        )
        .order_by("order", "created_at", "pk")
    )
    found = defaultdict(list)
    for row in rows:
        if _key(row) in keys and row.patok_lectures:
            found[_key(row)].append(row)
    return found


def _teacher(partner, leads, assigned_ids):
    lecturers = {}
    for lead in leads:
        for assignment in lead.patok_lectures:
            lecturers.setdefault(assignment.teacher_id, (assignment.teacher, lead))
    local = [teacher_id for teacher_id in lecturers if teacher_id in assigned_ids]
    if len(local) == 1:
        return lecturers[local[0]]
    if len(lecturers) == 1:
        return next(iter(lecturers.values()))
    return None, None


def partner_lectures(rows) -> dict:
    """``{sətir pk: {"hours", "teacher_id", "teacher_name", "groups"}}`` — verilmiş sətirlərdən tərəfdaş olanlar.

    ``rows``-un ``assignments`` prefetch-i varsa əlavə sorğu yoxdur; aparıcılar üçün BİR sorğu.
    """
    partners = [row for row in rows if is_partner(row)]
    if not partners:
        return {}
    leads = _leads(partners)
    result = {}
    for row in partners:
        assigned = {a.teacher_id for a in row.assignments.all() if a.teacher_id}
        teacher, lead = _teacher(row, leads.get(_key(row), ()), assigned)
        result[row.pk] = {
            "hours": int(row.lecture_plan),
            "teacher_id": str(teacher.pk) if teacher is not None else "",
            "teacher_name": (teacher.get_full_name() or teacher.username) if teacher is not None else "",
            "groups": " / ".join(group.name for group in lead.groups.all()) if lead is not None else "",
        }
    return result


def teacher_partner_rows(*, organization, teacher_id, released_q) -> list:
    """Müəllimin MÜHAZİRƏSİNİ apardığı patok tərəfdaşı sətirləri (onun öz bölgüsü olmasa da)."""
    lead_keys = set(
        TeachingTaskRow.objects.filter(
            organization=organization,
            row_kind=RowKind.TEACHING,
            lecture_total__gt=0,
            assignments__teacher_id=teacher_id,
            assignments__activity=Activity.LECTURE,
            assignments__hours__gt=0,
        )
        .filter(released_q)
        .values_list("task_id", "subject_id", "season", "period_id")
        .distinct()
    )
    if not lead_keys:
        return []
    candidates = list(
        TeachingTaskRow.objects.filter(
            partner_q(),
            organization=organization,
            task_id__in={key[0] for key in lead_keys},
            subject_id__in={key[1] for key in lead_keys},
        )
        .filter(released_q)
        .prefetch_related("groups", "assignments")
    )
    candidates = [row for row in candidates if _key(row) in lead_keys]
    lectures = partner_lectures(candidates)
    return [row for row in candidates if lectures.get(row.pk, {}).get("teacher_id") == str(teacher_id)]


__all__ = ["is_partner", "partner_lectures", "partner_q", "teacher_partner_rows"]
