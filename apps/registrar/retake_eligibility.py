"""25% / alt qrup UYĞUNLUĞU — tələbənin kəsr fənləri və hər fənn üzrə «niyə olar / niyə olmaz».

Sahibin qaydası (2026-10-18, tövsiyə olunan variant):

* fənn **25%** üçün uyğundur, əgər: yekun nəticə KƏSRdir; davamiyyət (qayıb) həddi KEÇİLMƏYİB; fənn
  üzrə 25% cəhd limiti (``retake.max_attempts``) dolmayıb; müraciət pəncərəsi açıqdır
  (``retake.applications_open``);
* qayıb həddi keçilibsə yalnız **alt qrup** (fənni yenidən keçmək) yolu təklif olunur;
* fənn üzrə aktiv müraciət varsa yenisi açılmır; fənn başqa qeydiyyatda artıq keçilibsə və ya hazırda
  yenidən keçilirsə siyahıda göstərilmir / bağlanır.

Nəticə riyaziyyatı TƏKRAR YAZILMIR — ``finals.compute_final_result`` toplu dəstlə (``finals_batch``)
çağırılır, transkriptin istifadə etdiyi EYNİ yol. Sorğu sayı fənn sayından asılı deyil.
"""

from __future__ import annotations

from collections import defaultdict

from django.utils.translation import pgettext_lazy

from . import finals, finals_batch, retake_rules
from .exam_eligibility import FAIL_REASON_BARRED, FAIL_REASON_EXAM, FAIL_REASON_TOTAL
from .models import (
    RETAKE_ACTIVE_STATUSES,
    Enrollment,
    RetakeApplication,
    RetakeKind,
    StudentAcademicRecord,
)
from .models.retake import consumes_attempt

_CTX = "registrar.retake"

FAIL_REASON_LABELS = {
    FAIL_REASON_BARRED: pgettext_lazy(_CTX, "Qayıb həddi keçilib — imtahana buraxılmamısınız"),
    FAIL_REASON_EXAM: pgettext_lazy(_CTX, "İmtahandan keçid balı toplanmayıb"),
    FAIL_REASON_TOTAL: pgettext_lazy(_CTX, "Yekun bal keçid həddindən aşağıdır"),
}

WHY_WINDOW = pgettext_lazy(_CTX, "Müraciət pəncərəsi hazırda bağlıdır.")
WHY_BARRED = pgettext_lazy(_CTX, "Qayıb həddi keçildiyi üçün 25% imtahan mümkün deyil — yalnız alt qrup.")
WHY_LIMIT = pgettext_lazy(_CTX, "Bu fənn üzrə 25% cəhd limiti dolub ({used}/{limit}).")
WHY_ACTIVE = pgettext_lazy(_CTX, "Bu fənn üzrə aktiv müraciətiniz var.")
WHY_IN_PROGRESS = pgettext_lazy(_CTX, "Bu fənn hazırda yenidən keçilir.")


def _student_enrollments(student, organization):
    return list(
        Enrollment.objects.filter(organization=organization, student=student)
        .exclude(status=Enrollment.Status.DROPPED)
        .select_related(
            "offering",
            "offering__subject",
            "offering__period",
            "offering__group",
            "offering__assessment_scheme",
        )
        .order_by("offering__period__start_date", "offering__subject__code", "pk")
    )


def _results(enrollments, organization) -> dict:
    """``enrollment_id`` → ``compute_final_result`` (transkriptlə EYNİ toplu yol)."""
    if not enrollments:
        return {}
    student_id = enrollments[0].student_id
    exempt = bool(
        StudentAcademicRecord.objects.filter(organization=organization, student_id=student_id)
        .values_list("national_athlete_exemption", flat=True)
        .first()
    )
    batch = finals_batch.build(enrollments, organization=organization)
    return {
        e.id: finals.compute_final_result(enrollment=e, organization=organization, exempt=exempt, batch=batch)
        for e in enrollments
    }


def _applications_by_subject(student, organization) -> dict:
    grouped = defaultdict(list)
    for app in RetakeApplication.objects.filter(organization=organization, student=student).order_by("created_at"):
        grouped[app.subject_id].append(app)
    return grouped


def _option(allowed: bool, why="") -> dict:
    return {"allowed": bool(allowed), "why": str(why) if not allowed else ""}


