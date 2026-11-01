"""CSRF-protected reason-only attendance actions; exact offering tenant and RBAC."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from core.http_ids import parse_uuid

from . import excused_management
from .journal_access import writable_offering_or_404
from .models import CourseOffering


@login_required
@require_POST
def manage(request, offering_id):
    org = getattr(request, "organization", None)
    if org is None:
        raise Http404
    offering = writable_offering_or_404(get_object_or_404(CourseOffering, pk=offering_id, organization=org))
    if not excused_management.can_manage(request, offering):
        raise Http404
    try:
        excused_management.manage(
            request=request,
            offering=offering,
            mark_id=parse_uuid(request.POST.get("mark_id")),
            operation=request.POST.get("operation"),
            reason=request.POST.get("reason"),
            expected_status=request.POST.get("expected_status"),
            expected_correction_id=request.POST.get("expected_correction_id"),
            new_status=request.POST.get("new_status"),
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=409)
    return JsonResponse({"ok": True})
