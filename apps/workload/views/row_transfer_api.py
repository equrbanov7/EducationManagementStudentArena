"""Kafedralararası yük köçürməsi: eyni tenant, iki tərəfli RBAC, POST/CSRF."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from core.http_ids import parse_uuid
from core.write_rate_limit import score_write_rate_limited

from ..services.row_edit import AMENDMENT_REQUIRED, amend_from_payload
from ..services.row_transfer import destinations, source_row, transfer_row
from ..services.scoping import WorkloadDenied
from ._base import active_organization, actor_for, denied, error, json_body, no_org


def _ids(payload):
    row_id, task_id = parse_uuid(payload.get("row_id")), parse_uuid(payload.get("task_id"))
    if row_id is None or task_id is None:
        raise WorkloadDenied("workload.transfer_source_changed", "Sətir və tapşırıq düzgün seçilməyib.")
    return row_id, task_id


@never_cache
@login_required
@require_GET
def row_transfer_destinations(request):
    if active_organization(request) is None:
        return no_org()
    actor = actor_for(request)
    try:
        row_id, task_id = _ids(request.GET)
        row = source_row(actor=actor, row_id=row_id, task_id=task_id)
        results = destinations(actor=actor, row=row)
    except WorkloadDenied as exc:
        return denied(exc)
    return JsonResponse({"ok": True, "results": results})


@never_cache
@login_required
@require_POST
@score_write_rate_limited("workload_row_transfer")
def row_transfer(request):
    if active_organization(request) is None:
        return no_org()
    actor = actor_for(request)
    payload = json_body(request)
    try:
        row_id, task_id = _ids(payload)
        destination = parse_uuid(payload.get("destination_chair_id"))
        if destination is None:
            return error("workload.transfer_destination", "Hədəf kafedra seçilməyib.")
        result = transfer_row(
            actor=actor,
            row_id=row_id,
            source_task_id=task_id,
            destination_chair_id=destination,
            amend=amend_from_payload(payload),
            request=request,
        )
    except WorkloadDenied as exc:
        status = 409 if exc.code.startswith("workload.transfer_") or exc.code == AMENDMENT_REQUIRED else 403
        return denied(exc, status=status)
    return JsonResponse({"ok": True, **result})
