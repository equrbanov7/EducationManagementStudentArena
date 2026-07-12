"""
Apellyasiya icazə məntiqi — mərkəzi RBAC üzərində.

- create:  student yalnız ÖZ bitmiş attempt-i üçün, pəncərə açıqdırsa,
           ``appeal.create`` icazəsi ilə.
- respond/decide: apellyasiyalar mərkəzləşdirilmiş qaydada imtahan mərkəzi
           tərəfindən idarə olunur.

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


def _is_conflicted_reviewer(request, appeal):
    """Reviewer independence (EXAM-P1-18): imtahanın müəllifi öz imtahanına
    qarşı apellyasiyaya baxa/qərar verə bilməz — öz qiymətini müdafiə edən
    şəxs müstəqil reviewer ola bilməz. Superadmin bu qadağadan azaddır (audit
    məqsədləri üçün). Müəllif tapılmasa (məlumatsız) konservativ davranıb
    konflikt saymırıq ki, legitim mərkəz axını pozulmasın."""
    user = getattr(request, "user", None)
    if is_superadmin_user(user):
        return False
    user_id = getattr(user, "id", None)
    if user_id is None:
        return False
    # İmtahan müəllifi öz imtahanına baxa bilməz.
    author_id = getattr(getattr(appeal, "exam", None), "author_id", None)
    if author_id is not None and author_id == user_id:
        return True
    # İlk manual qiymətləndirən müəllim də öz qiymətinə baxan reviewer ola bilməz.
    graded_by_id = getattr(getattr(appeal, "attempt", None), "graded_by_id", None)
    return graded_by_id is not None and graded_by_id == user_id


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
    """Apellyasiyaya baxıb item-lərə cavab verə bilərmi (imtahan mərkəzi)."""
    if not _same_tenant(request, appeal):
        return False
    if _is_conflicted_reviewer(request, appeal):
        return False
    return is_exam_center_user(getattr(request, "user", None))


def can_decide_appeal(request, appeal):
    """Yekun status qərarı / override verə bilərmi (imtahan mərkəzi)."""
    if not _same_tenant(request, appeal):
        return False
    if _is_conflicted_reviewer(request, appeal):
        return False
    return is_exam_center_user(getattr(request, "user", None))


def can_view_appeal_managed(request, appeal):
    """Apellyasiya detalını READ-ONLY aça bilərmi (idarəetmə səthində).

    Reviewer-independence (EXAM-P1-18) QƏRARI bloklayır, BAXIŞI yox: imtahan
    mərkəzi istifadəçisi öz imtahanına (müəllif/qiymətləndirən kimi konflikt)
    apellyasiyada QƏRAR verə bilməz, amma məzmununu GÖRMƏLİDİR — əks halda
    reviewer siyahısındakı "Bax" generik "Yüklənmə alınmadı" xətası verirdi.
    Qeyri-mərkəz istifadəçilərə (adi müəllim) idarəetmə səthi bağlı qalır —
    onlar apellyasiyanı yalnız öz standart detal görünüşündən açır.
    """
    if not _same_tenant(request, appeal):
        return False
    return is_exam_center_user(getattr(request, "user", None))


__all__ = [
    "can_create_appeal",
    "can_decide_appeal",
    "can_review_appeal",
    "can_view_appeal_managed",
]
