"""«Bölgü sehrbazı» endpoint-ləri — fənn kartının seminar / laboratoriya bölgüsü addım-addım (sahib 2026-11-26).

* ``GET  bolgu/sehrbaz/?task=<id>&rows=<id,id>`` — sehrbazın açılış datası (:func:`.services.split_wizard.wizard_state`);
* ``POST bolgu/sehrbaz/yadda-saxla/`` — jurnal bölmələri + sətir cəmi + bölgülər BİR tranzaksiyada
  (:func:`.services.split_wizard_apply.apply_wizard`; gövdə — modulun başlığında);
* ``POST bolgu/sehrbaz/jurnal/`` — «Jurnalı indi yarat» (plan kafedraya çatıbsa, mövcud açılış sinxronu ilə).

Fail-closed: icazə/əhatə — 403; giriş xətası — 400; düzəliş tələbi / bağlı jurnal / cəm toqquşması — 409.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from core.write_rate_limit import score_write_rate_limited

from ..services import WorkloadDenied, amend_from_payload
from ..services.split_wizard import WIZARD_INPUT_CODES, wizard_state
from ..services.split_wizard_apply import apply_wizard, ensure_journals
from ._base import active_organization, actor_for, denied, json_body, no_org
from .distribution_api import _resolve_task, _task_payload, _write_denied

_WIZARD_CONFLICTS = frozenset({"workload.wizard_blocked", "workload.wizard_refresh"})
_WIZARD_FORBIDDEN = frozenset({"workload.wizard_forbidden"})


def _wizard_denied(exc: WorkloadDenied) -> JsonResponse:
    if exc.code in WIZARD_INPUT_CODES:
        return denied(exc, status=400)
    if exc.code in _WIZARD_CONFLICTS:
        return denied(exc, status=409)
    if exc.code in _WIZARD_FORBIDDEN:
        return denied(exc, status=403)
    return _write_denied(exc)


@never_cache
@login_required
@require_GET
def split_wizard_state(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    actor = actor_for(request)
    try:
        task = _resolve_task(request, actor, task_id=request.GET.get("task") or None)
        state = wizard_state(task=task, actor=actor, row_ids=request.GET.get("rows") or "")
    except WorkloadDenied as exc:
        return _wizard_denied(exc)
    return JsonResponse({"ok": True, **state})


@never_cache
@login_required
@require_POST
@score_write_rate_limited("workload_assign")
def split_wizard_save(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    try:
        task = _resolve_task(request, actor, task_id=payload.get("task_id"))
        summary = apply_wizard(
            task=task, actor=actor, payload=payload, amend=amend_from_payload(payload), request=request
        )
    except WorkloadDenied as exc:
        return _wizard_denied(exc)
    task.refresh_from_db()
    return JsonResponse({"ok": True, "summary": summary, "task": _task_payload(task)})


@never_cache
@login_required
@require_POST
def split_wizard_journals(request) -> JsonResponse:
    organization = active_organization(request)
    if organization is None:
        return no_org()
    payload = json_body(request)
    actor = actor_for(request)
    try:
        task = _resolve_task(request, actor, task_id=payload.get("task_id"))
        report = ensure_journals(task=task, actor=actor, row_ids=payload.get("row_ids"), request=request)
    except WorkloadDenied as exc:
        return _wizard_denied(exc)
    return JsonResponse({"ok": True, "report": report})


__all__ = ["split_wizard_journals", "split_wizard_save", "split_wizard_state"]
