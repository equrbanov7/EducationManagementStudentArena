"""
Apellyasiya icazə məntiqi — mərkəzi RBAC üzərində.

- create:  student yalnız ÖZ bitmiş attempt-i üçün, pəncərə açıqdırsa,
           ``appeal.create`` icazəsi ilə.
- respond: məsul müəllim (imtahan müəllifi) ``appeal.respond`` ilə, və ya
           ``appeal.decide`` icazəli yuxarı rol.
- decide:  ``appeal.decide`` icazəli rol (yekun qərar/override).

Bütün hallarda tenant uyğunluğu yoxlanılır (superadmin istisna).
"""

from apps.appeals.constants import PERM_APPEAL_CREATE, PERM_APPEAL_DECIDE, PERM_APPEAL_RESPOND
from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import get_request_organization

from .window import is_within_appeal_window


def _same_tenant(request, appeal):
    if is_superadmin_user(getattr(request, "user", None)):
        return True
    organization = get_request_organization(request)
    return organization is not None and appeal.organization_id == organization.id


def _is_exam_author(request, appeal):
    user = getattr(request, "user", None)
    return bool(user and getattr(appeal.exam, "author_id", None) == getattr(user, "id", None))


def can_create_appeal(request, attempt, *, at_time=None):
    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return False
    if attempt.user_id != getattr(user, "id", None):
        return False
    if not is_within_appeal_window(attempt, at_time=at_time):
        return False
    return request_has_permission(request, PERM_APPEAL_CREATE)


def can_review_appeal(request, appeal):
    """Apellyasiyaya baxıb item-lərə cavab verə bilərmi (respond)."""
    if not _same_tenant(request, appeal):
        return False
    if is_superadmin_user(getattr(request, "user", None)):
        return True
    if _is_exam_author(request, appeal) and request_has_permission(request, PERM_APPEAL_RESPOND):
        return True
    return request_has_permission(request, PERM_APPEAL_DECIDE)


def can_decide_appeal(request, appeal):
    """Yekun status qərarı / override verə bilərmi (decide)."""
    if not _same_tenant(request, appeal):
        return False
    if is_superadmin_user(getattr(request, "user", None)):
        return True
    return request_has_permission(request, PERM_APPEAL_DECIDE)


__all__ = [
    "can_create_appeal",
    "can_decide_appeal",
    "can_review_appeal",
]
