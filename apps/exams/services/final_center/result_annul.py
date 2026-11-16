"""final_center — imtahan nəticəsinin ləğvi (sahib 2026-11-16).

Sahib: «imtahandan uzaqlaşdırılmış tələbələrin midterm nəticəsi ləğv olmalıdır, qeyd kimi də düşməlidir»;
«bəzən nəzarətçi uzaqlaşdırana kimi tələbə “Bitir” vurur, bal sistemə düşür — o balı izahat yazılaraq ləğv
etmək, “köçürdü” və ya başqa səbəb kimi qeyd etmək olmalıdır».

Ləğv = cəhd ``supervision_status="removed"`` olur (jurnal körpüsü artıq bunu 0 bal kimi yazır — midterm də,
final də), səbəb + izahat ``SupervisionIncident`` (``teacher_action="result_annulled"``) kimi saxlanılır və
tələbəyə nəticə səhifəsində «Nəticəniz ləğv olunub» qeydi ilə göstərilir. Cəhd SİLİNMİR (cavablar qalır).
"""

from django.db import transaction
from django.utils.translation import pgettext, pgettext_lazy

from apps.exams.models import SupervisionIncident
from core.audit import log_action
from core.constants import AuditAction

from .tickets import TicketStateError

ANNUL_ACTION = "result_annulled"
ANNUL_REMOVED = "removed"
ANNUL_CHEATING = "cheating"
ANNUL_OTHER = "other"

ANNUL_REASONS = (
    (ANNUL_REMOVED, pgettext_lazy("exams.final_center.annul", "İmtahandan uzaqlaşdırıldığına görə")),
    (ANNUL_CHEATING, pgettext_lazy("exams.final_center.annul", "Köçürmə")),
    (ANNUL_OTHER, pgettext_lazy("exams.final_center.annul", "Digər səbəb")),
)
_REASON_LABELS = dict(ANNUL_REASONS)


def reason_label(key: str) -> str:
    return str(_REASON_LABELS.get(key, key or ""))


def annul_incident(attempt):
    """Cəhdin ləğv qeydi (ən sonuncu) və ya ``None``."""
    return (
        SupervisionIncident.objects.filter(attempt_id=attempt.pk, teacher_action=ANNUL_ACTION)
        .order_by("-timestamp", "-id")
        .first()
    )


def is_annulled(attempt) -> bool:
    return SupervisionIncident.objects.filter(attempt_id=attempt.pk, teacher_action=ANNUL_ACTION).exists()


def annul_attempt_result(attempt, by, *, reason_key: str, note: str, request=None, sync_journal: bool = True) -> bool:
    """Bitmiş cəhdin nəticəsini ləğv et → ``True`` (yeni ləğv) / ``False`` (artıq ləğv olunub).

    İzahat MƏCBURİDİR. Cəhd bitməyibsə — əvvəlcə tələbə imtahandan çıxarılmalıdır (``remove_student``).
    """
    note = (note or "").strip()
    if reason_key not in _REASON_LABELS:
        raise TicketStateError(pgettext("exams.final_center.error", "Ləğv səbəbi seçilməyib."))
    if not note:
        raise TicketStateError(pgettext("exams.final_center.error", "İzahat yazılmadan nəticə ləğv edilə bilməz."))
    if attempt is None:
        raise TicketStateError(pgettext("exams.final_center.error", "Bu biletdə imtahan cəhdi yoxdur."))
    if getattr(attempt, "is_trial", False):
        raise TicketStateError(pgettext("exams.final_center.error", "Sınaq cəhdinin nəticəsi jurnala düşmür."))
    if not attempt.is_finished:
        raise TicketStateError(
            pgettext("exams.final_center.error", "İmtahan hələ davam edir — əvvəlcə tələbəni imtahandan çıxarın.")
        )
    if is_annulled(attempt):
        return False

    label = reason_label(reason_key)
    display_reason = f"{label}: {note}"[:1000]
    with transaction.atomic():
        old_status = attempt.supervision_status
        if old_status != "removed":
            attempt.supervision_status = "removed"
            attempt.save(update_fields=["supervision_status"])
        SupervisionIncident.objects.create(
            organization=attempt.exam.organization,
            exam=attempt.exam,
            attempt=attempt,
            student=attempt.user,
            event_type="auto_submitted",
            severity="critical",
            metadata={
                "teacher_id": getattr(by, "pk", None),
                "teacher_username": getattr(by, "username", ""),
                "previous_status": old_status,
                "reason": ANNUL_ACTION,
                "reason_key": reason_key,
                "note": note[:1000],
                "display_reason": display_reason,
                "intervention_action": "annulled",
            },
            violation_count_at_time=attempt.supervision_violation_count,
            teacher_action=ANNUL_ACTION,
        )
        log_action(
            AuditAction.UPDATE,
            user=by,
            organization=attempt.exam.organization,
            obj=attempt,
            old_values={"supervision_status": old_status},
            new_values={"supervision_status": "removed", "annulled": True, "reason_key": reason_key},
            reason=f"exam_result_annulled[{reason_key}]: {note}"[:500],
            request=request,
            resource_type="exams.ExamAttempt",
            resource_id=str(attempt.pk),
            resource_repr=getattr(attempt.exam, "title", ""),
        )
    if sync_journal:
        from apps.exams.services.journal_sync import sync_attempt_to_journal

        sync_attempt_to_journal(attempt, actor=by)  # 0 bal (qovulma qaydası); heç vaxt istisna atmır
    return True


__all__ = [
    "ANNUL_ACTION",
    "ANNUL_CHEATING",
    "ANNUL_OTHER",
    "ANNUL_REASONS",
    "ANNUL_REMOVED",
    "annul_attempt_result",
    "annul_incident",
    "is_annulled",
    "reason_label",
]
