"""Səviyyə qrupları yenidən qurulduqdan sonra SİYAHIDA OLMAYAN tələbələr (sahib 2026-11-06).

Sahib: «siyahıda adı yoxdursa və digər heç bir fəndə də i/e yoxdursa — dondur hesablarını, varsa fəndən azad et.»

«Qalan» = planın səviyyə fənlərindən (Beginner / Elementary / Pre-Int / Intermediate) birində hələ ``enrolled``
olan, heç bir kohort jurnalına yerləşdirilməmiş tələbə (təkrar — ``retake`` qeydiyyatı toxunulmur):

* bu semestr DİGƏR fənlərin birində iştirakı (i/e — ``present`` və ya bal) varsa → səviyyə qeydiyyatları rəsmi
  «Fəndən azad et» ilə (:func:`subject_exempt.exempt_student`, səbəb «Digər») çıxarılır — jurnalda «Bərpa et» var;
* heç bir iştirakı yoxdursa → akademik qeyd «Akademik məzuniyyət (dondurma)» olur (cari qeydiyyatlar əmr yolu ilə
  eyni qayda ilə dondurulur) — tələbə kartında bərpa olunur.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db import transaction
from django.db.models import Q

from core.audit import log_action
from core.constants import AuditAction

FREEZE_REASON = (
    "Səviyyə qrupları rəsmi siyahısında yoxdur, heç bir fəndə iştirakı yoxdur (sahib 2026-11-06) — dondurulur"
)
RELEASE_NOTE = "Səviyyə qrupları rəsmi siyahısında yoxdur (sahib 2026-11-06) — xarici dil fənnindən azad"


def _model(name):
    return django_apps.get_model("registrar", name)


def settle(rebuild) -> None:
    Enrollment, Cohort = _model("Enrollment"), _model("LanguageLevelCohort")
    subjects = {row["subject"] for row in rebuild.plan["classes"]}
    cohort_offerings = Cohort.objects.filter(organization=rebuild.organization, period=rebuild.period).values(
        "offering_id"
    )
    placed = set(
        Enrollment.objects.filter(offering_id__in=cohort_offerings, status="enrolled").values_list(
            "student_id", flat=True
        )
    )
    rows = (
        Enrollment.objects.filter(
            organization=rebuild.organization,
            status="enrolled",
            offering__period=rebuild.period,
            offering__is_active=True,
            offering__subject_id__in=subjects,
        )
        .exclude(offering_id__in=cohort_offerings)
        .select_related("offering__organization")
        .order_by("student_id", "pk")
    )
    by_student = defaultdict(list)
    for row in rows:
        by_student[row.student_id].append(row)
    for student_id, enrollments in by_student.items():
        with transaction.atomic():
            _student(rebuild, student_id, enrollments, subjects, placed)


def _student(rebuild, student_id, enrollments, subjects, placed) -> None:
    counts = rebuild.counts
    if student_id in placed:
        counts["leftover_also_placed_kept"] += 1
        return
    if any(row.kind == "retake" for row in enrollments):
        counts["leftover_retake_kept"] += 1
        return
    record = (
        _model("StudentAcademicRecord")
        .objects.select_for_update(of=("self",))
        .filter(organization=rebuild.organization, student_id=student_id, is_active=True, status="enrolled")
        .first()
    )
    if record is None:
        counts["leftover_without_active_record"] += 1
        return
    rebuild.touched_sources.update(row.offering_id for row in enrollments)
    attends = (
        _model("LessonMark")
        .objects.filter(
            enrollment__student_id=student_id,
            enrollment__status="enrolled",
            enrollment__offering__period=rebuild.period,
        )
        .exclude(enrollment__offering__subject_id__in=subjects)
        .filter(Q(status="present") | Q(score__isnull=False))
        .exists()
    )
    if attends:
        _release(rebuild, enrollments)
    else:
        _freeze(rebuild, record)


def _release(rebuild, enrollments) -> None:
    from . import subject_exempt
    from .models import RemovalReason

    for row in enrollments:
        try:
            subject_exempt.exempt_student(
                offering=row.offering,
                enrollment_id=row.pk,
                actor=rebuild.actor,
                reason=RELEASE_NOTE,
                removal={"reason": RemovalReason.OTHER.value, "note": RELEASE_NOTE},
            )
        except subject_exempt.HygieneError:
            rebuild.counts["leftover_release_blocked"] += 1
            continue
        rebuild.counts["leftover_enrollments_released"] += 1
    rebuild.counts["leftover_students_released"] += 1


def _freeze(rebuild, record) -> None:
    from .enrollment_suspension import sync_enrollments_for_status
    from .status import audit_status_change

    previous = record.status
    record.status = "academic_leave"
    record.is_active = False
    record.save(update_fields=["status", "is_active", "updated_at"])
    audit_status_change(record=record, previous=previous, by_user=rebuild.actor, reason=FREEZE_REASON)
    sync_enrollments_for_status(
        record=record, previous=previous, to_status="academic_leave", actor=rebuild.actor, reason=FREEZE_REASON
    )
    log_action(
        AuditAction.UPDATE,
        user=rebuild.actor,
        organization=rebuild.organization,
        obj=record,
        old_values={"status": previous},
        new_values={"status": "academic_leave", "leave_reason": "other"},
        reason=FREEZE_REASON,
    )
    rebuild.counts["leftover_students_frozen"] += 1
