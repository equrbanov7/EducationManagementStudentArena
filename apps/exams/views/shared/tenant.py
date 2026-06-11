from django.shortcuts import get_object_or_404

from apps.exams.features import without_disabled_practical_exams
from apps.exams.models import Exam
from core.tenancy import (
    get_request_organization,
    request_has_active_organization_context,
    restore_request_organization_from_profile,
    scoped_by_organization,
)


def get_active_organization(request):
    return get_request_organization(request)


def tenant_scoped_exams(request, queryset=None):
    base_queryset = queryset if queryset is not None else Exam.objects.all()
    return without_disabled_practical_exams(scoped_by_organization(base_queryset, request))


def ensure_teacher_exam_tenant_context(request):
    """
    Sessiya aktiv org-u itirəndə tenant kontekstini bərpa et.

    ``ensure_student_exam_tenant_context``-in müəllim tərəfi üçün analoqu.
    Bərpa yalnız istifadəçinin həqiqətən aid olduğu YEGANƏ aktiv org üçün
    işləyir (bax: ``restore_request_organization_from_profile``) — tenant
    izolyasiyası pozulmur. Bu olmadan sual edit/delete kimi view-lar
    sessiya org-u düşəndə ``scoped_by_organization → queryset.none()``
    səbəbindən aralıqlı 404 verirdi (RLS GUC da bərpa olunur).
    """
    if request_has_active_organization_context(request):
        return True
    return restore_request_organization_from_profile(
        request,
        profile=getattr(getattr(request, "user", None), "profile", None),
    )


def get_teacher_exam_or_404(request, **filters):
    ensure_teacher_exam_tenant_context(request)
    teacher_queryset = tenant_scoped_exams(request, Exam.objects.filter(author=request.user))
    return get_object_or_404(teacher_queryset, **filters)


def exam_in_active_tenant(request, exam):
    organization = get_active_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return False

    return getattr(exam, "organization", None) == organization
