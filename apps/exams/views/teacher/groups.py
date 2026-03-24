from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_POST

from apps.accounts.models import ProfileRole
from apps.exams.forms import StudentGroupForm
from apps.exams.models import StudentGroup
from apps.exams.views.shared.tenant import get_active_organization
from core.tenancy import request_has_active_organization_context


def _is_superadmin(user):
    return user.is_superuser or getattr(user, "is_superadmin", False)


def _ensure_group_manager(user):
    if _is_superadmin(user):
        return
    has_student_role = hasattr(user, "has_role") and (
        user.has_role(ProfileRole.STUDENT) or user.has_role(ProfileRole.LEAD_STUDENT)
    )
    has_teacher_like_role = hasattr(user, "has_role") and (
        user.has_role(ProfileRole.TEACHER)
        or user.has_role(ProfileRole.ASSISTANT_TEACHER)
        or user.has_role(ProfileRole.ORG_ADMIN)
        or user.has_role(ProfileRole.ORG_OWNER)
        or user.has_role(ProfileRole.HR)
    )

    if has_student_role and not has_teacher_like_role:
        raise PermissionDenied(pgettext("exams.view.groups.message", "no_page_permission"))


def _can_multi_assign_teachers(user):
    if _is_superadmin(user):
        return True

    role_level = user._highest_role_level() if hasattr(user, "_highest_role_level") else 0
    return role_level >= ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60)


def _resolve_next_url(request):
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if not next_url:
        return ""
    if url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ""


def _get_required_organization(request):
    organization = get_active_organization(request)
    if organization is None:
        messages.error(request, pgettext_lazy("exams.view.groups.message", "active_org_not_found"))
        return None

    if not _is_superadmin(request.user) and not request_has_active_organization_context(request):
        raise PermissionDenied(pgettext("exams.view.groups.message", "active_tenant_mismatch"))

    return organization


def _group_queryset_for_actor(request, organization):
    queryset = (
        StudentGroup.objects.filter(organization=organization)
        .select_related("teacher", "organization")
        .prefetch_related("students", "teachers")
        .order_by("name")
    )
    if _is_superadmin(request.user) or _can_multi_assign_teachers(request.user):
        return queryset
    return queryset.filter(Q(teacher=request.user) | Q(teachers=request.user)).distinct()


def _group_form_for_request(request, organization, data=None, instance=None):
    return StudentGroupForm(
        data,
        instance=instance,
        actor=request.user,
        organization=organization,
        can_multi_assign_teachers=_can_multi_assign_teachers(request.user),
        is_superadmin=_is_superadmin(request.user),
    )


def _create_group_template_context(request, organization, form):
    return {
        "form": form,
        "organization": organization,
        "can_multi_assign_teachers": _can_multi_assign_teachers(request.user),
        "max_multi_teachers": getattr(form, "MAX_MULTI_TEACHERS", 3),
        "student_count": form.fields["students"].queryset.count(),
        "teacher_count": form.fields["primary_teacher"].queryset.count(),
        "is_editing": False,
    }


@login_required
def teacher_group_list(request):
    _ensure_group_manager(request.user)
    organization = _get_required_organization(request)
    if organization is None:
        return redirect("accounts:profile")

    groups = _group_queryset_for_actor(request, organization)
    form = _group_form_for_request(request, organization)

    context = {
        "groups": groups,
        "form": form,
        "organization": organization,
        "can_multi_assign_teachers": _can_multi_assign_teachers(request.user),
    }
    return render(request, "exams/teacher/teacher_group_list.html", context)


@login_required
@require_POST
def teacher_create_group(request):
    _ensure_group_manager(request.user)
    organization = _get_required_organization(request)
    if organization is None:
        return redirect("accounts:profile")

    form = _group_form_for_request(request, organization, data=request.POST)
    if form.is_valid():
        group = form.save()
        from apps.audit.utils import log_action
        from core.constants import AuditAction

        log_action(
            action=AuditAction.CREATE,
            user=request.user,
            organization=organization,
            obj=group,
            new_values={"name": group.name},
            reason="group_created",
            request=request,
        )
        messages.success(request, pgettext_lazy("exams.view.groups.message", "group_created"))
        next_url = _resolve_next_url(request)
        if next_url:
            return redirect(next_url)
        return redirect("exams:teacher_group_list")

    next_url = _resolve_next_url(request)
    if next_url:
        messages.error(request, pgettext_lazy("exams.view.groups.message", "group_create_failed"))
        return redirect(next_url)

    return render(
        request,
        "exams/teacher/create_student_group.html",
        _create_group_template_context(request, organization, form),
        status=400,
    )


@login_required
@require_POST
def teacher_update_group(request, group_id):
    _ensure_group_manager(request.user)
    organization = _get_required_organization(request)
    if organization is None:
        return redirect("accounts:profile")

    group = get_object_or_404(_group_queryset_for_actor(request, organization), id=group_id)
    form = _group_form_for_request(request, organization, data=request.POST, instance=group)

    if form.is_valid():
        group = form.save()
        from apps.audit.utils import log_action
        from core.constants import AuditAction

        log_action(
            action=AuditAction.UPDATE,
            user=request.user,
            organization=organization,
            obj=group,
            new_values={"name": group.name},
            reason="group_updated",
            request=request,
        )
        messages.success(request, pgettext_lazy("exams.view.groups.message", "group_updated"))
        next_url = _resolve_next_url(request)
        if next_url:
            return redirect(next_url)
        return redirect("exams:teacher_group_list")

    next_url = _resolve_next_url(request)
    if next_url:
        messages.error(request, pgettext_lazy("exams.view.groups.message", "group_update_failed"))
        return redirect(next_url)

    groups = _group_queryset_for_actor(request, organization)
    return render(
        request,
        "exams/teacher/teacher_group_list.html",
        {
            "groups": groups,
            "form": form,
            "organization": organization,
            "can_multi_assign_teachers": _can_multi_assign_teachers(request.user),
            "edit_group_id": group.id,
        },
        status=400,
    )


@login_required
@require_POST
def teacher_delete_group(request, group_id):
    _ensure_group_manager(request.user)
    organization = _get_required_organization(request)
    if organization is None:
        return redirect("accounts:profile")

    group = get_object_or_404(_group_queryset_for_actor(request, organization), id=group_id)
    from apps.audit.utils import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.DELETE,
        user=request.user,
        organization=organization,
        obj=group,
        old_values={"name": group.name},
        reason="group_deleted",
        request=request,
    )
    group.delete()
    messages.success(request, pgettext_lazy("exams.view.groups.message", "group_deleted"))
    next_url = _resolve_next_url(request)
    if next_url:
        return redirect(next_url)
    return redirect("exams:teacher_group_list")


@login_required
def create_student_group(request):
    _ensure_group_manager(request.user)
    organization = _get_required_organization(request)
    if organization is None:
        return redirect("accounts:profile")

    form = _group_form_for_request(request, organization)
    return render(
        request,
        "exams/teacher/create_student_group.html",
        _create_group_template_context(request, organization, form),
    )
