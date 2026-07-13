"""
Apellyasiya icazə məntiqi — mərkəzi RBAC üzərində.

- create:  student yalnız ÖZ bitmiş attempt-i üçün, pəncərə açıqdırsa,
           ``appeal.create`` icazəsi ilə.
- respond/decide: apellyasiyalar mərkəzləşdirilmiş qaydada imtahan mərkəzi
           tərəfindən idarə olunur. İmtahan mərkəzi bu platformada imtahan
           məzmununu da mərkəzi olaraq yaradır, ona görə öz yaratdığı imtahana
           gələn apellyasiyaya da qərar verə bilir (müstəqillik qadağası yoxdur
           — imtahan mərkəzi rolu onsuz da tək qərar səlahiyyətidir).

Bütün hallarda tenant uyğunluğu yoxlanılır (superadmin istisna).
"""

from apps.appeals.constants import PERM_APPEAL_CREATE
from apps.exams.public import is_exam_center_user
from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import get_request_organization

from .window import is_within_appeal_window


def _same_tenant(request, appeal):
    if is_superadmin_user(getattr(request, "user", None)):
        return True
    organization = get_request_organization(request)
    return organization is not None and appeal.organization_id == organization.id


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
    """Apellyasiyaya baxıb item-lərə cavab verə bilərmi (imtahan mərkəzi).

    İmtahan mərkəzi istifadəçisi (və superadmin) təşkilatının bütün
    apellyasiyalarına — öz yaratdığı imtahanlar daxil — baxa bilir.
    """
    if not _same_tenant(request, appeal):
        return False
    return is_exam_center_user(getattr(request, "user", None))


def can_decide_appeal(request, appeal):
    """Yekun status qərarı / override verə bilərmi (imtahan mərkəzi).

    İmtahan mərkəzi bu platformada mərkəzi qərar səlahiyyətidir; imtahan
    müəllifi eyni zamanda mərkəz istifadəçisidirsə də qərar verə bilir.
    """
    if not _same_tenant(request, appeal):
        return False
    return is_exam_center_user(getattr(request, "user", None))


__all__ = [
    "can_create_appeal",
    "can_decide_appeal",
    "can_review_appeal",
]
