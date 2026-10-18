"""
courses/views/resources.py
───────────────────────────
Resource management views for courses.

Contains:
- AddResourceView
- DeleteResourceView
"""

from django.contrib import messages
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import pgettext
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.generic import CreateView, View

from apps.courses.forms import CourseResourceForm
from apps.courses.models import CourseResource
from apps.courses.resource_upload import POLICIES, UPLOAD_BODY_MAX_BYTES, format_mb

from ..shared._helpers import IsCourseOwnerMixin, _get_owner_course_or_404

# ════════════════════════════════════════════════════════════════════════════
# Add Resource
# ════════════════════════════════════════════════════════════════════════════


# CSRF `dispatch` içində `csrf_protect` ilə — upload handler POST oxunmamışdan ƏVVƏL qurulmalıdır.
@method_decorator(csrf_exempt, name="dispatch")
class AddResourceView(IsCourseOwnerMixin, CreateView):
    """Resurs əlavə etmə (AJAX/Modal) — URL ``/courses/resource-upload/<id>/``.

    2026-10-19: video ≤ 200 MB qəbul edir. nginx bu yol üçün ayrıca ``location`` (210m) verir;
    burada isə gövdə YALNIZ kurs sahibi üçün parse olunur:

    * view ``csrf_exempt``-dir, CSRF aşağıda ``csrf_protect`` ilə yoxlanır — beləliklə auth/sahiblik
      və ``CONTENT_LENGTH`` tavanı multipart parse-dan ƏVVƏL işləyir (anonim/kənar 200 MB gövdə
      diskə yazılmır, aydın JSON 401/404/413 alır);
    * yükləmə handler-i ``TemporaryFileUploadHandler`` — fayl yaddaşa yox, birbaşa diskə axır;
    * qlobal 5 MB ``DATA_UPLOAD_MAX_MEMORY_SIZE`` yalnız mətn sahələrinə aiddir, fayla yox.
    """

    model = CourseResource
    form_class = CourseResourceForm
    http_method_names = ["post"]  # yalnız modal POST-u; GET şablonu yoxdur (əvvəl 500 verirdi)

    def dispatch(self, request, *args, **kwargs):
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
        if not request.user.is_authenticated:
            if is_ajax:
                return _json_error(
                    pgettext("courses.resource_upload", "Sessiyanız bitib — səhifəni yeniləyib yenidən daxil olun."),
                    status=401,
                )
            return self.handle_no_permission()
        self.course = _get_owner_course_or_404(request, kwargs["course_id"])
        if request.method == "POST":
            too_large = _body_too_large(request)
            if too_large:
                return _json_error(too_large, status=413)
            _install_disk_upload_handler(request)
        return csrf_protect(super().dispatch)(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Təhlükəsizlik auditi 2026-10-05: mövzu YALNIZ bu kursun mövzularından —
        # default queryset bütün CourseTopic-lər idi (başqa kursa resurs yeridilməsi).
        form.fields["topic"].queryset = self.course.topics.all()
        return form

    def form_invalid(self, form):
        # Modal/AJAX endpoint-dir — ``courses/courseresource_form.html`` şablonu YOXDUR
        # (əvvəl hər yanlış forma TemplateDoesNotExist → 500 verirdi).
        return JsonResponse({"success": False, "errors": form.errors}, status=400)

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


def _json_error(message, *, status):
    return JsonResponse({"success": False, "errors": {"__all__": [str(message)]}}, status=status)


def _body_too_large(request):
    """``CONTENT_LENGTH`` ən böyük tip limitini (+ zərf) keçirsə — aydın xəta mətni, əks halda ``""``."""
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        length = 0
    if length <= UPLOAD_BODY_MAX_BYTES:
        return ""
    largest = max(policy.max_mb for policy in POLICIES.values())
    return pgettext("courses.resource_upload", "Fayl çox böyükdür: {size} MB (maks. {max_mb} MB)").format(
        size=format_mb(length), max_mb=largest
    )


def _install_disk_upload_handler(request):
    """Gövdə hələ oxunmayıbsa faylı birbaşa diskə yazan handler (``request.FILES`` oxunmamışdan ƏVVƏL)."""
    if hasattr(request, "_files"):  # məs. view-as middleware POST-u artıq oxuyub
        return
    request.upload_handlers = [TemporaryFileUploadHandler(request)]


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
