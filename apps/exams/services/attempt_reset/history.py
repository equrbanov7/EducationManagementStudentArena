"""attempt_reset — imtahan üzrə silinmiş / sıfırlanmış cəhdlərin tarixçəsi (audit sətirlərindən).

Mənbə: ``AuditLog`` (``resource_type = exam_attempt_purge.AUDIT_RESOURCE_TYPE``, ``changes.exam_id``). Həm
veb «cəhdi sıfırla» (``verb=reset_exam_attempt`` — icraçı + əvvəlki ballar), həm də köhnə
``purge_exam_attempt`` idarə əmri (icraçı «Sistem») sətirləri görünür. Yeni məlumat saxlanmır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils.translation import pgettext

from apps.exams.services.exam_attempt_purge import AUDIT_RESOURCE_TYPE
from apps.exams.services.trial_exam_purge import _model

HISTORY_LIMIT = 50


def _display(user) -> str:
    return (user.get_full_name() or user.username) if user is not None else ""


def exam_reset_history(exam, *, limit=HISTORY_LIMIT) -> list[dict]:
    """Ən yenisi əvvəl: vaxt, icraçı, səbəb, tələbə, cəhd id-si, əvvəlki ballar, yenidən açılmış bilet sayı."""
    rows = list(
        _model("audit.AuditLog")
        .objects.filter(
            resource_type=AUDIT_RESOURCE_TYPE,
            organization_id=exam.organization_id,
            changes__exam_id=exam.pk,
        )
        .select_related("user")
        .order_by("-created_at")[:limit]
    )
    student_ids = {(row.changes or {}).get("student_id") for row in rows} - {None}
    students = {user.pk: user for user in get_user_model().objects.filter(pk__in=student_ids)}
    system = pgettext("exams.attempt_reset", "Sistem")
    history = []
    for row in rows:
        changes = row.changes or {}
        student = students.get(changes.get("student_id"))
        history.append(
            {
                "time": row.created_at,
                "actor": _display(row.user) or system,
                "reason": row.reason,
                "student": _display(student) or changes.get("student_username") or "—",
                "attempt_id": (row.old_values or {}).get("attempt_id") or row.resource_id,
                "verb": changes.get("verb", ""),
                "scores": changes.get("scores_before") or {},
                "tickets_reset": len(changes.get("ticket_ids") or ()),
            }
        )
    return history


__all__ = ["HISTORY_LIMIT", "exam_reset_history"]
