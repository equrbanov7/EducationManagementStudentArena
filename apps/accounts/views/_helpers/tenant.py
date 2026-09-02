"""
Tenant scoping helpers.

Resolve the active organization, bind active-role context to a user, and
scope course/exam querysets to the request's organization (tenant isolation).
"""

from apps.courses.models import Course
from apps.exams.models import Exam
from apps.exams.public import without_disabled_practical_exams
from core.tenancy import get_request_organization, scoped_by_organization

from ...queries import get_assigned_courses_for_user, get_assigned_exams_for_user


def _get_active_organization(request):
    """
    Use middleware-selected organization first; fallback to profile organization.
    """
    return get_request_organization(request)


def _bind_active_role_context(user, organization, *, memberships=None, permissions=None):
    if user and hasattr(user, "set_active_organization_context"):
        user.set_active_organization_context(
            organization,
            memberships=memberships,
            permissions=permissions,
        )
    return user


def _tenant_scoped_courses(request, queryset=None):
    base_queryset = queryset if queryset is not None else Course.objects.all()
    return scoped_by_organization(base_queryset, request)


def _tenant_scoped_exams(request, queryset=None, *, include_deleted=False):
    """Org-scoped imtahan queryset — default olaraq yumşaq silinmiş (``is_deleted``)
    imtahanları çıxarır. Bax: ``apps.exams.views.shared.tenant.tenant_scoped_exams``."""
    base_queryset = queryset if queryset is not None else Exam.objects.all()
    scoped = without_disabled_practical_exams(scoped_by_organization(base_queryset, request))
    if not include_deleted:
        scoped = scoped.filter(is_deleted=False)
    return scoped


def _assigned_courses_queryset(request, user):
    return _tenant_scoped_courses(request, get_assigned_courses_for_user(user))


def _assigned_exams_queryset(request, user, *, active_only=True):
    return _tenant_scoped_exams(
        request,
        get_assigned_exams_for_user(user, active_only=active_only, include_public=False),
    ).distinct()


def _resolve_superadmin_target_org(request, *, query_param: str):
    """Superadmin üçün hədəf təşkilat — id AKTİV təşkilatlar içində VALİDASİYA olunur.

    2026-09-02 audit, P2-3: ``kollokvium_windows`` və ``journal_close``
    ``organization_id``-ni birbaşa ``request.POST``-dan götürüb
    ``Organization.objects.filter(pk=org_id)`` yazırdı.  İki problem:

    * **IDOR forması** — id yalnız superadmin yolunda oxunsa da, gövdədən gələn
      identifikatorun heç bir yoxlanışı yox idi (ikinci tenant provizioned
      olan kimi bu, canlı riskə çevrilir);
    * **kobud giriş** — UUID olmayan mətn ``ValidationError`` ilə 500 verirdi.

    İndi: superadmin deyilsə HƏMİŞƏ aktiv-təşkilat konteksti; superadmin üçün
    id təhlükəsiz parse olunur və yalnız AKTİV təşkilatlar arasından seçilir,
    tapılmasa aktiv kontekstə, o da yoxdursa ilk aktiv təşkilata düşür.
    """
    from django.core.exceptions import ValidationError

    from apps.organizations.models import Organization
    from core.permissions import is_superadmin_user

    if not is_superadmin_user(getattr(request, "user", None)):
        return _get_active_organization(request)

    raw = (request.POST.get("organization_id") or request.GET.get(query_param) or "").strip()
    if raw:
        try:
            organization = Organization.objects.filter(pk=raw, is_active=True).first()
        except (ValidationError, ValueError, TypeError):
            organization = None
        if organization is not None:
            return organization
    return _get_active_organization(request) or Organization.objects.filter(is_active=True).order_by("name").first()
