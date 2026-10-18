"""
courses/views/teacher/syllabus.py — «Sillabusdan mövzuları götür» endpoint-ləri (2026-10-18).

- CourseSyllabusOptionsView  GET  ?q=                    → oxuna bilən sillabuslar (JSON)
- CourseSyllabusPreviewView  GET  ?syllabus=<uuid>       → yaradılacaq / artıq olan həftələr (heç nə yazılmır)
- CourseSyllabusImportView   POST {"syllabus", "link"}   → yeni həftələri mövzu kimi yaradır (bir tranzaksiya)

İcazə (hamısında, YAZIDAN ƏVVƏL): kurs aktiv təşkilatda deyilsə 404; kursun sahibi deyilsə və ya
``course.edit`` yoxdursa 403; sillabus aktorun oxu əhatəsində deyilsə 404. Qaydalar və idempotentlik
``apps.courses.syllabus_import``-dadır.
"""

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext
from django.views.generic import View

from apps.courses import syllabus_import
from core.helpers import _tenant_scoped_courses
from core.permissions import request_has_permission

_CTX = "courses.syllabus_import"


def _deny():
    return JsonResponse({"ok": False, "error": pgettext(_CTX, "Bu kursda mövzu idxalına icazəniz yoxdur.")}, status=403)


def _not_found():
    return JsonResponse(
        {"ok": False, "error": pgettext(_CTX, "Sillabus tapılmadı və ya ona baxmaq icazəniz yoxdur.")}, status=404
    )


class _SyllabusBase(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        try:
            self.course = get_object_or_404(_tenant_scoped_courses(request), pk=kwargs.get("course_id"))
        except Http404:
            return JsonResponse({"ok": False, "error": pgettext(_CTX, "Kurs tapılmadı.")}, status=404)
        if self.course.owner_id != request.user.pk or not request_has_permission(request, "course.edit"):
            return _deny()
        self.actor = syllabus_import.actor_for(request, self.course)
        return super().dispatch(request, *args, **kwargs)

    def _syllabus(self, syllabus_id):
        return syllabus_import.get_readable_syllabus(self.actor, self.course.organization, syllabus_id)


class CourseSyllabusOptionsView(_SyllabusBase):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        items = syllabus_import.syllabus_options(
            self.actor, self.course.organization, search=request.GET.get("q", ""), linked_id=self.course.syllabus_id
        )
        return JsonResponse({"ok": True, "items": items, "linked_id": str(self.course.syllabus_id or "")})


class CourseSyllabusPreviewView(_SyllabusBase):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        syllabus = self._syllabus(request.GET.get("syllabus"))
        if syllabus is None:
            return _not_found()
        preview = syllabus_import.build_preview(self.course, syllabus, user_id=request.user.pk)
        return JsonResponse({"ok": True, **preview})


class CourseSyllabusImportView(_SyllabusBase):
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        syllabus = self._syllabus(body.get("syllabus") or request.POST.get("syllabus"))
        if syllabus is None:
            return _not_found()
        link = body.get("link", request.POST.get("link", "1")) in (True, 1, "1", "true", "on")
        result = syllabus_import.apply_import(self.course, syllabus, link=link)
        message = pgettext(_CTX, "%(created)s mövzu əlavə olundu, %(skipped)s artıq var idi.") % result
        return JsonResponse({"ok": True, **result, "message": message})
