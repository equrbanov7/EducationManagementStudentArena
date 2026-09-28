"""
courses/views/teacher/ai.py — «AI ilə kurs qur» çekməcəsinin endpoint-ləri (2026-09-28).

- CourseAIPlanView   POST {"prompt"}          → plan (heç nə yazılmır)
- CourseAIApplyView  POST {"plan": {"topics"}} → təsdiqlənmiş mövzu/resursları yaradır
"""

import json
import logging

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.translation import get_language, pgettext
from django.views.generic import View

from apps.courses import ai_planner
from core.permissions import request_has_permission

from ..shared._helpers import _get_owner_course_or_404, _owner_courses_queryset

logger = logging.getLogger(__name__)
_CTX = "courses.ai"
PLAN_LOCK_SECONDS = 120


def _body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class _AIBase(LoginRequiredMixin, UserPassesTestMixin, View):
    http_method_names = ["post"]

    def test_func(self):
        return _owner_courses_queryset(self.request).filter(id=self.kwargs.get("course_id")).exists()

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        return JsonResponse({"ok": False, "error": pgettext(_CTX, "no_permission")}, status=403)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request_has_permission(request, "course.edit"):
            return JsonResponse({"ok": False, "error": pgettext(_CTX, "no_permission")}, status=403)
        return super().dispatch(request, *args, **kwargs)


class CourseAIPlanView(_AIBase):
    def post(self, request, *args, **kwargs):
        course = _get_owner_course_or_404(request, kwargs.get("course_id"))
        prompt = str(_body(request).get("prompt") or "").strip()
        if not prompt:
            return JsonResponse({"ok": False, "error": pgettext(_CTX, "prompt_required")}, status=400)
        # Audit 2026-09-28 DB-05: istifadəçi başına EYNİ ANDA bir plan sorğusu — paralel
        # sorğularla kvota yoxlamasını (check → call → record) keçmək olmasın.
        lock_key = f"courses:ai-plan:inflight:{request.user.id}"
        if not cache.add(lock_key, 1, timeout=PLAN_LOCK_SECONDS):
            return JsonResponse({"ok": False, "code": "busy", "error": pgettext(_CTX, "busy")}, status=429)
        try:
            result = ai_planner.generate_course_plan(
                course=course, request_text=prompt, user_id=request.user.id, language_code=get_language()
            )
        finally:
            cache.delete(lock_key)
        if not result.get("ok"):
            code = result.get("code") or ""
            error = result.get("error") or ""
            if error == "empty_plan" or not error:
                error = pgettext(_CTX, "plan_empty")
            elif code == "generation_failed":
                # exams-in ümumi mətni «AI xülasəsi…» deyir — kurs planı üçün öz mesajımız
                error = pgettext(_CTX, "error_generic")
            status = 429 if code in {"rate_limited", "quota"} else 502
            return JsonResponse({"ok": False, "code": code, "error": error}, status=status)
        return JsonResponse(result)


class CourseAIApplyView(_AIBase):
    def post(self, request, *args, **kwargs):
        course = _get_owner_course_or_404(request, kwargs.get("course_id"))
        plan = _body(request).get("plan")
        if not ai_planner.normalise_plan(plan or {})["topics"]:
            return JsonResponse({"ok": False, "error": pgettext(_CTX, "nothing_selected")}, status=400)
        try:
            created = ai_planner.apply_course_plan(course=course, plan=plan)
        except Exception:
            logger.exception("Course AI plan apply failed")
            return JsonResponse({"ok": False, "error": pgettext(_CTX, "apply_failed")}, status=500)
        message = pgettext(_CTX, "applied_summary").format(topics=created["topics"], resources=created["resources"])
        return JsonResponse({"ok": True, "created": created, "message": message})
