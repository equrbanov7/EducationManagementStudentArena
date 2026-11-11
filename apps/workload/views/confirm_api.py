"""«Bölgünü təsdiqlə» endpoint-i (``bolgu/tesdiq/``).

Sahib 2026-11-12: natamam bölgüdə cavab 409 + sətir siyahısıdır (``readiness.incomplete_rows`` — fənn, qruplar,
ixtisas, fəaliyyət üzrə qalıq saat); dialoq «Aydındır, Vakant saxla və təsdiqlə» ilə ``fill_vacant=1`` göndərir
və server qalan saatları «Vakant» yazıb təsdiqləyir (``services.confirm_vacant``). Artıq bölgü — sərt maneə (409).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from ..public import STATUS_LABELS
from ..services import WorkloadDenied, amend_from_payload, confirm_distribution, distribution_readiness
from ..services.confirm_vacant import INTENSIVE_INCOMPLETE, confirm_with_vacant
from ..services.distribution import INCOMPLETE, OVER_ASSIGNED
from ._base import active_organization, actor_for, json_body, no_org
from .distribution_api import _resolve_task, _truthy, _write_denied

#: Bu kodlarda cavaba sətir siyahısı (``readiness``) qoşulur — UI maneəni sətir-sətir göstərir.
_READINESS_CODES = frozenset({INCOMPLETE, OVER_ASSIGNED, INTENSIVE_INCOMPLETE})


def _blocked(exc: WorkloadDenied, task) -> JsonResponse:
    body = {"ok": False, "error": exc.code, "message": exc.message, "readiness": distribution_readiness(task)}
    return JsonResponse(body, status=409)


@never_cache
@login_required
@require_POST
def confirm(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    instance = None
    try:
        instance = _resolve_task(request, actor, task_id=payload.get("task_id"))
        if _truthy(payload.get("fill_vacant")):
            result = confirm_with_vacant(task=instance, actor=actor, request=request, amend=amend_from_payload(payload))
        else:
            result = confirm_distribution(
                task=instance,
                actor=actor,
                allow_vacant=str(payload.get("allow_vacant") or "1").lower() not in ("0", "false", "no"),
                request=request,
            )
    except WorkloadDenied as exc:
        if instance is not None and exc.code in _READINESS_CODES:
            instance.refresh_from_db()  # tranzaksiya geri qayıdıb — status/sətirlər bazadakı kimi
            return _blocked(exc, instance)
        # Qalan kodlar (icazə — 403, düzəliş səbəbi / saat toqquşması — 409, yanlış giriş — 400) yazı qaydası ilə.
        return _write_denied(exc)
    return JsonResponse(
        {
            "ok": True,
            "status": result["status"],
            "status_label": STATUS_LABELS.get(result["status"], result["status"]),
            # QA-2 F-09: id siyahıları (``offering_ids``, ``group_offering_ids`` — yüzlərlə UUID) UI-a lazım deyil.
            "sync": {
                key: value for key, value in result["sync"].items() if key not in ("offering_ids", "group_offering_ids")
            },
            "notified": result["notified"],
            "vacant_filled": result.get("vacant_filled") or {"rows": 0, "hours": 0},
        }
    )


__all__ = ["confirm"]
