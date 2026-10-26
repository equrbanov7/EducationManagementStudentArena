"""Midtermin fənni / jurnal bağlantısı dəyişəndə təsdiq + səbəb qapısı (sahib 2026-10-25).

Sahib: «İmtahan yaradılarkən səhvən fənn seçilə bilər, sonra fənn başqasına dəyişdirilə bilər — tələbə imtahanı
verdikdən sonra hansı olsa, o nəticələr həmin fənnə doğru keçirilir. Bunu TƏSDİQLƏ etmək lazımdır, SƏBƏB yazmaq —
bunu edən. Tələbənin nəticəsi YOXDURSA sadə formada olsun; VARSA məcburi (təsdiq + səbəb)».

Qayda (server avtoritetdir — API birbaşa çağırılsa da):

* imtahan (əvvəl və ya sonra) **midterm**dir, redaktə olunur və **fənn** dəyişir — və ya müəllim (jurnal) /
  reyestr qrupları dəyişib nəticədə **bağlı jurnallar** (``Exam.journal_offerings``) dəyişir;
* imtahanda sınaq olmayan cəhd (yazmaqda / bitmiş) **varsa** — dəyişiklik yalnız açıq təsdiq
  (``subject_change_confirm``) + ən azı :data:`REASON_MIN_LENGTH` simvolluq səbəb (``subject_change_reason``)
  ilə qəbul olunur; yoxdursa — əvvəlki sadə forma (heç nə soruşulmur).

Qəbul olunan dəyişiklik ``AuditLog``-a yazılır (``resource_type =`` :data:`AUDIT_RESOURCE` — kim, nə vaxt,
köhnə / yeni fənn və jurnallar, səbəb, nəticəsi olan tələbə sayı); nəticələrin köçürülməsi mövcud sinxron
servisi ilə gedir (``exam_journal_link.after_exam_saved`` → yeni jurnala yazılır, köhnə jurnaldakı bu imtahanın
xanaları silinir) və tranzaksiyadan sonra faktiki saylar :data:`AUDIT_RESOURCE_RESYNC` sətrinə düşür. Hər iki
sətir imtahan səhifəsindəki «Fənn dəyişikliyi tarixçəsi»ndə görünür (:func:`history`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.utils.translation import pgettext

logger = logging.getLogger(__name__)

#: Səbəbin minimum uzunluğu (boşluqlar kəsildikdən sonra).
REASON_MIN_LENGTH = 10
REASON_MAX_LENGTH = 1000
#: POST sahələri (ExamForm-un sahəsi deyil — ``allowed_units`` kimi view yoxlayır).
CONFIRM_FIELD = "subject_change_confirm"
REASON_FIELD = "subject_change_reason"
#: Audit sətirləri (``AuditLog.resource_type``; ``resource_id`` — imtahanın pk-si).
AUDIT_RESOURCE = "exam_subject_change"
AUDIT_RESOURCE_RESYNC = "exam_subject_change_resync"
#: Nəticəsi «olan» cəhd statusları — yazmaqda olan cəhdin balı da bitəndə yeni fənnə düşəcək.
_RESULT_STATUSES = ("in_progress", "submitted", "expired")

_CTX = "exams.subject_change"


def _is_midterm(category) -> bool:
    from apps.exams.services.journal_sync import MIDTERM_EXAM_CATEGORY

    return str(category or "").strip() == MIDTERM_EXAM_CATEGORY


def subject_label(subject) -> str:
    if subject is None:
        return "—"
    code = getattr(subject, "code", "") or ""
    name = getattr(subject, "name", "") or str(subject)
    return f"{name} ({code})" if code else name


def result_students(exam) -> int:
    """İmtahanda sınaq olmayan cəhdi (yazmaqda / bitmiş) olan tələbələrin sayı."""
    if not getattr(exam, "pk", None):
        return 0
    from apps.exams.models import ExamAttempt

    return (
        ExamAttempt.objects.filter(exam_id=exam.pk, is_trial=False, status__in=_RESULT_STATUSES)
        .values("user_id")
        .distinct()
        .count()
    )


@dataclass(frozen=True)
class Snapshot:
    """İmtahanın redaktədən ƏVVƏLKİ halı (forma ``is_valid()`` instansı dəyişməmiş götürülür)."""

    subject_id: object
    subject_label: str
    teacher_id: object
    unit_ids: frozenset
    link_ids: frozenset
    category: str


def take_snapshot(exam):
    if exam is None or not getattr(exam, "pk", None):
        return None
    from apps.exams.services import exam_journal_link

    return Snapshot(
        subject_id=exam.subject_id,
        subject_label=subject_label(exam.subject if exam.subject_id else None),
        teacher_id=exam.journal_teacher_id,
        unit_ids=frozenset(exam.allowed_units.values_list("pk", flat=True)),
        link_ids=frozenset(exam_journal_link.linked_offering_ids(exam)),
        category=str(exam.exam_type_extended or ""),
    )


@dataclass(frozen=True)
class Decision:
    """Təsdiq tələb edən dəyişiklik."""

    students: int
    old_subject_id: object
    old_subject_label: str
    new_subject_id: object
    new_subject_label: str
    old_link_ids: frozenset
    new_link_ids: frozenset

    def audit_payload(self) -> dict:
        return {
            "old": {"subject_id": _s(self.old_subject_id), "subject": self.old_subject_label},
            "new": {"subject_id": _s(self.new_subject_id), "subject": self.new_subject_label},
            "old_journal_offerings": sorted(_s(pk) for pk in self.old_link_ids),
            "new_journal_offerings": sorted(_s(pk) for pk in self.new_link_ids),
            "students_with_results": self.students,
        }


def _s(value):
    return "" if value is None else str(value)


def _prospective_link_ids(exam, *, unit_ids) -> frozenset:
    from apps.registrar.public import exam_journal_link as registrar_link

    if not exam.subject_id or exam.organization_id is None:
        return frozenset()
    return frozenset(
        registrar_link.link_offering_ids(
            exam.organization,
            subject_id=exam.subject_id,
            group_ids=list(unit_ids),
            teacher=exam.journal_teacher,
        )
    )


def decide(snapshot, exam, *, unit_ids):
    """``exam`` — forma təmizlədikdən sonrakı (saxlanmamış) instans; ``unit_ids`` — saxlanacaq qruplar.

    → :class:`Decision` (təsdiq + səbəb tələb olunur) və ya ``None`` (sadə forma)."""
    if snapshot is None or not (_is_midterm(snapshot.category) or _is_midterm(exam.exam_type_extended)):
        return None
    unit_ids = frozenset(unit_ids or ())
    subject_changed = snapshot.subject_id != exam.subject_id
    inputs_changed = snapshot.teacher_id != exam.journal_teacher_id or snapshot.unit_ids != unit_ids
    if not subject_changed and not inputs_changed:
        return None
    new_link_ids = _prospective_link_ids(exam, unit_ids=unit_ids)
    if not subject_changed and snapshot.link_ids <= new_link_ids:
        # Qrup / müəllim dəyişsə də köhnə jurnalların HEÇ BİRİ ayrılmır (eyni və ya yalnız əlavə — məs. sahib
        # 2026-10-26: qrupun yeni alt qrup jurnalları) — nəticə heç yerdən silinmir, təsdiq lazım deyil.
        return None
    students = result_students(exam)
    if not students:
        return None
    return Decision(
        students=students,
        old_subject_id=snapshot.subject_id,
        old_subject_label=snapshot.subject_label,
        new_subject_id=exam.subject_id,
        new_subject_label=subject_label(exam.subject if exam.subject_id else None),
        old_link_ids=snapshot.link_ids,
        new_link_ids=new_link_ids,
    )


def validate_confirmation(data):
    """POST-dan təsdiq + səbəb → ``(reason | None, xəta mətni | "")``."""
    confirmed = str(data.get(CONFIRM_FIELD) or "").strip().lower() in {"1", "on", "true", "yes"}
    reason = " ".join(str(data.get(REASON_FIELD) or "").split())[:REASON_MAX_LENGTH]
    if not confirmed and not reason:
        return None, pgettext(
            _CTX, "Bu imtahanda tələbə nəticələri var — fənn dəyişikliyini təsdiqləyin və səbəbini yazın."
        )
    if not confirmed:
        return None, pgettext(_CTX, "Fənn dəyişikliyini təsdiqləyin («Təsdiq edirəm»).")
    if len(reason) < REASON_MIN_LENGTH:
        return None, pgettext(_CTX, "Səbəb ən azı %(min)d simvol olmalıdır.") % {"min": REASON_MIN_LENGTH}
    return reason, ""


def record_decision(exam, decision, *, reason, user, request=None):
    """Qəbul olunan dəyişikliyi audit et (imtahanın saxlanması ilə EYNİ tranzaksiyada) → ``AuditLog``."""
    from apps.audit.public import log_action
    from core.constants import AuditAction

    payload = decision.audit_payload()
    return log_action(
        action=AuditAction.UPDATE,
        user=user,
        organization=exam.organization,
        obj=exam,
        old_values=payload["old"],
        new_values=payload["new"],
        changes=payload,
        reason=reason,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(exam.pk),
        resource_repr=str(getattr(exam, "title", ""))[:500],
    )


def record_resync(exam, counts, *, decision_log_id, user=None) -> None:
    """Köçürmənin faktiki sayları (``on_commit`` — yenidən sinxrondan sonra). Best-effort."""
    from apps.audit.public import log_action
    from core.constants import AuditAction

    try:
        log_action(
            action=AuditAction.UPDATE,
            user=user,
            organization=exam.organization,
            obj=exam,
            changes={"decision": str(decision_log_id), "counts": {str(k): int(v) for k, v in dict(counts).items()}},
            reason="exam_subject_change_resync",
            resource_type=AUDIT_RESOURCE_RESYNC,
            resource_id=str(exam.pk),
            resource_repr=str(getattr(exam, "title", ""))[:500],
        )
    except Exception:  # noqa: BLE001 — sayların auditi köçürməni sındırmır (qərar sətri artıq yazılıb)
        logger.exception("exam_subject_change: resync audit failed for exam %s", getattr(exam, "pk", "?"))


def history(exam) -> list:
    """İmtahan səhifəsi üçün fənn dəyişikliyi tarixçəsi (yenidən köhnəyə) — siyahı dict-lər."""
    if not getattr(exam, "pk", None):
        return []
    from django.apps import apps as django_apps

    AuditLog = django_apps.get_model("audit", "AuditLog")
    rows = list(
        AuditLog.objects.filter(resource_type__in=(AUDIT_RESOURCE, AUDIT_RESOURCE_RESYNC), resource_id=str(exam.pk))
        .select_related("user")
        .order_by("-created_at")[:100]
    )
    resync = {}
    for row in rows:
        if row.resource_type == AUDIT_RESOURCE_RESYNC and isinstance(row.changes, dict):
            resync.setdefault(str(row.changes.get("decision") or ""), row.changes.get("counts") or {})
    out = []
    for row in rows:
        if row.resource_type != AUDIT_RESOURCE:
            continue
        changes = row.changes if isinstance(row.changes, dict) else {}
        counts = resync.get(str(row.pk))
        out.append(
            {
                "at": row.created_at,
                "user": (row.user.get_full_name() or row.user.username) if row.user else "—",
                "old_subject": (changes.get("old") or {}).get("subject") or "—",
                "new_subject": (changes.get("new") or {}).get("subject") or "—",
                "reason": row.reason,
                "students": changes.get("students_with_results") or 0,
                "moved": None if counts is None else int(counts.get("written", 0)) + int(counts.get("unchanged", 0)),
                "cleared": None if counts is None else int(counts.get("cleared", 0)),
                "not_enrolled": None if counts is None else int(counts.get("no_enrollment", 0)),
            }
        )
    return out


__all__ = [
    "AUDIT_RESOURCE",
    "AUDIT_RESOURCE_RESYNC",
    "CONFIRM_FIELD",
    "REASON_FIELD",
    "REASON_MIN_LENGTH",
    "Decision",
    "Snapshot",
    "decide",
    "history",
    "record_decision",
    "record_resync",
    "result_students",
    "subject_label",
    "take_snapshot",
    "validate_confirmation",
]
