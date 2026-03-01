from django.shortcuts import get_object_or_404

from apps.exams.models import Exam
from core.tenancy import get_organization_int_id, get_request_organization, scoped_by_organization_id


def get_active_organization(request):
    return get_request_organization(request)


def tenant_scoped_exams(request, queryset=None):
    base_queryset = queryset if queryset is not None else Exam.objects.all()
    return scoped_by_organization_id(
        base_queryset,
        request,
        org_id_field="organization_id",
        fallback_org_field="author__profile__organization",
    )


def get_teacher_exam_or_404(request, **filters):
    teacher_queryset = tenant_scoped_exams(request, Exam.objects.filter(author=request.user))
    return get_object_or_404(teacher_queryset, **filters)


def exam_in_active_tenant(request, exam):
    organization = get_active_organization(request)
    if organization is None:
        return True

    org_int_id = get_organization_int_id(organization)
    exam_org_id = getattr(exam, "organization_id", None)
    if exam_org_id is not None:
        if org_int_id is None:
            return False
        return exam_org_id == org_int_id

    author_org = getattr(getattr(getattr(exam, "author", None), "profile", None), "organization", None)
    return author_org == organization
