"""İmtahan mərkəzinin QƏRAR açarı — rol auditi 2026-10-13 (B1).

Əvvəl ikinci şans, kollokvium/midterm pəncərəsi və sual göndərişi qərarları rol ADI ilə
(``is_exam_center_user``) açılırdı — imtahan mərkəzi işçisi və RİM əməkdaşı (alias
``core/roles.py``) da qərar verirdi. Şablon isə əməkdaş üçün «görür və köməklik edir,
dəyişdirmir» deyir. İndi bölmələr mərkəz istifadəçisinə GÖRÜNÜR (yalnız-oxu), qərar əməlləri
``exam_center.decide`` açarı ilə (şablonda rəhbərdə; ``ikt_rehber``/rektor ``*`` ilə).

Açar sətri burada lokal saxlanılır (``organizations.permissions_role_audit`` xüsusi moduldur —
cross-app private import qapısı, bax ``scripts/public_api_boundaries.py``).
"""

from apps.exams.public import is_exam_center_user
from core.permissions import is_superadmin_user, request_has_permission

PERM_EXAM_CENTER_DECIDE = "exam_center.decide"


def can_exam_center_decide(request):
    """Mərkəz istifadəçisi + ``exam_center.decide`` (superadmin cross-org da keçir)."""
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False) or not is_exam_center_user(user):
        return False
    return is_superadmin_user(user) or request_has_permission(request, PERM_EXAM_CENTER_DECIDE)


__all__ = ["PERM_EXAM_CENTER_DECIDE", "can_exam_center_decide"]
