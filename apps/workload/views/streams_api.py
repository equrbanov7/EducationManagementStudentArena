"""Mühazirə axınları (patok) endpoint-i — «bir fənn = bir kart» seçicisi (sahib 2026-11-09).

POST ``patok/axinlar/`` gövdəsi::

    {"task_id": "...", "streams": [{"row_ids": ["...", "..."], "teacher_id": "<id> | vacant"}, ...],
     "amend_reason": "...", "amend_note": "..."}   # təsdiqlənmiş sənəddə məcburi (409 → UI dialoqu)

Fail-closed: icazə/əhatə ``WorkloadDenied`` → 403; giriş xətaları 400; düzəliş tələbi 409.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from ..services import WorkloadDenied, amend_from_payload
from ..services.patok_streams import apply_streams
from ._base import active_organization, actor_for, json_body, no_org
from .distribution_api import _resolve_task, _write_denied


@never_cache
@login_required
@require_POST
def patok_streams(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    try:
        task = _resolve_task(request, actor, task_id=payload.get("task_id"))
        result = apply_streams(
            task=task, actor=actor, streams=payload.get("streams"), amend=amend_from_payload(payload), request=request
        )
    except WorkloadDenied as exc:
        return _write_denied(exc)
    return JsonResponse({"ok": True, **result})


__all__ = ["patok_streams"]
