"""
courses/views/topics.py
───────────────────────
Topic management views for courses.

Contains:
- AddTopicView
- EditTopicView
- DeleteTopicView
"""

from django.contrib import messages
from django.db.models import Max
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import pgettext, pgettext_lazy
from django.views.generic import CreateView, UpdateView, View

from apps.courses.forms import CourseTopicForm
from apps.courses.models import CourseTopic

from ..shared._helpers import IsCourseOwnerMixin, _get_owner_course_or_404, _owner_courses_queryset

# ════════════════════════════════════════════════════════════════════════════
# Add Topic
# ════════════════════════════════════════════════════════════════════════════


class AddTopicView(IsCourseOwnerMixin, CreateView):
    """Mövzu əlavə etmə (AJAX POST)."""

    model = CourseTopic
    form_class = CourseTopicForm

    def dispatch(self, request, *args, **kwargs):
        self.course = _get_owner_course_or_404(request, kwargs["course_id"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.course = self.course
        max_order = CourseTopic.objects.filter(course=self.course).aggregate(Max("order"))["order__max"] or 0
        form.instance.order = max_order + 1

        response = super().form_valid(form)
        success_message = pgettext("courses.view.message", "topic_added").format(title=form.instance.title)

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": success_message,
                    "topic": {
                        "id": form.instance.id,
                        "title": form.instance.title,
                        "order": form.instance.order,
                    },
                }
            )

        messages.success(self.request, success_message)
        return response

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "errors": form.errors}, status=400)
        messages.error(self.request, pgettext_lazy("courses.view.message", "topic_add_failed"))
        return redirect("courses:course_dashboard", course_id=self.course.id)

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.course.id])


# ════════════════════════════════════════════════════════════════════════════
# Edit Topic
# ════════════════════════════════════════════════════════════════════════════


class EditTopicView(IsCourseOwnerMixin, UpdateView):
    """Mövzu redaktə etmə (AJAX POST)."""

    model = CourseTopic
    form_class = CourseTopicForm
    pk_url_kwarg = "topic_id"

    def test_func(self):
        topic = self.get_object()
        return _owner_courses_queryset(self.request).filter(id=topic.course_id).exists()

    def dispatch(self, request, *args, **kwargs):
        self.topic = self.get_object()
        self.course = self.topic.course
        if not _owner_courses_queryset(request).filter(id=self.course.id).exists():
            return HttpResponseForbidden(pgettext("courses.view.message", "no_permission_edit_course"))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        success_message = pgettext("courses.view.message", "topic_updated").format(title=form.instance.title)

        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": success_message,
                    "topic": {
                        "id": form.instance.id,
                        "title": form.instance.title,
                        "description": form.instance.description,
                        "order": form.instance.order,
                    },
                }
            )

        messages.success(self.request, success_message)
        return response

    def form_invalid(self, form):
        if self.request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "errors": form.errors}, status=400)

        messages.error(self.request, pgettext_lazy("courses.view.message", "topic_update_failed"))
        return redirect("courses:course_dashboard", course_id=self.course.id)

    def get_success_url(self):
        return reverse_lazy("courses:course_dashboard", args=[self.course.id])


# ════════════════════════════════════════════════════════════════════════════
# Delete Topic
# ════════════════════════════════════════════════════════════════════════════


class DeleteTopicView(IsCourseOwnerMixin, View):
    """Mövzu silmə (POST)."""

    def post(self, request, *args, **kwargs):
        course_id = kwargs.get("course_id")
        topic_id = kwargs.get("topic_id")

        course = _get_owner_course_or_404(request, course_id)
        topic = get_object_or_404(CourseTopic, id=topic_id, course=course)

        topic_title = topic.title
        topic.delete()

        messages.success(
            request,
            pgettext("courses.view.message", "topic_deleted").format(title=topic_title),
        )

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})

        return redirect("courses:course_dashboard", course_id=course_id)
