"""«Bu müəllimə bərpa et» — jurnal siyahısının tarixçə sətrindən JSON POST (CSRF; view-as: yalnız tam rejim)."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from ..services.history_teacher_restore import CTX, Denied, restore_for_teacher
from ..services.scoping import WorkloadDenied
from ._base import active_organization, denied, json_body, no_org


@never_cache
@login_required
@require_POST
def history_teacher_restore(request, offering_id):
    if active_organization(request) is None:
        return no_org()
    payload = json_body(request)
    try:
        result = restore_for_teacher(
            request=request,
            offering_id=offering_id,
            reason=payload.get("reason"),
            teacher_id=payload.get("teacher"),
        )
    except Denied as exc:
        return denied(exc, status=exc.status)
    except WorkloadDenied as exc:
        return denied(exc, status=409)
    except PermissionDenied:
        return JsonResponse(
            {
                "ok": False,
                "error": "workload.history_teacher_restore_denied",
                "message": pgettext(CTX, "Bu əməliyyat üçün səlahiyyətiniz yoxdur."),
            },
            status=403,
        )
    if result["status"] == "already_current":
        text = pgettext(CTX, "Jurnal artıq bu müəllimin cari dərs yükündədir.")
    else:
        text = pgettext(CTX, "Jurnal müəllimin cari dərs yükünə bərpa edildi.")
    return JsonResponse({"ok": True, "message": text, **result})
