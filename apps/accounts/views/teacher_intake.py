"""«Müəllim idxalı» bölməsinin JSON/fayl endpoint-ləri (`user.import`, 2026-09-08).

Tələbə idxalı ilə EYNİ qapı və eyni «quru icra = tətbiq» müqaviləsi
(bax `views/student_intake.py`); fərq yalnız sütun müqaviləsi və planların
qurulmasıdır (`services/intake/teachers.py`). Serverdə state saxlanılmır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.services import intake
from apps.accounts.services.intake import teachers

_CTX = "teacher_intake"


def _organization(request):
    from apps.accounts.views._helpers.tenant import _get_active_organization

    return _get_active_organization(request)


def _gate(request):
    organization = _organization(request)
    if organization is None or not intake.can_import(request.user, organization):
        return None, JsonResponse(
            {
                "ok": False,
                "error": "permission_denied",
                "message": pgettext(_CTX, "Toplu müəllim əlavəsi üçün icazəniz yoxdur."),
            },
            status=403,
        )
    return organization, None


def _plans_from_request(request, organization):
    try:
        rows = teachers.read_rows(request.FILES.get("file"))
    except intake.IntakeFileError as exc:
        return None, JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=400)
    if len(rows) > intake.MAX_ROWS:
        return None, JsonResponse(
            {
                "ok": False,
                "error": "intake_too_many_rows",
                "message": pgettext(_CTX, "Bir faylda ən çox %d sətir ola bilər.") % intake.MAX_ROWS,
            },
            status=400,
        )
    return teachers.build_plans(organization, rows), None


@never_cache
@login_required
@require_GET
def teacher_intake_template(request):
    _org, denied = _gate(request)
    if denied is not None:
        return denied
    payload, content_type, filename = teachers.build_template()
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
@login_required
@require_POST
def teacher_intake_preview(request):
    organization, denied = _gate(request)
    if denied is not None:
        return denied
    plans, error = _plans_from_request(request, organization)
    if error is not None:
        return error
    return JsonResponse({"ok": True, "summary": teachers.summarize(plans), "rows": [plan.as_dict() for plan in plans]})


@never_cache
@login_required
@require_POST
def teacher_intake_apply(request):
    organization, denied = _gate(request)
    if denied is not None:
        return denied
    plans, error = _plans_from_request(request, organization)
    if error is not None:
        return error
    try:
        result = teachers.apply_plans(organization=organization, plans=plans, actor=request.user, request=request)
    except intake.IntakeApplyError as exc:
        return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=409)
    result["ok"] = True
    return JsonResponse(result)


__all__ = ["teacher_intake_apply", "teacher_intake_preview", "teacher_intake_template"]
