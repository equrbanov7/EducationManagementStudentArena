from django.shortcuts import get_object_or_404

from apps.exams.models import Exam
from core.tenancy import get_request_organization, request_has_active_organization_context, scoped_by_organization


def get_active_organization(request):
    return get_request_organization(request)


def tenant_scoped_exams(request, queryset=None):
    base_queryset = queryset if queryset is not None else Exam.objects.all()
    return scoped_by_organization(base_queryset, request)


def get_teacher_exam_or_404(request, **filters):
    teacher_queryset = tenant_scoped_exams(request, Exam.objects.filter(author=request.user))
    return get_object_or_404(teacher_queryset, **filters)


def exam_in_active_tenant(request, exam):
    organization = get_active_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return False

    return getattr(exam, "organization", None) == organization
