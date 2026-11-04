"""attempt_reset — kim sıfırlaya bilər və səbəb qaydası (sahib 2026-11-04).

Sahib: «səbəb yazaraq yalnız RİM rəhbəri və imtahan mərkəzi rəhbəri silə bilsin». Rol bayrağı
``is_exam_center_head`` məhz bu iki rolu (``exam_center_head`` + köhnə ``exam_center`` alias-ı və
``ikt_rehber`` = RİM rəhbəri) əhatə edir; İŞÇİLƏR (``exam_center_staff``, ``rim_staff``) və müəllim
(imtahanın müəllifi olsa belə) DAXİL DEYİL. Superadmin də icazəlidir. Rol aktiv təşkilat üzərindən
oxunur — başqa tenant-ın imtahanı heç vaxt bu yolla açılmır.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from core.roles import is_superadmin_user

#: Səbəbin minimal uzunluğu (boşluqlar kəsildikdən sonra) — «səhv» kimi tək sözlü səbəb qəbul olunmur.
REASON_MIN_LENGTH = 10
REASON_MAX_LENGTH = 500


class ResetReasonError(ValueError):
    """Səbəb boşdur / çox qısadır — heç nə yazılmır."""


def can_reset_exam_attempts(user, organization) -> bool:
    """RİM rəhbəri / imtahan mərkəzi rəhbəri (aktiv təşkilat = imtahanın təşkilatı) və ya superadmin."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if is_superadmin_user(user):
        return True
    if organization is None:
        return False
    active = getattr(user, "active_organization", None)
    if active is None or getattr(active, "pk", None) != getattr(organization, "pk", None):
        return False
    return bool(getattr(user, "is_exam_center_head", False))


def clean_reason(raw) -> str:
    """Səbəbi normallaşdır (boşluqlar sıxılır) və yoxla → ``ResetReasonError``."""
    reason = " ".join(str(raw or "").split())
    if not reason:
        raise ResetReasonError(pgettext("exams.attempt_reset", "Səbəb mütləqdir."))
    if len(reason) < REASON_MIN_LENGTH:
        raise ResetReasonError(
            pgettext("exams.attempt_reset", "Səbəb ən azı %(n)s simvol olmalıdır.") % {"n": REASON_MIN_LENGTH}
        )
    return reason[:REASON_MAX_LENGTH]


__all__ = [
    "REASON_MAX_LENGTH",
    "REASON_MIN_LENGTH",
    "ResetReasonError",
    "can_reset_exam_attempts",
    "clean_reason",
]
