"""«Tələbə idxalı» bölməsinin JSON/fayl endpoint-ləri (`user.import`).

Üç marşrut:

* ``student_intake_template`` — boş şablon faylı (GET, .xlsx / CSV);
* ``student_intake_preview``  — QURU İCRA: fayl yüklənir, sətir-sətir yoxlanılır,
  HEÇ NƏ YAZILMIR (POST, multipart);
* ``student_intake_apply``    — tətbiq: sətir başına savepoint + audit
  (POST, multipart). Cavabda birdəfəlik parollar qayıdır — operator onları
  CSV kimi endirir; parol nə DB-də, nə də audit jurnalında saxlanılmır.

Hər üçü FAIL-CLOSED: aktiv təşkilat konteksti + `user.import` açarı olmayan
aktor 403 alır. Ön baxış və tətbiq EYNİ plan qurucusundan keçir, ona görə
«gördüyün nəticə = alacağın nəticə».

Qəsdən STATE SAXLANILMIR: «Tətbiq et» eyni faylı yenidən göndərir. Serverdə
yüklənmiş fayl və ya parsed sətirlər sessiyada/kəşdə qalmır (PII + parol riski).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.services import intake

_CTX = "student_intake"


def _organization(request):
    from apps.accounts.views._helpers.tenant import _get_active_organization

    return _get_active_organization(request)


def _denied():
    return JsonResponse(
        {
            "ok": False,
            "error": "permission_denied",
            "message": pgettext(_CTX, "Tələbə idxalı üçün icazəniz yoxdur."),
        },
        status=403,
    )


def _gate(request):
    """``(organization, error_response)`` — fail-closed icazə qapısı."""

    organization = _organization(request)
    if organization is None or not intake.can_import(request.user, organization):
        return None, _denied()
    return organization, None


def _plans_from_request(request, organization):
    """``(plans, error_response)`` — faylı oxuyub planları qurur."""

    try:
        rows = intake.read_rows(request.FILES.get("file"))
    except intake.IntakeFileError as exc:
        return None, JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=400)
    return intake.build_plans(organization, rows), None


@never_cache
@login_required
@require_GET
def student_intake_template(request):
    """Boş şablon faylı — sütun başlıqları + izah sətri."""

    _organization_or_none, denied = _gate(request)
    if denied is not None:
        return denied
    payload, content_type, filename = intake.build_template()
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
@login_required
@require_POST
def student_intake_preview(request):
    """Quru icra — nə yaranacaq, nə ötürüləcək, harada xəta var."""

    organization, denied = _gate(request)
    if denied is not None:
        return denied
    plans, error = _plans_from_request(request, organization)
    if error is not None:
        return error
    return JsonResponse(
        {
            "ok": True,
            "summary": intake.summarize(plans),
            "rows": [plan.as_dict() for plan in plans],
        }
    )


@never_cache
@login_required
@require_POST
def student_intake_apply(request):
    """Tətbiq — sətir başına savepoint; bir pis sətir faylı dayandırmır."""

    organization, denied = _gate(request)
    if denied is not None:
        return denied
    plans, error = _plans_from_request(request, organization)
    if error is not None:
        return error
    try:
        result = intake.apply_plans(
            organization=organization,
            plans=plans,
            actor=request.user,
            request=request,
        )
    except intake.IntakeApplyError as exc:
        return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=409)
    result["ok"] = True
    return JsonResponse(result)


__all__ = ["student_intake_apply", "student_intake_preview", "student_intake_template"]
