"""«Arayış sorğusu» → «Arayışı hazırla və əlavə et» (sahib 2026-10-19) — JSON endpoint.

Qaydalar ``services.documents``-dədir (emalçı + ``transcript.issue`` əhatəsi + aktiv tələbə; view-as 403).
Cavab adi əməl cavabı ilə eynidir: yenilənmiş DETAL payload-u (yeni qeyd + əlavə olunmuş PDF).
"""

from __future__ import annotations

from django.views.decorators.http import require_POST

from ..services import documents
from ._base import error, json_endpoint, load_application, ok


def detail_with_tools(application, *, request) -> dict:
    """``detail_payload`` + «Arayış hazırla» bloku (yalnız uyğun emalçıya; əks halda ``None``)."""
    from ..payloads import detail_payload

    payload = detail_payload(application, user=request.user)
    payload["arayis_tool"] = documents.arayis_tool(application, user=request.user, request=request)
    return payload


@require_POST
@json_endpoint
def application_issue_arayis(request, application_id, *, organization):
    application = load_application(request, organization, application_id)
    if application is None:
        return error("Müraciət tapılmadı.", status=404)
    try:
        documents.issue_arayis(
            application=application, user=request.user, place=request.POST.get("place", ""), request=request
        )
    except documents.ArayisUnavailable as exc:
        return error(exc.message, status=exc.status)
    application.refresh_from_db()
    return ok({"application": detail_with_tools(application, request=request)})


__all__ = ["application_issue_arayis", "detail_with_tools"]
