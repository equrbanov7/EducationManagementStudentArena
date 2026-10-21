"""«Qərarları yadda saxla» — qərarı verən müəllim, əsaslandırıcı sənəd, qərar yazısı (sahib 2026-10-21).

Sahib: «Apellyasiyaya baxıb qəbul edərkən orada seçim olsun ki, hansı müəllim qəbul edib. Hələlik məcburi olmasa
da sənəd yükləmə yeri olsun … Yəni hansı müəllim bal artırıbdır, qeyd olsun».

* «Qərarı verən müəllim» — MƏCBURİ; yalnız fənni tədris edən aktiv müəllim və ya təşkilatın bal yaza bilən aktiv
  üzvü (``services.teachers.resolve_decision_teacher``) qəbul olunur. Yadda SAXLAYAN əməkdaş əvvəlki kimi
  ``resolved_by`` / ``saved_by``-dadır.
* «Əsaslandırıcı sənəd» — opsional; ``exam.appeal_document_required`` yandırılıbsa məcburi (server rədd edir).
* Hər uğurlu saxlama bir ``AppealDecisionRecord`` + audit sətri yazır və bir bildiriş hadisəsi yaradır.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from ...models import AppealDecisionRecord
from ...services.documents import can_download_document, document_required, validate_decision_document
from ...services.teachers import decision_teacher_options, resolve_decision_teacher, subject_teachers

logger = logging.getLogger(__name__)

TEACHER_FIELD = "decided_by_teacher"
DOCUMENT_FIELD = "decision_document"


def parse_decision_extras(request, appeal):
    """``(teacher, document)`` — xəta olarsa ``ValidationError`` (ilk mesaj UI-a gedir)."""
    raw = request.POST.get(TEACHER_FIELD)
    if raw is None:
        # Sahəni ümumiyyətlə göndərməyən köhnə klient (UI həmişə göndərir): fənnin TƏK müəllimi varsa o götürülür —
        # seçicinin defolt seçimi ilə eyni. Boş göndərilmiş sahə isə həmişə xətadır.
        teachers = subject_teachers(appeal)
        raw = teachers[0].pk if len(teachers) == 1 else ""
    teacher = resolve_decision_teacher(appeal, raw)
    if teacher is None:
        raise ValidationError(pgettext("appeals.view.message", "Qərarı verən müəllimi seçin."))
    document = validate_decision_document(request.FILES.get(DOCUMENT_FIELD))
    return teacher, document


def _person(user):
    return (user.get_full_name() or user.get_username()).strip() if user is not None else ""


def record_decision(request, appeal, *, teacher, document, decisions, score_before, score_after):
    """Qərar yazısını (sənəd daxil) saxla, audit et; yaradılmış ``AppealDecisionRecord``-u qaytar."""
    accepted = sum(1 for _item, decision, _text, _was in decisions if decision == "accept")
    record = AppealDecisionRecord(
        organization_id=appeal.organization_id,
        appeal=appeal,
        decided_by_teacher=teacher,
        saved_by=request.user,
        item_ids=[item.pk for item, *_rest in decisions],
        accepted_count=accepted,
        rejected_count=len(decisions) - accepted,
        score_before=score_before,
        score_after=score_after,
    )
    if document is not None:
        record.document_name = str(getattr(document, "name", "") or "")[:255]
        record.document = document
    record.save()
    _audit_decision(request, appeal, record)
    return record


def _audit_decision(request, appeal, record):
    try:
        from apps.audit.public import log_action
        from core.constants import AuditAction

        with transaction.atomic():  # savepoint — audit xətası qərarı geri qaytarmasın
            log_action(
                action=AuditAction.UPDATE,
                user=request.user,
                organization=appeal.organization,
                obj=record,
                reason="Appeal decisions saved",
                request=request,
                resource_type="appeals.decision_record",
                resource_id=str(record.pk),
                new_values={
                    "appeal_id": appeal.pk,
                    "attempt_id": appeal.attempt_id,
                    "decided_by_teacher_id": record.decided_by_teacher_id,
                    "decided_by_teacher": _person(record.decided_by_teacher),
                    "saved_by_id": record.saved_by_id,
                    "item_ids": record.item_ids,
                    "accepted": record.accepted_count,
                    "rejected": record.rejected_count,
                    "score_before": None if record.score_before is None else str(record.score_before),
                    "score_after": None if record.score_after is None else str(record.score_after),
                    "document": bool(record.document),
                },
            )
    except Exception:
        logger.warning("Appeal decision audit log failed.", exc_info=True)


def notify_after_commit(appeal, record):
    from ...services.notify import notify_decision_saved

    transaction.on_commit(lambda: notify_decision_saved(appeal, record))


def review_teacher_context(request, appeal, items):
    """Qərar modalı üçün: «Fənni tədris edən», seçici variantları (qərar yazıları tarixçədədir)."""
    options = decision_teacher_options(appeal)
    current = next((item.decided_by_teacher_id for item in items if item.decided_by_teacher_id), None)
    return {
        "review_subject_teachers": subject_teachers(appeal),
        "review_teacher_options": options,
        "review_teacher_selected": current or options["default_id"],
        "review_document_required": document_required(),
        "review_teacher_field": TEACHER_FIELD,
        "review_document_field": DOCUMENT_FIELD,
    }


def decision_timeline_events(request, appeal):
    """Tarixçəyə «Qərar: müəllim X · sənəd» sətirləri (``appeal_timeline``-a əlavə olunur)."""
    events = []
    records = list(AppealDecisionRecord.objects.filter(appeal=appeal).select_related("decided_by_teacher", "saved_by"))
    can_download = bool(records) and can_download_document(request.user, records[0])
    for record in records:
        record.can_download = can_download and bool(record.document)
        events.append(
            {
                "at": record.created_at,
                "icon": "fa-user-check",
                "text": pgettext(
                    "appeals.history",
                    "Qərar yadda saxlanıldı — qərarı verən müəllim: {teacher} ({accepted} qəbul, {rejected} rədd)",
                ).format(
                    teacher=_person(record.decided_by_teacher) or "—",
                    accepted=record.accepted_count,
                    rejected=record.rejected_count,
                ),
                "actor": _person(record.saved_by),
                "record": record,
            }
        )
    return events


def decided_teacher_names(appeal) -> str:
    """Item-lərdə qeyd olunmuş qərarı verən müəllimlər (təkrarsız, sıra ilə; prefetch olunmuş item-lərdən)."""
    seen, names = set(), []
    for item in appeal.items.all():
        teacher = getattr(item, "decided_by_teacher", None)
        if teacher is not None and teacher.pk not in seen:
            seen.add(teacher.pk)
            names.append(_person(teacher))
    return ", ".join(names)


def attach_list_teachers(appeals):
    from ...services.teachers import attach_subject_teachers

    attach_subject_teachers(appeals)
    for appeal in appeals:
        appeal.decided_teacher_names = decided_teacher_names(appeal)
    return appeals


__all__ = [
    "attach_list_teachers",
    "decided_teacher_names",
    "DOCUMENT_FIELD",
    "TEACHER_FIELD",
    "decision_timeline_events",
    "notify_after_commit",
    "parse_decision_extras",
    "record_decision",
    "review_teacher_context",
]
