"""Fənn təhvilinin YAZMA endpoint-i — TƏK POST marşrutu + ``action`` allow-list-i.

``people`` kataloqundakı naxışın eynisidir və eyni səbəbdən: hər əməl eyni
ön-şərt zəncirindən keçir (aktor → icazə → əhatə → bloker → audit); marşrutları
parçalasaq zəncir iki yerdə təkrarlanardı.

⚠️ SƏBƏB HƏR İKİ ƏMƏLDƏ MƏCBURİDİR. Təhvil jurnalın sahibliyini dəyişir; geri
qaytarma isə onu yenidən dəyişir. «Niyə» sualı audit sətrində cavabsız qalmamalıdır.
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.registrar import handover_actions as handover_write

from .labels import error_message
from .policy import resolve_actor

logger = logging.getLogger(__name__)

#: Allow-list — naməlum `action` 400 verir (səssiz keçid yoxdur).
ALLOWED_ACTIONS = frozenset({"reassign", "revert"})


def _read_payload(request) -> dict:
    """Gövdəni sözlüyə çevirir — JSON və forma kodlaşdırması üçün EYNİ forma.

    ⚠️ ``request.POST.items()`` təkrarlanan sahənin YALNIZ SONUNCU dəyərini
    verir. Kabinet paneli seçilmiş fənləri məhz təkrarlanan ``offering_ids``
    sahələri ilə göndərir (ortaq dialoq mexanizmi formanı olduğu kimi POST edir),
    ona görə çoxdəyərli açarlar SİYAHI kimi oxunur.
    """
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {key: (values[0] if len(values) == 1 else values) for key, values in request.POST.lists()}


def _error(code, message, status=400, codes=()):
    """JSON xəta cavabı.

    ``codes`` yalnız ``code == "blocked"`` halında dolur — UI hər blokeri ayrıca
    göstərmək istəsə mətni yenidən parçalamağa məcbur qalmasın (mesaj artıq
    birləşdirilmiş və tərcümə olunmuş formadadır).
    """
    payload = {"ok": False, "error": code, "message": message}
    if codes:
        payload["codes"] = list(codes)
    return JsonResponse(payload, status=status)


@never_cache
@login_required
@require_POST
def handover_action(request):
    """Təhvil əməllərinin vahid giriş nöqtəsi."""
    actor = resolve_actor(request)
    if not actor.has_access:
        return _error("permission_denied", error_message("permission_denied"), status=403)

    payload = _read_payload(request)
    action = str(payload.get("action") or "").strip()
    if action not in ALLOWED_ACTIONS:
        return _error("unknown_action", error_message("unknown_action"))

    reason = payload.get("reason") or ""
    try:
        if action == "reassign":
            result = handover_write.bulk_reassign(
                actor=actor.user,
                organization=actor.organization,
                items=_normalize_items(payload),
                reason=reason,
                request=request,
            )
        else:
            result = handover_write.revert(
                actor=actor.user,
                organization=actor.organization,
                handover_id=str(payload.get("handover_id") or "").strip(),
                reason=reason,
                request=request,
            )
    except PermissionDenied:
        # ⚠️ `str(exc)` QƏSDƏN İŞLƏDİLMİR: servis mətnləri AZ-dır və birbaşa
        # cavaba düşsəydi digər üç dildə istifadəçi azərbaycanca mesaj görərdi.
        return _error("permission_denied", error_message("permission_denied"), status=403)
    except handover_write.HandoverError as exc:
        # Servis mesajı AZ-dır və yalnız son çarə fallback-dır; «blocked» halında
        # mətn kodlardan, aktiv dildə və əməlin istiqamətinə görə qurulur.
        codes = getattr(exc, "codes", ())
        message = error_message(exc.code, exc.message, codes=codes, action=action)
        return _error(exc.code, message, status=exc.status, codes=codes)

    return JsonResponse({"ok": True, **result})


def _normalize_items(payload) -> list:
    """Girişi ``[{offering_id, new_instructor_id}, …]`` formasına gətirir.

    ÜÇ forma dəstəklənir və hər birinin öz səbəbi var:

    * ``items`` (JSON siyahısı) — hər sətrə AYRI müəllim; servisin əsl müqaviləsi;
    * ``offering_ids`` (təkrarlanan sahə) + ``new_instructor_id`` — kabinet
      panelinin toplu təsdiqi: seçilmiş fənlərin HAMISI eyni müəllimə gedir
      (ən tez-tez rast gəlinən hal: «müəllim işdən çıxdı»). Sətir-sətir fərqli
      müəllim lazımdırsa sətrin öz «Təhvil ver» düyməsi ilə ayrıca aparılır —
      hər əməl onsuz da atomik və auditlidir;
    * ``offering_id`` (tək) — jurnal səhifəsindən gələcək tək-sətir düyməsi.
    """
    items = payload.get("items")
    if isinstance(items, str) and items.strip():
        try:
            items = json.loads(items)
        except ValueError:
            items = None
    if isinstance(items, list):
        rows = []
        for row in items:
            if not isinstance(row, dict):
                continue
            offering_id = str(row.get("offering_id") or "").strip()
            target_id = str(row.get("new_instructor_id") or "").strip()
            if offering_id:
                rows.append({"offering_id": offering_id, "new_instructor_id": target_id})
        return rows

    target = str(payload.get("new_instructor_id") or "").strip()
    bulk = payload.get("offering_ids")
    if isinstance(bulk, str):
        bulk = [bulk]
    if isinstance(bulk, (list, tuple)):
        rows = [
            {"offering_id": str(value).strip(), "new_instructor_id": target}
            for value in bulk
            if str(value or "").strip()
        ]
        if rows:
            return rows

    offering_id = str(payload.get("offering_id") or "").strip()
    if offering_id:
        return [{"offering_id": offering_id, "new_instructor_id": target}]
    return []


__all__ = ["ALLOWED_ACTIONS", "handover_action"]
