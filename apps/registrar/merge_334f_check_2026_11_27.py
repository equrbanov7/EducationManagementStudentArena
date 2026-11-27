"""MR-000836 (2026-11-27): 334F birləşməsindən sonra qayıb saatı tələbə-tələbə tutuşdurulur — YALNIZ OXUYUR.

Tyutor: «birləşmədən sonra bir sıra tələbələrin q/b göstəricilərində uyğunsuzluq var». Mənbə (334F1 / 334F2) jurnalların
xanaları bazada qalıb (qeydiyyatlar ``dropped``), ona görə hər tələbə üçün iki rəqəm hesablanır — jurnalın göstərdiyi
qaydada (:func:`.absence_credit.raw_hours` − :func:`.absence_credit_read.credit_hours_map`):

* ``src`` — mənbə qeydiyyat(lar)ının effektiv qayıb saatı (qayıb dərs saatları + əvvəlki birləşmələrdən köçən saat −
  üzrlü güzəşt);
* ``tgt`` — birləşmiş «334F» jurnalında, YALNIZ birləşmə anına qədərki xanalarla (sonra yazılan dərslər sayılmır).

Fərqin mənbəyi ayrıca sayılır: ``credit`` (mənbə qeydiyyatına bağlı üzrlü güzəşt — hədəfə keçmir), ``carried``
(mənbəyə əvvəlki birləşmədən köçən saat — hədəfə keçmir), ``marks`` (xana saatı fərqi: dərs saatı / itən xana).
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Sum

from .absence_credit_read import credit_hours_map, effective_hours
from .guest_merge import carried_absence_hours
from .merge_334f_2026_11_26 import RESOURCE


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def _absent_hours(enrollment_ids, *, until=None) -> dict:
    marks = _model("LessonMark").objects.filter(enrollment_id__in=enrollment_ids, status="absent")
    if until is not None:
        marks = marks.filter(created_at__lte=until)
    return dict(
        marks.values("enrollment_id").annotate(total=Sum("lesson__hours")).values_list("enrollment_id", "total")
    )


def _family(row, counts, report) -> None:
    Enrollment, CourseOffering = _model("Enrollment"), _model("CourseOffering")
    changes = row.changes or {}
    manifest = changes.get("manifest") or {}
    target_id, sources = changes.get("target"), manifest.get("sources_retired") or []
    target = CourseOffering.objects.select_related("subject").filter(pk=target_id).first()
    if target is None or not sources:
        counts["check_family_skipped"] += 1
        return
    code = getattr(target.subject, "code", "") or "x"
    by_student = defaultdict(list)
    for enrollment in Enrollment.objects.filter(offering_id__in=sources):
        by_student[enrollment.student_id].append(enrollment)
    targets = {row.student_id: row for row in Enrollment.objects.filter(offering=target, status="enrolled")}
    src_ids = [e.pk for rows in by_student.values() for e in rows]
    src_marks, src_credit = _absent_hours(src_ids), credit_hours_map(src_ids)
    tgt_ids = [e.pk for e in targets.values()]
    tgt_marks, tgt_credit = _absent_hours(tgt_ids, until=row.created_at), credit_hours_map(tgt_ids)
    counts["check_families"] += 1
    for student_id, rows in sorted(by_student.items()):
        target_row = targets.get(student_id)
        if target_row is None:
            counts["check_students_without_target"] += 1
            continue
        marks = sum(int(src_marks.get(e.pk) or 0) for e in rows)
        carried = sum(carried_absence_hours(e) for e in rows)
        credit = sum(int(src_credit.get(e.pk) or 0) for e in rows)
        src = effective_hours(marks + carried, credit)
        tgt_raw = int(tgt_marks.get(target_row.pk) or 0) + carried_absence_hours(target_row)
        tgt = effective_hours(tgt_raw, tgt_credit.get(target_row.pk))
        counts["check_students"] += 1
        if src == tgt:
            counts["check_students_equal"] += 1
            continue
        counts["check_students_target_less" if tgt < src else "check_students_target_more"] += 1
        counts["check_hours_lost_credit"] += credit - int(tgt_credit.get(target_row.pk) or 0)
        counts["check_hours_lost_carried"] += carried - (tgt_raw - int(tgt_marks.get(target_row.pk) or 0))
        counts["check_hours_marks_diff"] += marks - int(tgt_marks.get(target_row.pk) or 0)
        report.append(
            {
                "family": code,
                "student": student_id,
                "src": src,
                "tgt": tgt,
                "marks": marks,
                "tgtmarks": int(tgt_marks.get(target_row.pk) or 0),
                "credit": credit,
                "carried": carried,
            }
        )


def check(*, organization, batch: str, counts, report) -> None:
    AuditLog = _model("AuditLog", "audit")
    rows = AuditLog.objects.filter(
        organization=organization, resource_type=RESOURCE, new_values__batch=batch, new_values__op="family"
    ).order_by("created_at")
    if not rows.exists():
        counts["check_batch_unknown"] += 1
        return
    for row in rows:
        _family(row, counts, report)


__all__ = ["check"]
