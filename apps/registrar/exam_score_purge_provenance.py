"""Silinmiş cəhdin rəqəmsal ledger-i üçün dar, append-only mənbə sübutu.

Note özü sübut deyil: cəhd və apellyasiya hələ mövcud ikən adi rəqəmsal
provenance qaydası ilə yoxlanmış entry ID-ləri saxlanır. Cəhd silindikdən
sonra yalnız həmin təşkilat/qeydiyyat/tələbə/entry əlaqəsi istisnadır.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from core.constants import AuditAction

from .models import Enrollment, ExamAssessment, ExamScoreEntry, ExamScoreEntryKind

AUDIT_RESOURCE_TYPE = "registrar.exam-score-purged-attempt"
_VERSION = 1


def capture_purge_provenance(attempt):
    """Purge tranzaksiyasında, cəhd və onun sübutları silinməzdən ƏVVƏL çağırılır."""
    from .exam_bridge import resolve_exam_result_target
    from .exam_score_precedence import _DIGITAL_APPEAL_NOTE, _digital_appeal_entry

    exam = attempt.exam
    if exam.exam_type_extended != "final":
        return None
    target = resolve_exam_result_target(
        student=attempt.user,
        subject_id=exam.subject_id,
        organization=exam.organization,
        offering_ids=list(exam.journal_offerings.values_list("pk", flat=True)),
        attempt=attempt,
    )
    if target is None or target[0] != "enrollment":
        return None
    enrollment = Enrollment.objects.select_for_update().get(pk=target[1], organization_id=exam.organization_id)
    entries = ExamScoreEntry.objects.filter(
        organization_id=exam.organization_id, enrollment=enrollment, assessment=ExamAssessment.FINAL
    )
    proven = [
        {"entry_id": str(entry.pk), "appeal_id": int(_DIGITAL_APPEAL_NOTE.fullmatch(entry.note)[1])}
        for entry in entries
        if _digital_appeal_entry(entry, enrollment, attempt)
    ]
    if not proven:
        return None
    return {
        "version": _VERSION,
        "organization_id": str(exam.organization_id),
        "enrollment_id": str(enrollment.pk),
        "student_id": enrollment.student_id,
        "attempt_id": attempt.pk,
        "exam_id": exam.pk,
        "entries": proven,
    }


def record_purge_provenance(proof, *, organization, reason, actor=None, request=None):
    """Silinmə və bərpa ilə EYNİ tranzaksiyada; audit alınmasa purge geri qayıdır."""
    from core.audit import log_action

    if not proof:
        return None
    Attempt = django_apps.get_model("exams", "ExamAttempt")
    if proof["organization_id"] != str(organization.pk) or Attempt.objects.filter(pk=proof["attempt_id"]).exists():
        raise ValueError("purge_provenance_requires_deleted_attempt")
    AuditLog = django_apps.get_model("audit", "AuditLog")
    existing = AuditLog.objects.filter(
        organization=organization,
        resource_type=AUDIT_RESOURCE_TYPE,
        resource_id=str(proof["attempt_id"]),
        changes__enrollment_id=proof["enrollment_id"],
    ).first()
    if existing is not None:
        return existing
    return log_action(
        action=AuditAction.DELETE,
        user=actor,
        organization=organization,
        resource_type=AUDIT_RESOURCE_TYPE,
        resource_id=str(proof["attempt_id"]),
        changes=proof,
        reason=reason,
        request=request,
    )


def purged_digital_entry_ids(enrollment, entries):
    """Yalnız saxlanmış sübut + artıq mövcud olmayan cəhd əsasında ledger istisnası."""
    AuditLog = django_apps.get_model("audit", "AuditLog")
    proofs = list(
        AuditLog.objects.filter(
            organization_id=enrollment.organization_id,
            resource_type=AUDIT_RESOURCE_TYPE,
            action=AuditAction.DELETE,
            changes__version=_VERSION,
            changes__organization_id=str(enrollment.organization_id),
            changes__enrollment_id=str(enrollment.pk),
            changes__student_id=enrollment.student_id,
        ).values("resource_id", "changes", "created_at")
    )
    if not proofs:
        return set()
    Attempt = django_apps.get_model("exams", "ExamAttempt")
    attempt_ids = {
        proof["changes"].get("attempt_id") for proof in proofs if isinstance(proof["changes"].get("attempt_id"), int)
    }
    remaining = set(Attempt.objects.filter(pk__in=attempt_ids).values_list("pk", flat=True))
    by_id = {str(entry.pk): entry for entry in entries}
    ignored = set()
    for proof in proofs:
        data = proof["changes"]
        attempt_id = data.get("attempt_id")
        if attempt_id not in attempt_ids or attempt_id in remaining or proof["resource_id"] != str(attempt_id):
            continue
        if not isinstance(data.get("exam_id"), int):
            continue
        for item in data.get("entries", []):
            if not isinstance(item, dict):
                continue
            entry = by_id.get(item.get("entry_id"))
            if (
                entry is not None
                and entry.organization_id == enrollment.organization_id
                and entry.enrollment_id == enrollment.pk
                and entry.assessment == ExamAssessment.FINAL
                and entry.kind == ExamScoreEntryKind.APPEAL
                and not entry.evidence
                and entry.sheet_id is None
                and isinstance(item.get("appeal_id"), int)
                and entry.note == f"Rəqəmsal apellyasiya #{item['appeal_id']}"
                and entry.created_at <= proof["created_at"]
            ):
                ignored.add(entry.pk)
    return ignored
