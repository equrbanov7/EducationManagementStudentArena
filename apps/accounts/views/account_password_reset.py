"""«Parol sıfırlama» JSON endpoint-ləri — axtarış + sıfırlama (sahib, 2026-09-30).

Hər ikisi YALNIZ POST + CSRF (Django middleware; `csrf_exempt` YOXDUR) və
`never_cache`-dir. Axtarış da POST-dur: istifadəçi adı/ad-soyad URL-ə (server
access log-una, brauzer tarixçəsinə) düşməsin.

Qapılar servis qatındadır (`services/password_reset_admin.py`) — view yalnız
girişi oxuyur və xətanı JSON-a çevirir. Xam parol yalnız sıfırlama cavabında,
bir dəfə qayıdır; heç yerdə saxlanılmır və loglanmır.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from ..services.password_reset_admin import (
    PasswordResetError,
    audit_denied,
    enforce_lookup_rate,
    enforce_reset_rate,
    enforce_suggest_rate,
    operator_for,
    reset_password,
)
from ..services.password_reset_lookup import lookup, serialize_candidates, suggest

_CTX = "accounts.password_reset"


def _read_payload(request) -> dict:
    """JSON gövdəsi (və ya form-encoded POST)."""
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {key: value for key, value in request.POST.items()}


def _error(exc: PasswordResetError) -> JsonResponse:
    return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=exc.status)


@never_cache
@login_required
@require_POST
def account_password_reset_lookup(request):
    """İstifadəçi adı (dəqiq) və ya ad/soyad (dözümlü) ilə hədəf axtarışı."""
    try:
        enforce_lookup_rate(request)
        actor = operator_for(request)
        result = lookup(actor, _read_payload(request).get("q"))
    except PasswordResetError as exc:
        return _error(exc)
    return JsonResponse({"ok": True, **result})


@never_cache
@login_required
@require_POST
def account_password_reset_suggest(request):
    """Yazdıqca təklif (yüngül siyahı) — seçim sonra ``lookup`` ilə tam karta çevrilir."""
    try:
        enforce_suggest_rate(request)
        actor = operator_for(request)
        results = suggest(actor, _read_payload(request).get("q"))
    except PasswordResetError as exc:
        return _error(exc)
    return JsonResponse({"ok": True, "results": results})


@never_cache
@login_required
@require_POST
def account_password_reset_perform(request):
    """Seçilmiş hədəfə müvəqqəti parol verir — parol cavabda BİR DƏFƏ qayıdır."""
    target_id = _read_payload(request).get("user_id")
    actor = None
    try:
        enforce_reset_rate(request)
        actor = operator_for(request, for_write=True)
        target, raw_password = reset_password(actor, target_id, request=request)
    except PasswordResetError as exc:
        audit_denied(actor, request, target_id, exc.code)
        return _error(exc)

    return JsonResponse(
        {
            "ok": True,
            "password": raw_password,
            "user": serialize_candidates(actor, [target])[0],
            "message": pgettext(
                _CTX, "Müvəqqəti parol yaradıldı. İstifadəçi ilk girişdə öz parolunu qurmağa məcbur olacaq."
            ),
        }
    )


def _js_strings() -> dict:
    """Xarici JS-in mətnləri — `json_script` ilə ötürülür (JS tərcümə tag-larından keçmir)."""
    return {
        "searching": pgettext(_CTX, "Axtarılır…"),
        "suggestEmpty": pgettext(_CTX, "Uyğun istifadəçi yoxdur — adı və ya soyadı yoxlayın."),
        "suggestHint": pgettext(_CTX, "Seçmək üçün klikləyin və ya ↑ ↓ və Enter istifadə edin."),
        "noResults": pgettext(_CTX, "Heç kim tapılmadı. İstifadəçi adını yoxlayın və ya ad və soyadla axtarın."),
        "hasMore": pgettext(_CTX, "Nəticə çoxdur — yalnız ilk 8-i göstərilir. Sorğunu dəqiqləşdirin."),
        "found": pgettext(_CTX, "Şəxsiyyəti sənədlə yoxlayın və yalnız sonra parolu sıfırlayın."),
        "username": pgettext(_CTX, "İstifadəçi adı"),
        "roles": pgettext(_CTX, "Rol"),
        "units": pgettext(_CTX, "Qrup / bölmə"),
        "lastLogin": pgettext(_CTX, "Son giriş"),
        "pendingChange": pgettext(_CTX, "Əvvəlki müvəqqəti parol hələ dəyişdirilməyib"),
        "reset": pgettext(_CTX, "Parolu sıfırla"),
        "resetting": pgettext(_CTX, "Sıfırlanır…"),
        "confirmTitle": pgettext(_CTX, "Parol sıfırlansın?"),
        "confirmBody": pgettext(
            _CTX,
            "{name} ({username}) üçün yeni müvəqqəti parol yaradılacaq.\n"
            "Köhnə parol dərhal etibarsız olacaq, istifadəçinin bütün açıq sessiyaları bağlanacaq.\n"
            "İstifadəçinin şəxsiyyətini yoxladınız?",
        ),
        "confirmOk": pgettext(_CTX, "Bəli, sıfırla"),
        "resultFor": pgettext(_CTX, "{name} ({username}) üçün müvəqqəti parol:"),
        "copied": pgettext(_CTX, "Parol kopyalandı."),
        "copyFailed": pgettext(_CTX, "Kopyalamaq alınmadı — parolu əl ilə yazın."),
        "genericError": pgettext(_CTX, "Xəta baş verdi. Yenidən cəhd edin."),
    }


def build_panel_context(request) -> dict:
    """Bölmə paneli (`{% account_password_reset_panel %}` tag-ı) üçün çərçivə.

    Server yalnız icazəni və endpoint URL-lərini verir; axtarış/sıfırlama JSON-la
    gedir. İcazə burada yalnız GÖRÜNÜŞ üçündür — faktiki qapı endpoint-lərdədir.
    """
    from django.urls import reverse

    try:
        actor = operator_for(request)
    except PasswordResetError as exc:
        return {"has_access": False, "denied_message": exc.message}
    return {
        "has_access": True,
        "denied_message": "",
        "organization_name": getattr(actor.organization, "name", "") or "",
        "lookup_url": reverse("accounts:account_password_reset_lookup"),
        "suggest_url": reverse("accounts:account_password_reset_suggest"),
        "reset_url": reverse("accounts:account_password_reset_perform"),
        "js_strings": _js_strings(),
    }


__all__ = [
    "account_password_reset_lookup",
    "account_password_reset_perform",
    "account_password_reset_suggest",
    "build_panel_context",
]
