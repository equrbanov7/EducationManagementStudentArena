"""Müəllimin oxşarlıq qərarı: «plagiat deyil» (dismiss) və geri qaytarma.

Uyğunluq sətri SİLİNMİR — yalnız ``dismissed_*`` sahələri dolur və bayraq
keşi (``plagiarism_flagged`` / ``similarity_max``) yenidən qurulur. Qərarı
cütün İSTƏNİLƏN tərəfinin qrupunu yoxlaya bilən müəllim (və ya qovluq sahibi)
verə bilər.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from ...constants import MAX_FEEDBACK_CHARS
from ...errors import FolderError
from .. import access
from ..events import audit_change
from .engine import refresh_flags


def _ensure_can_decide(user, match) -> None:
    for submission in (match.submission_a, match.submission_b):
        assignment = submission.assignment
        if access.can_review_assignment(user, assignment) or access.can_manage_folder(user, assignment.folder):
            return
    raise FolderError.of("permission.not_reviewer")


@transaction.atomic
def dismiss_match(match, *, by_user, note: str = "", request=None):
    _ensure_can_decide(by_user, match)
    note = str(note or "").strip()
    if len(note) > MAX_FEEDBACK_CHARS:
        raise FolderError.of("text.too_long", max=MAX_FEEDBACK_CHARS)
    match.dismissed_at = timezone.now()
    match.dismissed_by = by_user
    match.dismiss_note = note[:500]
    match.save(update_fields=["dismissed_at", "dismissed_by", "dismiss_note", "updated_at"])
    refresh_flags([match.submission_a_id, match.submission_b_id])
    audit_change(match, actor=by_user, changes={"dismissed": True, "note": match.dismiss_note}, request=request)
    return match


@transaction.atomic
def restore_match(match, *, by_user, request=None):
    _ensure_can_decide(by_user, match)
    match.dismissed_at = None
    match.dismissed_by = None
    match.dismiss_note = ""
    match.save(update_fields=["dismissed_at", "dismissed_by", "dismiss_note", "updated_at"])
    refresh_flags([match.submission_a_id, match.submission_b_id])
    audit_change(match, actor=by_user, changes={"dismissed": False}, request=request)
    return match


__all__ = ["dismiss_match", "restore_match"]
