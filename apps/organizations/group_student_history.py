"""Qrup çekmecəsi «Tarixçə» — tələbənin BÜTÜN jurnal statistikası, dondurulmuş qeydiyyatlar daxil (sahib 2026-11-25).

Sahib: «tələbənin köhnə datasını görə bilsin, yenidən dönsə belə baxa bilsin ki statistik olaraq, dondurana kimi
neçə qiyməti var idi».

NİYƏ YENİ SƏTH? Akademik məzuniyyət / xaric cari qeydiyyatı ``suspended`` edir, köçürmə köhnəsini ``dropped``
(``Enrollment.Status``); jurnal grid-i, transkript, kabinet bu sətirləri GÖSTƏRMİR — bal DB-də qalır, amma heç yerdə
görünmürdü. Bu endpoint YALNIZ OXUDUR və hər statusdakı qeydiyyatı sayır:

* fənn × semestr: dərs qeydi (iştirak / qayıb / üzrlü), bal sayı, orta bal, qayıb saatı, son dərs tarixi;
* son akademik məzuniyyət əmri varsa: «dondurulana qədər» bal sayı (dərs tarixi ≤ əmrin tarixi);
* hərəkət əmrlərinin tarixçəsi (dondurma, bərpa, köçürmə, xaric …).

QAPI — ``group_students`` ilə EYNİ (tenant + ``unit.view`` + tələbə siyahısı açarı + görünən qrup) ÜSTƏGƏL
``student.records_view`` (akademik qeyd oxusu). Tələbə bu qrupa aid olmalıdır: qeydinin qrupu qrup / alt qrupudur
və ya bu qrupun açılışında (istənilən statusda) qeydiyyatı var («əlavə üzv»). Əks halda 404 (IDOR).
Sorğular sabitdir: qeydlər + qeydiyyatlar + bir aqreqat + hərəkətlər.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from core.person_names import person_label

from .group_actions import _error, _visible_group
from .group_roster_union import roster_group_ids
from .groups_registry import can_view_group_students, can_view_groups, group_scope
from .models import Organization
from .views.shared._helpers import _has_org_permission

_CTX = "accounts.group_history"
PERM_RECORDS_VIEW = "student.records_view"
#: Bir tələbənin qeydiyyat sətirlərinin yuxarı həddi (≈ 8 semestr × 12 fənn + təkrarlar).
MAX_ENROLLMENTS = 240


def can_view_history(request) -> bool:
    return _has_org_permission(request, PERM_RECORDS_VIEW)


def history_url(organization, unit, record_id) -> str:
    return reverse(
        "organizations:group_student_history",
        kwargs={"slug": organization.slug, "unit_id": unit.pk, "record_id": record_id},
    )


def _enrollment_status_labels() -> dict:
    return {
        "enrolled": pgettext(_CTX, "Oxuyur"),
        "completed": pgettext(_CTX, "Tamamlanıb"),
        "suspended": pgettext(_CTX, "Dondurulub"),
        "dropped": pgettext(_CTX, "Çıxarılıb / köçürülüb"),
    }


def _record_status_labels() -> dict:
    return {
        "enrolled": pgettext(_CTX, "Qeydiyyatlı"),
        "academic_leave": pgettext(_CTX, "Akademik məzuniyyət"),
        "expelled": pgettext(_CTX, "Xaric edilib"),
        "graduated": pgettext(_CTX, "Məzun"),
    }


def _date(value) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _number(value):
    return None if value is None else round(float(value), 2)


def _load_record(organization, unit, record_id):
    """Qeyd bu qrupa aiddirmi — öz qrupu (və alt qrupları) və ya bu qrupun açılışında qeydiyyatı var."""
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    record = (
        record_model.objects.filter(organization=organization, pk=record_id)
        .select_related("student", "group", "program")
        .first()
    )
    if record is None:
        return None
    group_ids = roster_group_ids(organization, [unit])[str(unit.pk)]
    if record.group_id in group_ids:
        return record
    in_group = enrollment_model.objects.filter(
        organization=organization, student_id=record.student_id, offering__group_id__in=list(group_ids)
    ).exists()
    return record if in_group else None


def _last_freeze(movements):
    for movement in movements:
        if movement.kind == "academic_leave":
            return movement
    return None


def _movement_rows(movements) -> list:
    return [
        {
            "kind": movement.kind,
            "kind_label": str(movement.kind_label),
            "order_number": movement.order_number or "",
            "order_date": _date(movement.order_date),
            "until": _date(movement.effective_until),
            "from_group": getattr(movement.from_group, "name", "") or "",
            "to_group": getattr(movement.to_group, "name", "") or "",
        }
        for movement in movements
    ]


def _stats(organization, enrollment_ids, freeze_date) -> dict:
    mark_model = django_apps.get_model("registrar", "LessonMark")
    aggregates = {
        "lessons": Count("pk"),
        "present": Count("pk", filter=Q(status="present")),
        "absent": Count("pk", filter=Q(status="absent")),
        "excused": Count("pk", filter=Q(status="excused")),
        "marks": Count("pk", filter=Q(score__isnull=False)),
        "average": Avg("score", filter=Q(score__isnull=False)),
        "last_date": Max("lesson__date"),
    }
    if freeze_date is not None:
        aggregates["marks_before_freeze"] = Count("pk", filter=Q(score__isnull=False, lesson__date__lte=freeze_date))
    rows = (
        mark_model.objects.filter(organization=organization, enrollment_id__in=enrollment_ids)
        .values("enrollment_id")
        .annotate(**aggregates)
    )
    return {row["enrollment_id"]: row for row in rows}


def build_history(organization, record) -> dict:
    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    movement_model = django_apps.get_model("registrar", "StudentMovement")
    movements = list(
        movement_model.objects.filter(organization=organization, record=record)
        .select_related("from_group", "to_group")
        .order_by("-order_date", "-created_at")
    )
    freeze = _last_freeze(movements)
    freeze_date = freeze.order_date if freeze is not None else None
    enrollments = list(
        enrollment_model.objects.filter(organization=organization, student_id=record.student_id)
        .select_related("offering__subject", "offering__group", "offering__period")
        .order_by("-offering__period__start_date", "offering__subject__name")[:MAX_ENROLLMENTS]
    )
    stats = _stats(organization, [enrollment.pk for enrollment in enrollments], freeze_date)
    labels = _enrollment_status_labels()
    periods: dict = {}
    totals = {"subjects": 0, "lessons": 0, "present": 0, "absent": 0, "marks": 0, "marks_before_freeze": 0}
    score_sum, score_count = 0.0, 0
    for enrollment in enrollments:
        offering = enrollment.offering
        period = offering.period
        row_stats = stats.get(enrollment.pk, {})
        marks = int(row_stats.get("marks") or 0)
        average = _number(row_stats.get("average"))
        row = {
            "subject": getattr(offering.subject, "name", "") or "",
            "subject_code": getattr(offering.subject, "code", "") or "",
            "group": getattr(offering.group, "name", "") or "",
            "status": enrollment.status,
            "status_label": labels.get(enrollment.status, enrollment.status),
            "lessons": int(row_stats.get("lessons") or 0),
            "present": int(row_stats.get("present") or 0),
            "absent": int(row_stats.get("absent") or 0),
            "excused": int(row_stats.get("excused") or 0),
            "marks": marks,
            "marks_before_freeze": int(row_stats.get("marks_before_freeze") or 0),
            "average": average,
            "absence_hours": int(enrollment.absence_hours or 0),
            "last_date": _date(row_stats.get("last_date")),
        }
        key = str(period.pk) if period is not None else ""
        bucket = periods.setdefault(
            key,
            {"label": f"{period.academic_year} · {period.name}" if period is not None else "—", "rows": []},
        )
        bucket["rows"].append(row)
        totals["subjects"] += 1
        for name in ("lessons", "present", "absent", "marks", "marks_before_freeze"):
            totals[name] += row[name]
        if average is not None and marks:
            score_sum += average * marks
            score_count += marks
    totals["average"] = round(score_sum / score_count, 2) if score_count else None
    student = record.student
    return {
        "ok": True,
        "student": {"name": person_label(student), "username": student.username},
        "record": {
            "status": record.status,
            "status_label": _record_status_labels().get(record.status, record.status),
            "group": getattr(record.group, "name", "") or "",
            "program": getattr(record.program, "name", "") or "",
        },
        "freeze": (
            {
                "order_number": freeze.order_number or "",
                "date": _date(freeze.order_date),
                "until": _date(freeze.effective_until),
            }
            if freeze is not None
            else None
        ),
        "periods": list(periods.values()),
        "totals": totals,
        "movements": _movement_rows(movements),
        "truncated": len(enrollments) >= MAX_ENROLLMENTS,
    }


@login_required
@require_GET
def group_student_history(request, slug, unit_id, record_id):
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    if not (can_view_groups(request) and can_view_group_students(request) and can_view_history(request)):
        return _error(
            pgettext(_CTX, "Tələbənin tarixçəsinə baxmaq səlahiyyətiniz yoxdur."), status=403, code="forbidden"
        )
    scope = group_scope(request, organization)
    if not scope.has_structure_access:
        return _error(pgettext(_CTX, "Struktur əhatəniz yoxdur."), status=403, code="forbidden")
    unit = _visible_group(organization, scope, str(unit_id), include_archived=True)
    if unit is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı."), status=404, code="not_found")
    record = _load_record(organization, unit, record_id)
    if record is None:
        return _error(pgettext(_CTX, "Tələbə bu qrupda tapılmadı."), status=404, code="not_found")
    return JsonResponse(build_history(organization, record))


__all__ = ["build_history", "can_view_history", "group_student_history", "history_url"]
