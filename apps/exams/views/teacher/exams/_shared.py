"""teacher exams paketi — _shared."""

from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext, pgettext_lazy

from apps.exams.models import Exam
from apps.exams.views.shared.tenant import get_active_organization, tenant_scoped_exams
from apps.organizations.models import Organization
from core.helpers import _tenant_scoped_courses
from core.permissions import request_has_permission
from core.tenancy import request_has_active_organization_context, restore_request_organization_from_profile

from .constants import (
    DETAIL_QUESTION_MAX_PAGE_SIZE,
    DETAIL_QUESTION_PAGE_SIZE,
)


def _teacher_profile_my_exams_url():
    return f"{reverse('accounts:profile')}?section=my-exams"


def _safe_same_origin_redirect_path(request, candidate_url):
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""

    parsed = urlsplit(raw_url)
    if parsed.netloc and parsed.netloc != request.get_host():
        return ""

    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def _is_internal_exam_management_path(candidate_path):
    raw_path = (candidate_path or "").strip()
    if not raw_path:
        return False

    try:
        match = resolve(urlsplit(raw_path).path)
    except Resolver404:
        return False

    return match.namespace == "exams" and match.url_name in {
        "teacher_questions_bank",
        "test_question_bank",
        "create_question_bank",
        "add_exam_question",
        "edit_exam_question",
        "delete_exam_question",
        "teacher_exam_results",
        "teacher_view_attempt",
        "teacher_check_attempt",
    }


def _resolve_profile_navigation(request, *, default_section="my-exams"):
    requested_profile_section = (request.GET.get("from_section") or "").strip()
    valid_profile_sections = {
        "my-exams",
        "assigned-exams",
        "profile-info",
        "my-courses",
        "assigned-courses",
        "courses",
        "pending-review",
        "review-results",
    }
    if requested_profile_section not in valid_profile_sections:
        requested_profile_section = default_section

    fallback_profile_return_url = f"{reverse('accounts:profile')}?section={requested_profile_section}"
    explicit_return_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    referer_return_url = _safe_same_origin_redirect_path(request, request.META.get("HTTP_REFERER"))
    if _is_internal_exam_management_path(referer_return_url):
        referer_return_url = ""

    profile_return_url = explicit_return_url or referer_return_url or fallback_profile_return_url
    nav_params = {"from_section": requested_profile_section}
    if profile_return_url:
        nav_params["return_to"] = profile_return_url

    return profile_return_url, requested_profile_section, urlencode(nav_params)


def _is_superadmin(user):
    return user.is_superuser or getattr(user, "is_superadmin", False)


def _ensure_exam_permission(request, permission):
    if request_has_permission(request, permission):
        return
    raise PermissionDenied(
        pgettext("exams.view.exams.permission", "missing_required_permission").format(permission=permission)
    )


def _organization_selection_redirect(request):
    return redirect(f"{reverse('organizations:select')}?{urlencode({'next': request.get_full_path()})}")


def _restore_superadmin_profile_organization(request):
    if not _is_superadmin(getattr(request, "user", None)):
        return False
    return restore_request_organization_from_profile(request)


def _organization_selection_queryset():
    return Organization.objects.filter(is_active=True, status="active").order_by("name")


def _exam_detail_question_queryset(exam):
    return exam.questions.prefetch_related("options").order_by("order", "id")


