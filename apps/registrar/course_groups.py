"""Kurs (LMS) üçün qrup mənbəyi — müəllimin reyestr qrupları və onların tələbələri.

NİYƏ (2026-09-28): «Kurslarım» panelindəki «Qrup əlavə et» köhnə
``exams.StudentGroup`` cədvəlini oxuyurdu. Həmin model köhnəlib (bax
``apps/exams/domain/access_policy.py``) və real bazada BOŞDUR — müəllim modalda
heç vaxt qrup görmürdü. Həqiqi qruplar ``organizations.OrgUnit(unit_type=group)``
-dur; müəllim onlara ``CourseOffering.instructor`` (və ya dərs səviyyəsində
``Lesson.instructor``) ilə bağlanır, tələbə isə ``StudentAcademicRecord.group``
ilə qrupa aiddir.

Tələbə siyahısı iki mənbənin BİRLƏŞMƏSİDİR:
* qrupun aktiv+enrolled akademik qeydləri;
* müəllimin həmin qrupdakı açılışlarının aktiv qeydiyyatları (``Enrollment``) —
  birləşik qrupların («234 K az») öz qeydi olmur, tələbələri alt qruplardan
  qonaq kimi gəlir (bax ``subgroup_rollup``).

Bu modul yalnız OXUYUR; kurs üzvlüyünü ``apps.courses`` yazır.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from django.db.models import Count, Q

from apps.registrar.dashboard_data import current_period
from apps.registrar.models import AcademicStatus, CourseOffering, Enrollment, Lesson, StudentAcademicRecord
from core.constants import OrgUnitType
from core.search_text import tolerant_q

#: Axtarış nəticəsinin tavanı — seçici siyahısı uzanmasın.
SEARCH_LIMIT = 30


def _group_model():
    from django.apps import apps as django_apps

    return django_apps.get_model("organizations", "OrgUnit")


def _taught_offerings(organization, teacher, period):
    lesson_offerings = Lesson.objects.filter(instructor=teacher).values("offering_id")
    return CourseOffering.objects.filter(
        organization=organization,
        period=period,
        is_active=True,
        group__isnull=False,
    ).filter(Q(instructor=teacher) | Q(pk__in=lesson_offerings))


def _record_students(organization, group_ids):
    """``{group_id: {student_id, ...}}`` — aktiv+enrolled akademik qeydlər, BİR sorğu."""
    out = defaultdict(set)
    if not group_ids:
        return out
    rows = StudentAcademicRecord.objects.filter(
        organization=organization,
        group_id__in=list(group_ids),
        is_active=True,
        status=AcademicStatus.ENROLLED,
    ).values_list("group_id", "student_id")
    for group_id, student_id in rows:
        out[group_id].add(student_id)
    return out


def _enrollment_students(offering_ids):
    """``{group_id: {student_id, ...}}`` — açılışların aktiv qeydiyyatları, BİR sorğu.

    Audit 2026-09-28 (flows P1-3): xaric olunmuş / akademik məzuniyyətdəki tələbənin
    açılış qeydiyyatı `enrolled` qala bilir — ona görə tələbənin AKTİV+ENROLLED
    akademik qeydi (istənilən qrupda — alt qrupdan qonaqlar da daxil) şərtdir.
    """
    out = defaultdict(set)
    if not offering_ids:
        return out
    active_students = StudentAcademicRecord.objects.filter(is_active=True, status=AcademicStatus.ENROLLED).values(
        "student_id"
    )
    rows = Enrollment.objects.filter(
        offering_id__in=list(offering_ids),
        status=Enrollment.Status.ENROLLED,
        student_id__in=active_students,
    ).values_list("offering__group_id", "student_id")
    for group_id, student_id in rows:
        out[group_id].add(student_id)
    return out


def _specialty_name(group) -> str:
    parent = getattr(group, "parent", None)
    return getattr(parent, "name", "") or ""


def taught_group_rows(*, organization, teacher, period=None) -> list[dict]:
    """Müəllimin (cari) dövrdə dərs dediyi qruplar — seçici sətirləri.

    Hər sətir: ``{"id", "name", "specialty", "subjects", "student_count", "taught": True}``.
    """
    if organization is None or teacher is None:
        return []
    period = period or current_period(organization)
    if period is None:
        return []
    offerings = list(
        _taught_offerings(organization, teacher, period).select_related("group", "group__parent", "subject")
    )
    if not offerings:
        return []
    groups, subjects, offering_ids = {}, defaultdict(list), []
    for offering in offerings:
        groups[offering.group_id] = offering.group
        offering_ids.append(offering.pk)
        name = getattr(offering.subject, "name", "") or ""
        if name and name not in subjects[offering.group_id]:
            subjects[offering.group_id].append(name)
    by_record = _record_students(organization, groups.keys())
    by_enrollment = _enrollment_students(offering_ids)
    rows = [
        {
            "id": str(group_id),
            "name": group.name,
            "specialty": _specialty_name(group),
            "subjects": subjects[group_id],
            "student_count": len(by_record[group_id] | by_enrollment[group_id]),
            "taught": True,
        }
        for group_id, group in groups.items()
    ]
    rows.sort(key=lambda row: row["name"].casefold())
    return rows


def search_group_rows(*, organization, query: str = "", exclude_ids=(), limit: int = SEARCH_LIMIT) -> list[dict]:
    """Təşkilatın AKTİV akademik qrupları (xidməti vahidlər xaric) — adla dözümlü axtarış."""
    if organization is None:
        return []
    qs = _group_model().objects.filter(
        organization=organization,
        unit_type=OrgUnitType.GROUP,
        is_active=True,
        is_service_unit=False,
    )
    search = tolerant_q(query, compact_fields=("name",))
    if search is not None:
        qs = qs.filter(search)
    exclude = [pk for pk in exclude_ids if pk]
    if exclude:
        qs = qs.exclude(pk__in=exclude)
    groups = list(qs.select_related("parent").order_by("name")[: max(1, int(limit))])
    counts = dict(
        StudentAcademicRecord.objects.filter(
            organization=organization,
            group_id__in=[g.pk for g in groups],
            is_active=True,
            status=AcademicStatus.ENROLLED,
        )
        .values("group_id")
        .annotate(n=Count("student_id", distinct=True))
        .values_list("group_id", "n")
    )
    return [
        {
            "id": str(group.pk),
            "name": group.name,
            "specialty": _specialty_name(group),
            "subjects": [],
            "student_count": counts.get(group.pk, 0),
            "taught": False,
        }
        for group in groups
    ]


def specialty_by_group_name(*, organization, names) -> dict:
    """``{ad.casefold(): ixtisas adı}`` — kursdakı qrup adlarını reyestrlə zənginləşdirmək üçün."""
    wanted = {str(name or "").strip() for name in names or () if str(name or "").strip()}
    if organization is None or not wanted:
        return {}
    out = {}
    rows = (
        _group_model()
        .objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, name__in=wanted)
        .select_related("parent")
        .order_by("-is_active", "name")
    )
    for group in rows:
        out.setdefault(group.name.strip().casefold(), _specialty_name(group))
    return out


def resolve_groups(*, organization, group_ids) -> list:
    """Verilən id-lərdən bu təşkilatın aktiv akademik qrupları (yad/yanlış id-lər süzülür)."""
    ids = []
    for raw in group_ids or ():
        try:
            value = uuid.UUID(str(raw or "").strip())
        except ValueError:
            continue
        if value not in ids:
            ids.append(value)
    if organization is None or not ids:
        return []
    return list(
        _group_model()
        .objects.filter(organization=organization, unit_type=OrgUnitType.GROUP, is_active=True, pk__in=ids)
        .order_by("name")
    )


def group_student_ids(*, organization, groups, teacher=None, period=None) -> dict:
    """``{group_id: [student_id, ...]}`` — qeydlər + (müəllim verilibsə) onun açılış qeydiyyatları."""
    if organization is None or not groups:
        return {}
    group_ids = [group.pk for group in groups]
    by_record = _record_students(organization, group_ids)
    by_enrollment = defaultdict(set)
    if teacher is not None:
        period = period or current_period(organization)
        if period is not None:
            offering_ids = list(
                _taught_offerings(organization, teacher, period)
                .filter(group_id__in=group_ids)
                .values_list("pk", flat=True)
            )
            by_enrollment = _enrollment_students(offering_ids)
    return {group_id: sorted(by_record[group_id] | by_enrollment[group_id]) for group_id in group_ids}