def _row(enrollment, result, *, apps, limit, window_open, in_progress) -> dict:
    fail_reason = result.get("fail_reason") or ""
    # 2026-10-19 (sahib): qaytarılma qərarı «cəhd istifadə olunmuş sayılmasın» ilə cəhdi bərpa edir.
    used = sum(1 for a in apps if consumes_attempt(a))
    active = next((a for a in apps if a.status in RETAKE_ACTIVE_STATUSES), None)
    barred = fail_reason == FAIL_REASON_BARRED
    common_block = WHY_WINDOW if not window_open else WHY_ACTIVE if active else WHY_IN_PROGRESS if in_progress else ""
    if common_block:
        retake = _option(False, common_block)
    elif barred:
        retake = _option(False, WHY_BARRED)
    elif used >= limit:
        retake = _option(False, str(WHY_LIMIT).format(used=used, limit=limit))
    else:
        retake = _option(True)
    subgroup = _option(not common_block, common_block)
    return {
        "enrollment": enrollment,
        "offering": enrollment.offering,
        "subject": enrollment.offering.subject,
        "period": enrollment.offering.period,
        "result": result,
        "fail_reason": fail_reason,
        "fail_reason_label": str(FAIL_REASON_LABELS.get(fail_reason, "")),
        "attempts_used": used,
        "attempts_limit": limit,
        "attempts_left": max(0, limit - used),
        "active": active,
        "applications": apps,
        "options": {RetakeKind.RETAKE_25.value: retake, RetakeKind.SUBGROUP.value: subgroup},
        "any_allowed": retake["allowed"] or subgroup["allowed"],
    }


def failed_subjects(*, student, organization) -> list:
    """Tələbənin hələ keçilməmiş kəsr fənləri — fənn başına ƏN SON kəsr qeydiyyat bir sətir."""
    if student is None or organization is None:
        return []
    enrollments = _student_enrollments(student, organization)
    results = _results(enrollments, organization)
    passed_subjects = {e.offering.subject_id for e in enrollments if results[e.id]["passed"]}
    latest_failed: dict = {}
    open_after: dict = defaultdict(list)
    for enrollment in enrollments:
        result = results[enrollment.id]
        subject_id = enrollment.offering.subject_id
        if result["failed"]:
            latest_failed[subject_id] = enrollment
        elif not result["passed"]:
            open_after[subject_id].append(enrollment)
    apps_by_subject = _applications_by_subject(student, organization)
    limit = retake_rules.max_attempts()
    window_open = retake_rules.applications_open(organization)
    rows = []
    for subject_id, enrollment in latest_failed.items():
        if subject_id in passed_subjects:
            continue
        start = enrollment.offering.period.start_date
        in_progress = any(
            other.offering.period.start_date > start and other.id != enrollment.id for other in open_after[subject_id]
        )
        rows.append(
            _row(
                enrollment,
                results[enrollment.id],
                apps=apps_by_subject.get(subject_id, []),
                limit=limit,
                window_open=window_open,
                in_progress=in_progress,
            )
        )
    rows.sort(key=lambda row: (row["period"].start_date, row["subject"].name), reverse=True)
    return rows


def row_for_enrollment(*, student, organization, enrollment_id):
    """Bir qeydiyyatın uyğunluq sətri (müraciət anında YENİDƏN hesablanır) və ya ``None``."""
    for row in failed_subjects(student=student, organization=organization):
        if str(row["enrollment"].id) == str(enrollment_id):
            return row
    return None


def snapshot(row) -> dict:
    """Müraciət anında «niyə uyğundur» — JSON-a sığan dondurulmuş şəkil."""
    result = row["result"]

    def _num(value):
        return None if value is None else str(value)

    return {
        "fail_reason": row["fail_reason"],
        "fail_reason_label": row["fail_reason_label"],
        "barred": bool(result["barred"]),
        "entry_score": _num(result.get("entry_score")),
        "exam_score": _num(result.get("exam_score")),
        "effective_exam": _num(result.get("effective_exam")),
        "total": _num(result.get("total")),
        "letter": result.get("letter") or "",
        "pass_threshold": _num(result.get("pass_threshold")),
        "min_final_exam_score": _num(result.get("min_final_exam_score")),
        "attempts_used": row["attempts_used"],
        "attempts_limit": row["attempts_limit"],
        "period": row["period"].name,
    }


__all__ = ["FAIL_REASON_LABELS", "failed_subjects", "row_for_enrollment", "snapshot"]