def _positive_int(value, *, default, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        return default
    if maximum is not None:
        return min(parsed, maximum)
    return parsed


def _get_exam_detail_question_page(exam, *, offset=0, limit=DETAIL_QUESTION_PAGE_SIZE):
    offset = _positive_int(offset, default=0)
    limit = _positive_int(limit, default=DETAIL_QUESTION_PAGE_SIZE, maximum=DETAIL_QUESTION_MAX_PAGE_SIZE)
    limit = max(1, limit)
    fetched = list(_exam_detail_question_queryset(exam)[offset : offset + limit + 1])
    questions = fetched[:limit]
    return {
        "questions": questions,
        "has_more": len(fetched) > limit,
        "next_offset": offset + len(questions),
        "page_size": limit,
    }


def _resolve_selected_superadmin_organization(request):
    raw_organization_id = (request.POST.get("organization") or request.GET.get("organization") or "").strip()
    if not raw_organization_id.isdigit():
        return None

    return _organization_selection_queryset().filter(id=int(raw_organization_id)).first()


def _bind_selected_organization(request, organization):
    request.organization = organization
    request.org_memberships = []
    request.org_permissions = list(getattr(request, "org_permissions", []) or [])
    if hasattr(request, "session"):
        request.session["active_organization"] = organization.slug
    if hasattr(request.user, "set_active_organization_context"):
        request.user.set_active_organization_context(
            organization,
            memberships=request.org_memberships,
            permissions=request.org_permissions,
        )


def _resolve_required_organization(request):
    organization = get_active_organization(request)
    if organization is not None and request_has_active_organization_context(request):
        return organization

    if _restore_superadmin_profile_organization(request):
        organization = get_active_organization(request)
        if organization is not None and request_has_active_organization_context(request):
            return organization

    if not hasattr(request, "session"):
        raise PermissionDenied(
            pgettext("exams.view.exams.permission", "missing_required_permission").format(permission="organization")
        )

    messages.error(request, pgettext_lazy("exams.view.groups.message", "active_org_not_found"))
    return None


def _get_editable_exam_or_404(request, slug):
    exam = tenant_scoped_exams(request, Exam.objects.filter(slug=slug)).first()
    if exam is None:
        raise Http404

    if exam.author_id != request.user.id and not _is_superadmin(request.user):
        raise PermissionDenied(pgettext("exams.view.exams.permission", "not_exam_owner"))

    return exam


def _selected_access_entities(form):
    """Yalnız SEÇİLİ icazəli qrup/istifadəçiləri qaytarır (lazy render üçün).

    Böyük təşkilatlarda bütün variantları render etmək əvəzinə, server yalnız
    seçililəri göndərir; qalanları axtarış endpoint-ləri (group_search /
    user_search) debounce ilə gətirir. Nəticə forma sahələrinin queryset-inə
    görə scope olunur (təşkilat + icazə).
    """
    groups_field = form.fields.get("allowed_groups")
    users_field = form.fields.get("allowed_users")
    if not groups_field or not users_field:
        return [], []

    group_ids = []
    user_ids = []
    if form.is_bound:
        data = form.data
        group_ids = data.getlist("allowed_groups") if hasattr(data, "getlist") else []
        user_ids = data.getlist("allowed_users") if hasattr(data, "getlist") else []
    elif getattr(form.instance, "pk", None):
        group_ids = list(form.instance.allowed_groups.values_list("id", flat=True))
        user_ids = list(form.instance.allowed_users.values_list("id", flat=True))

    groups = list(groups_field.queryset.filter(id__in=group_ids)) if group_ids else []
    users = list(users_field.queryset.filter(id__in=user_ids)) if user_ids else []
    return groups, users


def _build_group_student_map(form):
    """
    İcazəli qruplardan icazəli istifadəçilərə xəritə qurur.
    Frontend bu xəritə ilə qrup seçiləndə uyğun tələbələri avtomatik seçir.
    """
    group_field = form.fields.get("allowed_groups")
    user_field = form.fields.get("allowed_users")
    if not group_field or not user_field:
        return {}

    allowed_user_ids = set(user_field.queryset.values_list("id", flat=True))
    group_student_map = {}
    group_qs = group_field.queryset.prefetch_related("students")

    for group in group_qs:
        member_ids = [student.id for student in group.students.all() if student.id in allowed_user_ids]
        group_student_map[str(group.id)] = [str(member_id) for member_id in member_ids]

    return group_student_map


def _get_requested_course_for_exam(request):
    raw_course_id = (
        request.POST.get("course_id") or request.GET.get("course") or request.GET.get("course_id") or ""
    ).strip()
    if not raw_course_id.isdigit():
        return None

    course = _tenant_scoped_courses(request).filter(id=int(raw_course_id)).first()
    if course is None:
        return None

    if course.owner_id == request.user.id:
        return course

    # M2 (2026-07-02): lazy lookup — exams→courses import kənarını kəsir.
    from django.apps import apps as django_apps

    CourseMembership = django_apps.get_model("courses", "CourseMembership")
    membership_exists = CourseMembership.objects.filter(
        course=course,
        user=request.user,
        role__in=["teacher", "assistant"],
    ).exists()
    return course if membership_exists else None
