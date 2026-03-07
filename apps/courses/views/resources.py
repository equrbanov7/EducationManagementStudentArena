"""
courses/views/resources.py
───────────────────────────
Resource management views for courses.

Contains:
- AddResourceView
- DeleteResourceView
"""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import pgettext
from django.views.generic import CreateView, View

from apps.courses.forms import CourseResourceForm
from apps.courses.models import CourseResource

from ._helpers import IsCourseOwnerMixin, _get_owner_course_or_404


# ════════════════════════════════════════════════════════════════════════════
# Add Resource
# ════════════════════════════════════════════════════════════════════════════


class AddResourceView(IsCourseOwnerMixin, CreateView):
    """Resurs əlavə etmə (AJAX/Modal)."""

    model = CourseResource
    form_class = CourseResourceForm

    def dispatch(self, request, *args, **kwargs):
        self.course = _get_owner_course_or_404(request, kwargs["course_id"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.course = self.course
        response = super().form_valid(form)
        success_message = pgettext("courses.view.message", "resource_added").format(title=form.instance.title)

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": success_message,
                    "resource": {
                        "id": form.instance.id,
                        "title": form.instance.title,
                        "type": form.instance.get_resource_type_display(),
                    },
                }
            )

        messages.success(self.request, success_message)
        return response

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.course.id])


# ════════════════════════════════════════════════════════════════════════════
# Delete Resource
# ════════════════════════════════════════════════════════════════════════════


class DeleteResourceView(IsCourseOwnerMixin, View):
    """Resurs silmə."""

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        resource_id = kwargs.get("resource_id")

        course = _get_owner_course_or_404(request, course_id)
        resource = get_object_or_404(CourseResource, id=resource_id, course=course)

        resource_title = resource.title
        resource.delete()

        messages.success(
            request,
            pgettext("courses.view.message", "resource_deleted").format(title=resource_title),
        )

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})

        return redirect("courses:course_dashboard", course_id=course_id)
