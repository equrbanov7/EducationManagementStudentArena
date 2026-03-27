"""
courses/views/crud.py
─────────────────────
CRUD operations for courses.

Contains:
- CreateCourseView
- EditCourseView
- DeleteCourseView
- MyCoursesListView
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.courses.forms import CourseForm
from apps.courses.models import Course
from apps.organizations.models import Organization
from core.helpers import _safe_same_origin_redirect_path
from core.permissions import is_superadmin_user
from core.tenancy import get_request_organization, restore_request_organization_from_profile

from ._helpers import IsCourseOwnerMixin, _get_owner_course_or_404, _owner_courses_queryset, _require_org_permission

# ════════════════════════════════════════════════════════════════════════════
# Create Course
# ════════════════════════════════════════════════════════════════════════════


class CreateCourseView(LoginRequiredMixin, CreateView):
    """Kurs yaratma view-u.

    Authorization: user must be logged in and have the ``course.create``
    RBAC permission in the active organisation (checked in ``dispatch``).
    """

    model = Course
    form_class = CourseForm
    template_name = "courses/create_course.html"
    modal_form_template_name = "courses/partials/_create_course_modal_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        restore_request_organization_from_profile(request)
        if not self._can_superadmin_select_organization(request):
            _require_org_permission(request, "course.create")
        return super().dispatch(request, *args, **kwargs)

    def _is_modal_request(self):
        return self.request.GET.get("modal") == "1"

    def _can_superadmin_select_organization(self, request=None):
        current_request = request or self.request
        return (
            is_superadmin_user(getattr(current_request, "user", None))
            and get_request_organization(current_request) is None
        )

    def _organization_selection_queryset(self):
        return Organization.objects.filter(is_active=True, status="active").order_by("name")

    def _bind_selected_organization(self, organization):
        self.request.organization = organization
        self.request.org_memberships = []
        self.request.org_permissions = list(getattr(self.request, "org_permissions", []) or [])
        if hasattr(self.request, "session"):
            self.request.session["active_organization"] = organization.slug
        if hasattr(self.request.user, "set_active_organization_context"):
            self.request.user.set_active_organization_context(
                organization,
                memberships=self.request.org_memberships,
                permissions=self.request.org_permissions,
            )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self._can_superadmin_select_organization():
            kwargs["allow_organization_selection"] = True
            kwargs["organization_queryset"] = self._organization_selection_queryset()
        return kwargs

    def get(self, request, *args, **kwargs):
        if self._is_modal_request():
            self.object = None
            form = self.get_form()
            return render(
                request,
                self.modal_form_template_name,
                {
                    "form": form,
                },
            )
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        organization = get_request_organization(self.request)
        if organization is None and self._can_superadmin_select_organization():
            organization = form.cleaned_data.get("organization")
            if organization is not None:
                self._bind_selected_organization(organization)
        if organization is None:
            raise PermissionDenied(pgettext("courses.view.permission", "active_organization_required"))
        form.instance.owner = self.request.user
        form.instance.status = "draft"
        form.instance.organization = organization
        super().form_valid(form)
        messages.success(
            self.request,
            pgettext("courses.view.message", "course_created_successfully").format(title=form.instance.title),
        )
        if self._is_modal_request():
            return JsonResponse(
                {
                    "success": True,
                    "course_id": self.object.id,
                    "dashboard_url": str(self.get_success_url()),
                }
            )
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        if self._is_modal_request():
            html = render_to_string(
                self.modal_form_template_name,
                {
                    "form": form,
                },
                request=self.request,
            )
            return JsonResponse({"success": False, "html": html}, status=400)
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.object.id])


# ════════════════════════════════════════════════════════════════════════════
# Edit Course
# ════════════════════════════════════════════════════════════════════════════


class EditCourseView(IsCourseOwnerMixin, UpdateView):
    """Kurs məlumatını redaktə etmə."""

    model = Course
    form_class = CourseForm
    template_name = "courses/edit_course.html"
    context_object_name = "course"
    pk_url_kwarg = "course_id"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        _require_org_permission(request, "course.edit")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(
            self.request,
            pgettext("courses.view.message", "course_updated").format(title=form.instance.title),
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.object.id])


# ════════════════════════════════════════════════════════════════════════════
# Delete Course
# ════════════════════════════════════════════════════════════════════════════


class DeleteCourseView(IsCourseOwnerMixin, View):
    """Kursun tam silinməsi."""

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        course = _get_owner_course_or_404(request, course_id)

        course_title = course.title
        course.delete()

        messages.success(
            request,
            pgettext("courses.view.message", "course_deleted").format(title=course_title),
        )
        return_to = _safe_same_origin_redirect_path(
            request,
            request.POST.get("return_to") or request.GET.get("return_to"),
        )
        if return_to:
            return redirect(return_to)

        return redirect(f"{reverse('accounts:profile')}?section=my-courses")


# ════════════════════════════════════════════════════════════════════════════
# Update Course Status
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_POST
def update_course_status(request, course_id):
    """Update the course visibility status from the dashboard panel."""

    _require_org_permission(request, "course.edit")
    course = _get_owner_course_or_404(request, course_id)

    requested_status = (request.POST.get("status") or "").strip().lower()
    normalized_status = {"active": "published", "published": "published", "draft": "draft"}.get(requested_status)

    if normalized_status is None:
        messages.error(request, pgettext("courses.view.message", "invalid_course_status"))
    else:
        course.status = normalized_status
        course.save(update_fields=["status", "updated_at"])
        messages.success(
            request,
            pgettext("courses.view.message", "course_status_updated").format(status=course.get_status_display()),
        )

    redirect_target = _safe_same_origin_redirect_path(
        request,
        request.POST.get("next") or request.GET.get("next"),
    )
    if redirect_target:
        return redirect(redirect_target)
    return redirect("courses:course_dashboard", course_id=course.id)


# ════════════════════════════════════════════════════════════════════════════
# My Courses List
# ════════════════════════════════════════════════════════════════════════════


class MyCoursesListView(LoginRequiredMixin, ListView):
    """Mənim kurslarım (owner)."""

    template_name = "courses/my_courses.html"
    context_object_name = "courses"
    paginate_by = 12

    def get_queryset(self):
        return _owner_courses_queryset(self.request).order_by("-created_at")
