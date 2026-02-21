from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import ProfileRole
from apps.exams.forms import StudentGroupForm
from apps.exams.models import StudentGroup
from apps.exams.views.shared.tenant import get_active_organization


def _user_role(user):
    profile = getattr(user, "profile", None)
    return getattr(profile, "role", None)


def _is_superadmin(user):
    return user.is_superuser or getattr(user, "is_superadmin", False)


def _ensure_group_manager(user):
    if _is_superadmin(user):
        return
    if _user_role(user) == ProfileRole.STUDENT:
        raise PermissionDenied("Bu səhifəyə giriş icazəniz yoxdur.")


def _can_multi_assign_teachers(user):
    if _is_superadmin(user):
        return True

    role = _user_role(user)
    role_level = ProfileRole.LEVELS.get(role, 0)
    return role_level > ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60)


def _get_required_organization(request):
    organization = get_active_organization(request)
    if organization is None:
        messages.error(request, "Aktiv təşkilat tapılmadı.")
        return None

    if not _is_superadmin(request.user):
        user_org = getattr(getattr(request.user, "profile", None), "organization", None)
        if user_org != organization:
            raise PermissionDenied("Aktiv tenant sizin təşkilatınızla uyğun deyil.")

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
        form.save()
        messages.success(request, "Qrup uğurla yaradıldı.")
        return redirect("exams:teacher_group_list")

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
        form.save()
        messages.success(request, "Qrup yeniləndi.")
        return redirect("exams:teacher_group_list")

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
    group.delete()
    messages.success(request, "Qrup silindi.")
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
