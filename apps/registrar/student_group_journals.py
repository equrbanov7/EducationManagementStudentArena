"""Tələbəni ÖZ qrupunun cari jurnallarına salmaq (RİM müraciətləri, 2026-11-06).

Bərpa / köhnə sistemdən sinxronla qrupa düşən tələbə qrupun reyestrində görünür, amma qrupun cari semestr
jurnallarında yoxdur (məs. MR-000256: 535 MU reyestrdə 31, jurnallarda 30). «Alt qrupdan əlavə» öz qrupunun
tələbəsini qəbul etmir, rəsmi qrup köçürməsi isə eyni qrupa getmir — bu modul həmin boşluğu doldurur.

Qayda (yalnız ƏLAVƏ edir, heç nəyi silmir / dəyişmir):

* tələbənin aktiv, oxuyan (``enrolled``) akademik qeydi və qrupu olmalıdır;
* qrupun cari semestrdəki AKTİV adi (``regular``) jurnalları; səviyyə fənləri (xarici dil səviyyə qrupları
  ayrıca kohort jurnallarıdır) toxunulmur;
* jurnalda tələbənin istənilən statuslu sətri varsa — toxunulmur (çıxarılmışı geri qaytarmır);
* eyni fəndən bu semestrdə başqa jurnalda aktivdirsə (alt qrup / intensiv) və ya fəndən azad edilibsə — toxunulmur;
* qalan hallarda ``Enrollment(kind=mandatory)`` yaranır, hər biri audit sətri ilə.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from .language_levels import level_of

REASON = "Tələbə öz qrupunun cari jurnalına əlavə edildi (reyestrdə qrupdadır, jurnalda yox idi)"


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def current_period(organization):
    return (
        _model("AcademicPeriod", "organizations")
        .objects.filter(organization=organization, is_current=True, is_active=True)
        .order_by("-start_date")
        .first()
    )


def sync_student(*, organization, actor, student_id, counts, period=None) -> None:
    from .subject_exempt import is_exempt_from_subject

    Record, Offering, Enrollment = _model("StudentAcademicRecord"), _model("CourseOffering"), _model("Enrollment")
    period = period or current_period(organization)
    record = (
        Record.objects.filter(
            organization=organization, student_id=student_id, is_active=True, status="enrolled", group__isnull=False
        )
        .select_related("group")
        .order_by("-created_at")
        .first()
    )
    if record is None or period is None:
        counts["students_without_active_record"] += 1
        return
    offerings = Offering.objects.filter(
        organization=organization, group=record.group, period=period, is_active=True, course_format="regular"
    ).select_related("subject")
    added = 0
    for offering in offerings:
        if level_of(offering.subject.name):
            counts["level_subject_skipped"] += 1
            continue
        if Enrollment.objects.filter(offering=offering, student_id=student_id).exists():
            counts["already_in_journal"] += 1
            continue
        elsewhere = Enrollment.objects.filter(
            organization=organization,
            student_id=student_id,
            status="enrolled",
            offering__period=period,
            offering__subject_id=offering.subject_id,
        ).exists()
        if elsewhere:
            counts["active_in_other_journal_skipped"] += 1
            continue
        if is_exempt_from_subject(record, period, offering.subject_id):
            counts["exempt_skipped"] += 1
            continue
        with transaction.atomic():
            row = Enrollment.objects.create(
                organization=organization, offering=offering, student_id=student_id, kind="mandatory"
            )
            log_action(
                AuditAction.CREATE,
                user=actor,
                organization=organization,
                obj=row,
                new_values={"offering": str(offering.pk), "group": str(record.group_id), "student": student_id},
                reason=REASON,
            )
        added += 1
    counts["enrollments_added"] += added
    counts["students_synced" if added else "students_unchanged"] += 1


def run(*, organization, actor, counts, student_ids) -> None:
    period = current_period(organization)
    for student_id in student_ids:
        sync_student(organization=organization, actor=actor, student_id=student_id, counts=counts, period=period)
