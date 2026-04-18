from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext, pgettext_lazy

from apps.courses.models import CourseMembership
from apps.exams.forms import ExamForm
from apps.exams.models import Exam
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.views.shared.tenant import get_active_organization, get_teacher_exam_or_404, tenant_scoped_exams
from apps.organizations.models import Organization
from core.helpers import _tenant_scoped_courses
from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import (
    get_request_organization,
    request_has_active_organization_context,
    restore_request_organization_from_profile,
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

    membership_exists = CourseMembership.objects.filter(
        course=course,
        user=request.user,
        role__in=["teacher", "assistant"],
    ).exists()
    return course if membership_exists else None


@login_required
def teacher_exam_list(request):
    """
    Legacy /exams/ entry point.
    Teacher exam list now lives inside the profile "my-exams" section.
    """
    return redirect(_teacher_profile_my_exams_url())


# ((sonra adını teacher_exam_create / teacher_exam_edit edərsən))


@login_required
def createAndEditExamView(request, slug=None):
    """
    Birləşdirilmiş view: Create və Edit
    slug=None -> Yeni imtahan
    slug=<value> -> Mövcud imtahanı redaktə
    """
    is_editing = slug is not None
    allow_organization_selection = False

    if not is_editing and is_superadmin_user(request.user) and get_request_organization(request) is None:
        _restore_superadmin_profile_organization(request)
        organization = get_active_organization(request)
        if organization is None or not request_has_active_organization_context(request):
            organization = None
            allow_organization_selection = True
    else:
        organization = _resolve_required_organization(request)
        if organization is None:
            return _organization_selection_redirect(request)

    _ensure_teacher(request.user)

    required_permission = "exam.edit" if slug else "exam.create"
    permission_verified = False
    if organization is not None:
        _ensure_exam_permission(request, required_permission)
        permission_verified = True

    # Əgər slug varsa -> Edit mode
    if slug:
        exam = _get_editable_exam_or_404(request, slug)
    else:
        exam = None
    linked_course = None if is_editing else _get_requested_course_for_exam(request)
    is_modal_request = request.GET.get("modal") == "1" or request.POST.get("modal") == "1"

    # Load existing supervision config for edit mode
    supervision_config = None
    if is_editing and exam:
        try:
            supervision_config = exam.supervision_config
        except Exception:
            pass

    selected_organization = _resolve_selected_superadmin_organization(request) if allow_organization_selection else None
    form_organization = organization or selected_organization
    form_kwargs = {
        "user": request.user,
        "organization": form_organization,
    }
    if allow_organization_selection:
        form_kwargs["allow_organization_selection"] = True
        form_kwargs["organization_queryset"] = _organization_selection_queryset()
        form_kwargs["initial_organization"] = selected_organization

    if request.method == "POST":
        previous_is_active = exam.is_active if is_editing else False
        previous_recipient_ids = set()
        if is_editing and exam is not None:
            from apps.notifications.services import get_exam_assigned_user_ids

            previous_recipient_ids = get_exam_assigned_user_ids(exam)

        if is_editing:
            # Edit mode
            form = ExamForm(request.POST, instance=exam, **form_kwargs)
        else:
            # Create mode
            form = ExamForm(request.POST, **form_kwargs)

        if form.is_valid():
            if organization is None and allow_organization_selection:
                organization = form.cleaned_data.get("organization")
                if organization is not None:
                    _bind_selected_organization(request, organization)
                    form_organization = organization

            if organization is None:
                raise PermissionDenied(
                    pgettext("exams.view.exams.permission", "missing_required_permission").format(
                        permission="organization"
                    )
                )

            if not permission_verified:
                _ensure_exam_permission(request, required_permission)
                permission_verified = True

            if not is_editing and linked_course is None:
                linked_course = _get_requested_course_for_exam(request)

            exam_instance = form.save(commit=False)

            # Yeni imtahanda author-u set et
            if not is_editing:
                exam_instance.author = request.user
                if linked_course is not None:
                    exam_instance.course = linked_course
            exam_instance.organization = organization

            exam_instance.save()
            form.save_m2m()  # ManyToMany field-ləri saxla

            # Save supervision config from POST data
            from apps.exams.services.supervision import save_supervision_config_from_form

            save_supervision_config_from_form(exam_instance, request.POST)

            from apps.notifications.services import get_exam_assigned_user_ids, notify_task_assignment

            current_recipient_ids = get_exam_assigned_user_ids(exam_instance)
            should_notify_all = not previous_is_active and exam_instance.is_active
            new_recipient_ids = (
                current_recipient_ids if should_notify_all else (current_recipient_ids - previous_recipient_ids)
            )
            if new_recipient_ids and exam_instance.is_active:
                notify_task_assignment(
                    task=exam_instance,
                    user_ids=new_recipient_ids,
                    task_kind="exam",
                )

            from apps.audit.utils import log_action
            from core.constants import AuditAction

            log_action(
                action=AuditAction.UPDATE if is_editing else AuditAction.CREATE,
                user=request.user,
                organization=organization,
                obj=exam_instance,
                new_values={"title": exam_instance.title, "is_active": str(exam_instance.is_active)},
                reason="exam_updated" if is_editing else "exam_created",
                request=request,
            )

            # Invalidate cached exam metadata so subsequent reads are fresh.
            try:
                from core.cache import invalidate_exam_metadata_cache

                invalidate_exam_metadata_cache(exam_instance.pk)
            except Exception:
                pass

            messages.success(
                request,
                (
                    pgettext_lazy("exams.view.exams.message", "exam_updated")
                    if is_editing
                    else pgettext_lazy("exams.view.exams.message", "exam_created")
                ),
            )
            if is_modal_request:
                return JsonResponse({"success": True, "slug": exam_instance.slug})
            return redirect("exams:teacher_exam_detail", slug=exam_instance.slug)
        group_student_map = _build_group_student_map(form)
        if is_modal_request:
            html = render_to_string(
                "exams/teacher/partials/_create_exam_modal_form.html",
                {
                    "form": form,
                    "is_editing": is_editing,
                    "exam": exam,
                    "linked_course": linked_course,
                    "group_student_map": group_student_map,
                    "supervision_config": supervision_config,
                },
                request=request,
            )
            return JsonResponse({"success": False, "html": html}, status=400)
    else:
        # GET request
        if is_editing:
            form = ExamForm(instance=exam, **form_kwargs)
        else:
            form = ExamForm(**form_kwargs)
    group_student_map = _build_group_student_map(form)

    if is_modal_request:
        return render(
            request,
            "exams/teacher/partials/_create_exam_modal_form.html",
            {
                "form": form,
                "exam": exam,
                "is_editing": is_editing,
                "linked_course": linked_course,
                "group_student_map": group_student_map,
                "supervision_config": supervision_config,
            },
        )

    return render(
        request,
        "exams/teacher/createAndEditExam.html",
        {
            "form": form,
            "exam": exam,
            "is_editing": is_editing,
            "linked_course": linked_course,
            "group_student_map": group_student_map,
            "supervision_config": supervision_config,
        },
    )


@login_required
def teacher_exam_detail(request, slug):
    """
    Müəllim üçün konkret imtahanın detal səhifəsi:
    - məlumat
    - suallar
    - 'Sual əlavə et' düyməsi
    (sonra bura statistikalar, attempts və s. də əlavə ediləcək).
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    questions = exam.questions.all().order_by("order")
    profile_return_url, _, nav_query = _resolve_profile_navigation(request, default_section="my-exams")
    exam_back_label = pgettext("exams.template.teacher_exam_detail", "action_back")

    return render(
        request,
        "exams/teacher/teacher_exam_detail.html",
        {
            "exam": exam,
            "questions": questions,
            "profile_return_url": profile_return_url,
            "exam_navigation_query": nav_query,
            "exam_back_label": exam_back_label,
        },
    )


@login_required
def toggle_exam_active(request, slug):
    """
    Müəllim imtahanı istənilən vaxt aktiv/deaktiv edə bilsin.
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    _ensure_exam_permission(request, "exam.edit")
    exam = get_teacher_exam_or_404(request, slug=slug)

    if request.method == "POST":
        exam.is_active = not exam.is_active
        exam.save()
        if exam.is_active:
            from apps.notifications.services import get_exam_assigned_user_ids, notify_task_assignment

            notify_task_assignment(
                task=exam,
                user_ids=get_exam_assigned_user_ids(exam),
                task_kind="exam",
            )
    return redirect("exams:teacher_exam_detail", slug=exam.slug)


@login_required
def delete_exam(request, slug):
    """
    İmtahanı silmək – amma əvvəlcə təsdiq istəyəciyik.
    Əgər imtahan üzrə cəhd (attempt) varsa, silməyə icazə vermirik.
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    _ensure_exam_permission(request, "exam.delete")
    exam = _get_editable_exam_or_404(request, slug)

    if exam.attempts.exists():
        # sadə variant: hazırda cəhd varsa silməyə icazə vermirik
        # istəsən bunu sonradan dəyişərik
        raise PermissionDenied(pgettext("exams.view.exams.permission", "delete_blocked_due_to_attempts"))

    if request.method == "POST":
        from apps.audit.utils import log_action
        from core.constants import AuditAction

        log_action(
            action=AuditAction.DELETE,
            user=request.user,
            organization=exam.organization,
            obj=exam,
            old_values={"title": exam.title, "slug": exam.slug},
            reason="exam_deleted",
            request=request,
        )
        _exam_pk = exam.pk
        exam.delete()
        try:
            from core.cache import invalidate_exam_metadata_cache, invalidate_exam_question_ids_cache

            invalidate_exam_metadata_cache(_exam_pk)
            invalidate_exam_question_ids_cache(_exam_pk)
        except Exception:
            pass
        return redirect(_teacher_profile_my_exams_url())

    return render(request, "exams/teacher/confirm_delete_exam.html", {"exam": exam})
