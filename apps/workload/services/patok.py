"""Patok mühazirəsi — ikinci (üçüncü …) qrupun sətrində də görünsün (sahib 2026-11-07).

Sahib: «2 qrup birlikdə göstərilib 30 saat mühazirə yazılıbsa, hər 2 qrupda 30 saat mühazirə görünsün … patok
dərsidirsə 2-ci qrupun mühazirəsi 0 olmamalıdır, 3 qrupda olsa da 0 olmamalıdır, çünki eyni vaxtda keçirilib».

Yükdə patok qrup başına AYRI sətirdədirsə (seminar planları fərqlidir — sətirləri birləşdirmək olmur) mühazirə
saatı YALNIZ bir sətirdə yazılır, qalanlarında ``lecture_total = 0`` (müəllimin yükü ikiqat sayılmasın —
``fix_workload_overcount`` qaydası), ``lecture_plan`` isə qrupun saatı kimi qalır. Bu modul həmin «patok tərəfdaşı»
sətrinin mühazirəsini aparıcı sətirdən TANIYIR — yükə saat əlavə etmir:

* tərəfdaş — tədris sətri, ``lecture_plan > 0`` və ``lecture_total = 0``;
* aparıcı — ƏVVƏLCƏ açıq bağ ``patok_lead`` (sahib 2026-11-08: eyni fənndə iki mühazirəçi — 536 MRK Həbibov,
  536 MU/ML/İ Balayev — evristikanı çaşdırırdı); bağ boşdursa və ya artıq etibarlı deyilsə evristika: eyni
  tapşırıq + fənn + mövsüm/dövr, ``lecture_total > 0`` və müəllimli mühazirə bölgüsü olan sətir;
* mühazirəçi: aparıcı(lar)ın MÜHAZİRƏ bölgüsünün müəllimlərindən tərəfdaş sətirdə də bölgüsü olan TƏK müəllim;
  belə yoxdursa bütün aparıcılarda TƏK müəllim; əks halda müəyyən deyil (``teacher_id`` boş — ad uydurulmur).
  Tərəfdaş sətrin seminar/lab müəllimi heç vaxt mühazirəçi sayılmır (yalnız aparıcının ``lecture`` bölgüsü).

Bağın yazılması (``apply_patok_lead``) yalnız ``save_row`` / ``link_patok_leads_20261108`` yolu ilədir.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from django.db.models import Prefetch, Q

from ..constants import Activity, RowKind
from ..models import TeacherAssignment, TeachingTaskRow
from .scoping import WorkloadDenied

#: Bağ rədd kodları → mesaj (``workload.*`` — UI kodla, mesaj yalnız göstəriş üçündür).
LEAD_ERRORS = {
    "workload.patok_lead_not_found": "Patokun aparıcı sətri tapılmadı.",
    "workload.patok_lead_self": "Sətir özünün aparıcısı ola bilməz.",
    "workload.patok_not_partner": "Bu sətir patok tərəfdaşı deyil: mühazirə planı olmalı, mühazirə cəmi 0 olmalıdır.",
    "workload.patok_lead_mismatch": "Aparıcı sətir eyni tapşırıq, fənn, mövsüm və semestrdə olmalıdır.",
    "workload.patok_lead_no_lecture": "Aparıcı sətirdə mühazirə saatı yoxdur.",
    "workload.patok_lead_is_partner": "Aparıcı sətrin özü başqa sətrə bağlıdır (patok tərəfdaşıdır).",
    "workload.patok_row_is_lead": "Bu sətrə başqa patok sətirləri bağlıdır — əvvəl onların bağını açın.",
}


def is_partner(row) -> bool:
    return row.row_kind == RowKind.TEACHING and int(row.lecture_plan or 0) > 0 and int(row.lecture_total or 0) == 0


def partner_q(prefix: str = "") -> Q:
    """Patok tərəfdaşı sətirlərin ``Q``-su (``prefix`` — sorğu modelindən sətrə gedən yol)."""
    return Q(**{f"{prefix}row_kind": RowKind.TEACHING, f"{prefix}lecture_plan__gt": 0, f"{prefix}lecture_total": 0})


def _key(row) -> tuple:
    return (row.task_id, row.subject_id, row.season, row.period_id)


def lead_problem(row, lead) -> str:
    """Boş sətir — ``lead`` ``row``-un etibarlı aparıcısıdır; əks halda rədd kodu (``LEAD_ERRORS``).

    Aparıcının özü tərəfdaş ola bilməz (bağı yoxdur, mühazirə cəmi > 0) — zəncir və dövr struktur olaraq yoxdur.
    """
    if lead is None:
        return "workload.patok_lead_not_found"
    if lead.pk == row.pk:
        return "workload.patok_lead_self"
    if not is_partner(row):
        return "workload.patok_not_partner"
    if not row.subject_id or _key(lead) != _key(row):
        return "workload.patok_lead_mismatch"
    if lead.row_kind != RowKind.TEACHING or int(lead.lecture_total or 0) <= 0:
        return "workload.patok_lead_no_lecture"
    if lead.patok_lead_id is not None:
        return "workload.patok_lead_is_partner"
    return ""


def _parse(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def apply_patok_lead(row, data) -> None:
    """``row.patok_lead``-i ``data["patok_lead_id"]``-dən qurur (yaddaşa yazmır — ``row.save()`` çağıranındır).

    Açar göndərilməyibsə bağ qalır; yalnız sətir artıq tərəfdaş deyilsə (mühazirə cəmi yazılıb) köhnə bağ silinir.
    Boş dəyər — bağı açır. Yanlış aparıcı → ``WorkloadDenied`` (``LEAD_ERRORS``).
    """
    if "patok_lead_id" not in data:
        if row.patok_lead_id and not is_partner(row):
            row.patok_lead = None
        return
    raw = data.get("patok_lead_id") or ""
    if not raw:
        row.patok_lead = None
        return
    pk = _parse(raw)
    lead = (
        TeachingTaskRow.objects.filter(organization_id=row.organization_id, pk=pk).first() if pk is not None else None
    )
    problem = lead_problem(row, lead)
    if not problem and not row._state.adding and TeachingTaskRow.objects.filter(patok_lead_id=row.pk).exists():
        problem = "workload.patok_row_is_lead"
    if problem:
        raise WorkloadDenied(problem, LEAD_ERRORS[problem])
    row.patok_lead = lead


def _candidates(partners) -> tuple[dict, dict]:
    """``({pk: açıq bağlı aparıcı}, {açar: [evristik aparıcı …]})`` — TƏK sorğu (+ qruplar, mühazirə bölgüləri)."""
    keys = {_key(row) for row in partners if row.subject_id}
    linked = {row.patok_lead_id for row in partners if row.patok_lead_id}
    if not keys and not linked:
        return {}, {}
    condition = Q(pk__in=linked)
    if keys:
        condition |= Q(
            task_id__in={key[0] for key in keys},
            subject_id__in={key[1] for key in keys},
            row_kind=RowKind.TEACHING,
            lecture_total__gt=0,
        )
    lectures = TeacherAssignment.objects.filter(activity=Activity.LECTURE, teacher__isnull=False, hours__gt=0)
    rows = (
        TeachingTaskRow.objects.filter(condition)
        .prefetch_related(
            "groups", Prefetch("assignments", queryset=lectures.select_related("teacher"), to_attr="patok_lectures")
        )
        .order_by("order", "created_at", "pk")
    )
    by_pk, found = {}, defaultdict(list)
    for row in rows:
        by_pk[row.pk] = row
        heuristic = row.row_kind == RowKind.TEACHING and int(row.lecture_total or 0) > 0
        if heuristic and _key(row) in keys and row.patok_lectures:
            found[_key(row)].append(row)
    return by_pk, found


def _teacher(leads, assigned_ids):
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


def partner_lectures(rows, *, assigned=None) -> dict:
    """``{sətir pk: {"hours", "teacher_id", "teacher_name", "groups", "lead_id", "linked"}}`` — tərəfdaşlar.

    ``assigned(row)`` — sətirdə bölgüsü olan müəllim id-ləri (defolt: ``row.assignments`` prefetch-i). ``linked`` —
    aparıcı açıq bağdandır (``patok_lead``), evristikadan deyil. Tərəfdaş yoxdursa sorğu yoxdur; varsa BİR sorğu.
    """
    partners = [row for row in rows if is_partner(row)]
    if not partners:
        return {}
    if assigned is None:

        def assigned(row):
            return {a.teacher_id for a in row.assignments.all() if a.teacher_id}

    by_pk, found = _candidates(partners)
    result = {}
    for row in partners:
        lead = by_pk.get(row.patok_lead_id) if row.patok_lead_id else None
        linked = lead is not None and not lead_problem(row, lead)
        if linked:
            teacher, _lead = _teacher([lead], assigned(row))
        else:
            teacher, lead = _teacher(found.get(_key(row), ()), assigned(row))
        result[row.pk] = {
            "hours": int(row.lecture_plan),
            "teacher_id": str(teacher.pk) if teacher is not None else "",
            "teacher_name": (teacher.get_full_name() or teacher.username) if teacher is not None else "",
            "groups": " / ".join(group.name for group in lead.groups.all()) if lead is not None else "",
            "lead_id": str(lead.pk) if lead is not None else "",
            "linked": linked,
        }
    return result


def taught_partner_rows(rows, teacher_id, *, owns=None) -> list:
    """``rows`` içində mühazirəsini BU müəllimin apardığı patok tərəfdaşları.

    ``owns(row)`` — müəllimin həmin sətirdə öz bölgüsü varmı (defolt: hamısında). Öz bölgüsü olmayan tərəfdaş
    yalnız AÇIQ bağla (``patok_lead`` → bu müəllimin mühazirə apardığı sətir) sayılır: evristika ilə tapılan
    mühazirəçi o jurnalın sahibi deyil (sorğu büdcəsi: tərəfdaş yoxdursa əlavə sorğu yoxdur).
    """
    if owns is None:

        def owns(row):
            return True

    lectures = partner_lectures(rows, assigned=lambda row: {teacher_id} if owns(row) else set())
    taught = []
    for row in rows:
        info = lectures.get(row.pk)
        if info and info["teacher_id"] == str(teacher_id) and (info["linked"] or owns(row)):
            taught.append(row)
    return taught


def lectured_partner_ids(queryset, teacher_id) -> set:
    """``queryset`` sətirlərindən mühazirəsini ``teacher_id``-nin apardığı tərəfdaşların pk-ları (kart xətti ilə eyni)."""
    partners = list(queryset.filter(partner_q()).prefetch_related("assignments"))
    found = partner_lectures(partners)
    return {pk for pk, info in found.items() if info["teacher_id"] == str(teacher_id)}


__all__ = [
    "LEAD_ERRORS",
    "apply_patok_lead",
    "is_partner",
    "lead_problem",
    "lectured_partner_ids",
    "partner_lectures",
    "partner_q",
    "taught_partner_rows",
]
