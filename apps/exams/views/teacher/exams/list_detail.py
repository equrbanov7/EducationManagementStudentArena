"""teacher exams paketi — list_detail."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_GET

from apps.exams.constants import get_live_active_states, get_live_session_model
from apps.exams.forms import ExamForm
from apps.exams.services.access_policy import _ensure_teacher, can_manage_exam_questions
from apps.exams.views.shared.tenant import get_active_organization, get_teacher_exam_or_404
from core.permissions import is_superadmin_user
from core.tenancy import get_request_organization, request_has_active_organization_context

from ._shared import (
    _bind_selected_organization,
    _ensure_exam_permission,
    _get_editable_exam_or_404,
    _get_exam_detail_question_page,
    _get_requested_course_for_exam,
    _organization_selection_queryset,
    _organization_selection_redirect,
    _resolve_profile_navigation,
    _resolve_required_organization,
    _resolve_selected_superadmin_organization,
    _restore_superadmin_profile_organization,
    _selected_access_entities,
    _teacher_profile_my_exams_url,
)

logger = logging.getLogger(__name__)


@login_required
def teacher_exam_list(request):
    """
    Legacy /exams/ entry point.
    Teacher exam list now lives inside the profile "my-exams" section.
    """
    return redirect(_teacher_profile_my_exams_url())


@login_required
def createAndEditExamView(request, slug=None):
    """
    Birləşdirilmiş view: Create və Edit
    slug=None -> Yeni imtahan
    slug=<value> -> Mövcud imtahanı redaktə
    """
    is_editing = slug is not None
    is_modal_request = request.GET.get("modal") == "1" or request.POST.get("modal") == "1"
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

    if not is_modal_request:
        return redirect(_teacher_profile_my_exams_url())

    linked_course = None if is_editing else _get_requested_course_for_exam(request)

    # Load existing supervision config for edit mode
    supervision_config = None
    if is_editing and exam:
        try:
            supervision_config = exam.supervision_config
        except ObjectDoesNotExist:
            # No supervision config row exists yet for this exam — keep the
            # None default. Narrowed from a bare ``except Exception`` so real
            # errors (e.g. DB failures) are no longer silently swallowed.
            supervision_config = None

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
            from apps.notifications.public import get_exam_assigned_user_ids

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

            # Final/midterm imtahanlarında hər tələbəyə fərdi PIN təmin et
            # (kabinetdə dərhal görünür, imtahan kodunu əvəz edir).
            from apps.exams.services.student_pins import provision_exam_student_pins

            provision_exam_student_pins(exam_instance)

            from apps.notifications.public import get_exam_assigned_user_ids, notify_task_assignment

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

            from apps.audit.public import log_action
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
                # Best-effort: a stale metadata entry self-heals on its next
                # TTL, so a cache failure must not break the save flow — but it
                # must be visible for diagnostics instead of being swallowed.
                logger.warning(
                    "Exam metadata cache invalidation failed for exam %s",
                    getattr(exam_instance, "pk", None),
                    exc_info=True,
                )

            from apps.exams.services.difficulty import schedule_ai_question_difficulty_warmup

            schedule_ai_question_difficulty_warmup(exam_instance)

            messages.success(
                request,
                (
                    pgettext_lazy("exams.view.exams.message", "exam_updated")
                    if is_editing
                    else pgettext_lazy("exams.view.exams.message", "exam_created")
                ),
            )
            return JsonResponse({"success": True, "slug": exam_instance.slug})
        selected_groups, selected_users, selected_excluded_users = _selected_access_entities(form)
        html = render_to_string(
            "exams/teacher/partials/_create_exam_modal_form.html",
            {
                "form": form,
                "is_editing": is_editing,
                "exam": exam,
                "linked_course": linked_course,
                "selected_allowed_groups": selected_groups,
                "selected_allowed_users": selected_users,
                "selected_excluded_users": selected_excluded_users,
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
    selected_groups, selected_users, selected_excluded_users = _selected_access_entities(form)

    return render(
        request,
        "exams/teacher/partials/_create_exam_modal_form.html",
        {
            "form": form,
            "exam": exam,
            "is_editing": is_editing,
            "linked_course": linked_course,
            "selected_allowed_groups": selected_groups,
            "selected_allowed_users": selected_users,
            "selected_excluded_users": selected_excluded_users,
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
    question_page = _get_exam_detail_question_page(exam)
    profile_return_url, _, nav_query = _resolve_profile_navigation(request, default_section="my-exams")
    exam_back_label = pgettext("exams.template.teacher_exam_detail", "action_back")
    active_live_session = (
        get_live_session_model()
        .objects.filter(exam=exam, host_user=request.user, state__in=get_live_active_states())
        .order_by("-created_at", "-id")
        .first()
    )
    active_live_continue_url = ""
    active_live_new_url = ""
    if active_live_session:
        active_live_continue_url = (
            f"{reverse('liveExam:host_presentation', kwargs={'pin': active_live_session.pin})}?controls=1"
        )
        active_live_new_url = f"{reverse('liveExam:create_session_slug', kwargs={'slug': exam.slug})}?force_new=1"

    return render(
        request,
        "exams/teacher/teacher_exam_detail.html",
        {
            "exam": exam,
            "questions": question_page["questions"],
            "questions_has_more": question_page["has_more"],
            "questions_next_offset": question_page["next_offset"],
            "questions_page_size": question_page["page_size"],
            "questions_total_count": exam.questions.count(),
            "profile_return_url": profile_return_url,
            "exam_navigation_query": nav_query,
            "exam_back_label": exam_back_label,
            "active_live_session": active_live_session,
            "active_live_continue_url": active_live_continue_url,
            "active_live_new_url": active_live_new_url,
            "can_manage_exam_questions": can_manage_exam_questions(request.user, exam),
        },
    )


@login_required
@require_GET
def teacher_exam_detail_questions_page(request, slug):
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    question_page = _get_exam_detail_question_page(
        exam,
        offset=request.GET.get("offset"),
        limit=request.GET.get("limit"),
    )
    _, _, nav_query = _resolve_profile_navigation(request, default_section="my-exams")
    html = render_to_string(
        "exams/teacher/partials/_exam_detail_question_items.html",
        {
            "exam": exam,
            "questions": question_page["questions"],
            "exam_navigation_query": nav_query,
            "can_manage_exam_questions": can_manage_exam_questions(request.user, exam),
        },
        request=request,
    )
    return JsonResponse(
        {
            "html": html,
            "has_more": question_page["has_more"],
            "next_offset": question_page["next_offset"],
        }
    )
