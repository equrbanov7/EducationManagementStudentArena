"""«Mühasibatlıq» → «Dərs saatının ödəniş dərəcələri» — yazı endpoint-ləri (sahib 2026-10-19).

``POST /accounts/accounting/rates/`` — dərəcəni yarat / dəyiş (köhnə aktiv sətir arxivlənir, tarixçə qalır);
``POST /accounts/accounting/rates/<uuid>/archive/`` — «Sil» (sətir silinmir, «ləğv edildi» ilə arxivlənir).

Qapı (fail-closed, yazıdan ƏVVƏL): bölmə qapısı (``accounting.view`` — ``policy.resolve_actor``) + ``accounting.manage_fees``
TƏŞKİLAT əhatəsində (``rates.can_manage``). Açar yoxdursa 403, başqa təşkilatın / arxivlənmiş / mövcud olmayan sətir
404, «Başqasının adından» rejimində 403 (``view_as_blocked``). Cavab: ``{"ok": bool, "message" | "error": str}``.
Hər yazı ``core.audit.log_action``-a düşür (servis qatı).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from ..services.accounting import constants as C
from ..services.accounting import rates
from ..services.accounting.policy import resolve_actor


def _deny(error: str, status: int, **extra):
    return JsonResponse({"ok": False, "error": error, **extra}, status=status)


def _gate(request):
    """(aktor, xəta cavabı) — xəta varsa yazı ümumiyyətlə başlamır."""
    actor = resolve_actor(request)
    if actor.view_as:
        detail = pgettext(C.CTX, "Başqasının adından baxış rejimində dəyişiklik etmək olmaz.")
        return actor, _deny(detail, 403, view_as_blocked=True, detail=detail)
    if not actor.has_access or not rates.can_manage(actor.user, actor.organization, request=request):
        return actor, _deny(pgettext(C.CTX, "Ödəniş dərəcələrini yalnız Mühasibatlıq dəyişə bilər."), 403)
    return actor, None


def _run(callable_, success: str):
    try:
        callable_()
    except ObjectDoesNotExist:
        return _deny(pgettext(C.CTX, "Dərəcə tapılmadı."), 404)
    except PermissionDenied:
        return _deny(pgettext(C.CTX, "Ödəniş dərəcələrini yalnız Mühasibatlıq dəyişə bilər."), 403)
    except ValidationError as exc:
        return _deny("; ".join(str(message) for message in exc.messages), 400)
    response = JsonResponse({"ok": True, "message": success})
    response["Cache-Control"] = "private, no-store"
    return response


def _field(request, name: str) -> str:
    return str(request.POST.get(name) or "").strip()


@never_cache
@login_required
@require_POST
def accounting_rate_save(request):
    actor, denied = _gate(request)
    if denied is not None:
        return denied
    return _run(
        lambda: rates.save_rate(
            actor=request.user,
            organization=actor.organization,
            academic_year=_field(request, "academic_year"),
            position=_field(request, "position"),
            activity=_field(request, "activity"),
            hourly_rate=_field(request, "hourly_rate"),
            note=_field(request, "note"),
            request=request,
        ),
        pgettext(C.CTX, "Ödəniş dərəcəsi yadda saxlanıldı."),
    )


@never_cache
@login_required
@require_POST
def accounting_rate_archive(request, rate_id):
    actor, denied = _gate(request)
    if denied is not None:
        return denied
    return _run(
        lambda: rates.archive_rate(
            actor=request.user, organization=actor.organization, rate_id=rate_id, request=request
        ),
        pgettext(C.CTX, "Dərəcə ləğv edildi — tarixçədə qalır."),
    )


__all__ = ["accounting_rate_archive", "accounting_rate_save"]
