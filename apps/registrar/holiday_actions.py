"""«Akademik təqvim» → «Bayram və qeyri-iş günləri» ƏMƏLLƏRİ — tək JSON POST endpoint-i (2026-10-19).

Əməllər: ``save`` (əlavə et / redaktə et) · ``delete`` · ``seed_fixed`` (tədris ilinin SABİT tarixli rəsmi
bayramları; mövcud tarixlər atlanır). Hər əməl ``core.audit``-a yazılır (servis qatında).

QAPI: ``semester.open`` TƏŞKİLAT səviyyəsində (bax ``calendar_holidays.can_manage_holidays``): açar yoxdursa
və ya yalnız bölmə (UNIT) səviyyəsindədirsə — 403; başqa təşkilatın qeydi — 404. View-as rejimində yazı YOXDUR
(403, ``view_as_blocked``). Səlahiyyət HƏR yazıdan ƏVVƏL yoxlanılır (``ATOMIC_REQUESTS``).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from .calendar_holidays import can_manage_holidays

_CTX = "registrar.calendar"


def _error(message, *, status=400, code="invalid", field=""):
    payload = {"ok": False, "error": code, "message": str(message)}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def _save(request, organization):
    from apps.organizations.public import save_holiday

    holiday, created = save_holiday(
        organization=organization,
        actor=request.user,
        request=request,
        holiday_id=request.POST.get("id") or "",
        raw_date=request.POST.get("date") or "",
        name=request.POST.get("name") or "",
        kind=request.POST.get("kind") or "",
        note=request.POST.get("note") or "",
    )
    message = pgettext(_CTX, "Gün təqvimə əlavə olundu.") if created else pgettext(_CTX, "Dəyişiklik yadda saxlanıldı.")
    return JsonResponse({"ok": True, "id": str(holiday.pk), "created": created, "message": message})


def _delete(request, organization):
    from apps.organizations.public import delete_holiday

    delete_holiday(organization=organization, actor=request.user, request=request, holiday_id=request.POST.get("id"))
    return JsonResponse({"ok": True, "message": pgettext(_CTX, "Gün təqvimdən silindi.")})


def _seed_fixed(request, organization):
    from apps.organizations.public import holiday_academic_year_start, seed_fixed_holidays

    start_year = holiday_academic_year_start(request.POST.get("academic_year"))
    if start_year is None:
        return _error(pgettext(_CTX, "Tədris ili seçilməyib."), code="bad_year", field="academic_year")
    result = seed_fixed_holidays(organization=organization, actor=request.user, request=request, start_year=start_year)
    message = pgettext(
        _CTX, "%(year)s: təqvimə %(created)d gün əlavə olundu, %(skipped)d tarix artıq təqvimdə idi."
    ) % {
        "year": result["academic_year"],
        "created": result["created"],
        "skipped": result["skipped"],
    }
    return JsonResponse({"ok": True, "message": message, **result})


_HANDLERS = {"save": _save, "delete": _delete, "seed_fixed": _seed_fixed}


@login_required
@require_POST
def holiday_action(request):
    from apps.organizations.public import HolidayError

    organization = getattr(request, "organization", None)
    if organization is None:
        return _error(pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur."), status=403, code="no_org")
    if getattr(request, "is_view_as", False):
        return JsonResponse(
            {
                "ok": False,
                "view_as_blocked": True,
                "detail": pgettext(_CTX, "Başqasının adından baxış rejimində dəyişiklik etmək olmaz."),
            },
            status=403,
        )
    if not can_manage_holidays(request, organization):
        return _error(
            pgettext(_CTX, "Bayram təqvimini dəyişmək üçün səlahiyyətiniz yoxdur."), status=403, code="forbidden"
        )
    handler = _HANDLERS.get((request.POST.get("action") or "").strip())
    if handler is None:
        return _error(pgettext(_CTX, "Naməlum əməl."), code="unknown_action")
    try:
        return handler(request, organization)
    except HolidayError as exc:
        return _error(exc.message, status=exc.status, code=exc.code, field=exc.field)


__all__ = ["holiday_action"]
