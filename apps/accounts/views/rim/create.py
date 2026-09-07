"""RİM «yeni hesab» endpoint-ləri — tək-tək yaratma + seçici kataloqu.

İki marşrut:

* ``rim_create_account``  — POST (JSON): bir tələbə və ya müəllim hesabı;
  cavabda BİRDƏFƏLİK parol (heç yerdə saxlanılmır);
* ``rim_create_catalog``  — GET (JSON): qrup / kafedra type-ahead siyahısı.

Hər ikisi FAIL-CLOSED: icazə şablonda deyil, MƏHZ burada (servis qatında)
yoxlanılır — `services/rim/create.py::require_create` (``user.import`` +
aktiv təşkilat konteksti + aktiv üzvlük).

TOPLU (fayl) axını üçün ayrıca endpoint YAZILMIR: RİM konsolu mövcud
``accounts:student_intake_preview`` / ``…_apply`` marşrutlarını çağırır — onlar
eyni ``user.import`` qapısındandır və eyni plan qurucusundan keçir, ona görə
«gördüyün nəticə = alacağın nəticə» müqaviləsi iki səthdə də eynidir.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.services.rim import RimAccessError, resolve_actor
from apps.accounts.services.rim.create import MAX_NOTE_LENGTH, create_account
from apps.accounts.services.rim.create_form import COMMON_FIELDS, STUDENT_FIELDS, TEACHER_FIELDS
from apps.accounts.services.rim.create_options import DEFAULT_LIMIT, search_catalog

#: Formdan qəbul edilən sahələrin allow-list-i (naməlum açar sükutla atılır).
ACCEPTED_FIELDS = frozenset(COMMON_FIELDS + STUDENT_FIELDS + TEACHER_FIELDS)


def _error_response(exc: RimAccessError) -> JsonResponse:
    payload = {"ok": False, "error": exc.reason_code, "message": exc.message}
    fields = getattr(exc, "fields", None)
    if fields:
        payload["fields"] = fields
    return JsonResponse(payload, status=exc.status)


def _read_payload(request) -> dict:
    content_type = (request.content_type or "").lower()
    if "application/json" in content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {key: value for key, value in request.POST.items()}


@never_cache
@login_required
@require_POST
def rim_create_account(request):
    """Bir tələbə / müəllim hesabı yaradır (birdəfəlik parol cavabda)."""

    actor = resolve_actor(request)
    payload = _read_payload(request)
    data = {key: payload.get(key, "") for key in ACCEPTED_FIELDS}

    try:
        result = create_account(
            actor,
            kind=payload.get("kind", ""),
            data=data,
            request=request,
            note=str(payload.get("note") or "")[:MAX_NOTE_LENGTH],
        )
    except RimAccessError as exc:
        # `RimCreateError` bunun alt sinfidir — sahə xətaları `_error_response`
        # tərəfindən `fields` açarı ilə əlavə olunur.
        return _error_response(exc)

    return JsonResponse({"ok": True, **result})


@never_cache
@login_required
@require_GET
def rim_create_catalog(request):
    """Qrup / kafedra / valideyn bölmə seçicisinin axtarış nəticələri.

    ``request`` servisə ÖTÜRÜLÜR: valideyn kataloqu struktur əhatəsini
    (``unit.view``) həll edir və resolver sorğu başına keşlənir.
    """

    actor = resolve_actor(request)
    try:
        payload = search_catalog(
            actor,
            catalog=request.GET.get("catalog", ""),
            query=request.GET.get("q", ""),
            limit=request.GET.get("limit", DEFAULT_LIMIT),
            offset=request.GET.get("offset", 0),
            request=request,
        )
    except RimAccessError as exc:
        return _error_response(exc)
    return JsonResponse({"ok": True, **payload})


__all__ = ["rim_create_account", "rim_create_catalog"]
