"""«Akademik fəaliyyət» qeydləri üçün JSON endpoint (profil redaktəsi).

Nazik HTTP qatı: bütün validasiya/sahiblik/limit məntiqi
``services.academic_profile``-dədir. Cavab formatı fetchJSON istehlakçısı
üçün: ``{"success": bool, "error": str?, "html": str?}`` — ``html`` uğurda
yenilənmiş idarəetmə siyahısının render olunmuş fraqmentidir (client swap
edir, i18n server tərəfdə qalır). Hər uğurlu dəyişiklik audit jurnalına yazılır.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.audit.public import log_action
from core.constants import AuditAction

from ...services import academic_profile
from .._helpers import _role_capabilities

#: action → audit sabiti (uğurlu əməliyyatlar jurnala yazılır).
_AUDIT_ACTIONS = {
    "create": AuditAction.CREATE,
    "update": AuditAction.UPDATE,
    "delete": AuditAction.DELETE,
}


def _manage_list_html(request, capabilities):
    """İdarəetmə siyahısı fraqmentini yenidən render edir (AJAX swap üçün)."""
    return render_to_string(
        "accounts/profile/sections/_academic_items_manage.html",
        {
            "academic_item_groups": academic_profile.items_grouped_for(request.user, capabilities),
        },
        request=request,
    )


def _log_item_action(request, *, action, item_id, summary, attachment_event=""):
    """Uğurlu qeyd əməliyyatını audit jurnalına yazır.

    ``attachment_event`` (uploaded / replaced / removed) fayl dəyişikliyini
    ayrıca iz kimi saxlayır — kim, nə vaxt, hansı qeydə sənəd qoşub/silib.
    """
    reason = f"Academic profile item {action}"
    changes = None
    if attachment_event:
        reason = f"{reason}; attachment {attachment_event}"
        changes = {"attachment": attachment_event}
    log_action(
        action=_AUDIT_ACTIONS[action],
        user=request.user,
        reason=reason,
        changes=changes,
        request=request,
        resource_type="AcademicProfileItem",
        resource_id=str(item_id),
        resource_repr=summary[:200],
    )


def _item_summary(item):
    summary = f"{item.kind}: {item.title}"
    if item.attachment_name:
        summary = f"{summary} [{item.attachment_name}]"
    return summary


@login_required
@require_POST
def academic_items_api(request):
    """create / update / delete əməliyyatları — yalnız öz qeydləri üzərində.

    Sorğu ``multipart/form-data``-dır (2026-10-01): ``attachment`` faylı və
    ``remove_attachment=1`` bayrağı qəbul olunur; urlencoded sorğu da işləyir.
    """
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)

    not_found_error = str(academic_profile.NOT_FOUND_ERROR)
    action = (request.POST.get("action") or "").strip()
    item_id_raw = (request.POST.get("item_id") or "").strip()
    fields = {
        "kind": request.POST.get("kind", ""),
        "title": request.POST.get("title", ""),
        "detail": request.POST.get("detail", ""),
        "year": request.POST.get("year", ""),
        "link": request.POST.get("link", ""),
        "attachment": request.FILES.get("attachment"),
    }

    if action == "create":
        ok, item, error = academic_profile.create_item(request.user, capabilities, **fields)
        if ok:
            _log_item_action(
                request,
                action=action,
                item_id=item.pk,
                summary=_item_summary(item),
                attachment_event=item.attachment_event,
            )
    elif action == "update":
        if not item_id_raw.isdigit():
            return JsonResponse({"success": False, "error": not_found_error}, status=404)
        ok, item, error = academic_profile.update_item(
            request.user,
            capabilities,
            int(item_id_raw),
            remove_attachment=(request.POST.get("remove_attachment") or "").strip() == "1",
            **fields,
        )
        if ok:
            _log_item_action(
                request,
                action=action,
                item_id=item.pk,
                summary=_item_summary(item),
                attachment_event=item.attachment_event,
            )
    elif action == "delete":
        if not item_id_raw.isdigit():
            return JsonResponse({"success": False, "error": not_found_error}, status=404)
        ok, error = academic_profile.delete_item(request.user, int(item_id_raw))
        if ok:
            _log_item_action(request, action=action, item_id=item_id_raw, summary="deleted")
    else:
        return JsonResponse(
            {"success": False, "error": pgettext("accounts.academic_items.error", "Naməlum əməliyyat.")},
            status=400,
        )

    if not ok:
        status = 404 if error == not_found_error else 400
        return JsonResponse({"success": False, "error": error}, status=status)

    return JsonResponse({"success": True, "html": _manage_list_html(request, capabilities)})
