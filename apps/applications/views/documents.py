"""Müraciətə rəsmi sənədi «hazırla və əlavə et» — JSON endpoint-ləri.

* «Arayış sorğusu» → «Arayışı hazırla və əlavə et» (sahib 2026-10-19);
* «Transkript sorğusu» → «Transkripti hazırla və əlavə et» (sahib 2026-10-26).

Qaydalar ``services.documents``-dədir (emalçı + ``transcript.issue`` əhatəsi; view-as 403). Cavab adi əməl
cavabı ilə eynidir: yenilənmiş DETAL payload-u (yeni qeyd + əlavə olunmuş PDF).
"""

from __future__ import annotations

from django.views.decorators.http import require_POST

from ..services import documents
from ._base import error, json_endpoint, load_application, ok


def detail_with_tools(application, *, request) -> dict:
    """``detail_payload`` + «Sənədi hazırla» bloku (yalnız uyğun emalçıya; əks halda ``None``).

    ``document_tool`` — ümumi açar (UI bunu oxuyur); ``arayis_tool`` — köhnə açar, yalnız arayış növündə."""
    from ..payloads import detail_payload

    payload = detail_payload(application, user=request.user)
    tool = documents.document_tool(application, user=request.user, request=request)
    payload["document_tool"] = tool
    payload["arayis_tool"] = tool if tool and tool["kind"] == documents.ARAYIS_KIND_CODE else None
    return payload


def _issue(request, organization, application_id, kind_code):
    application = load_application(request, organization, application_id)
    if application is None:
        return error("Müraciət tapılmadı.", status=404)
    try:
        documents.issue_document(
            application=application,
            user=request.user,
            place=request.POST.get("place", ""),
            request=request,
            kind_code=kind_code,
        )
    except documents.DocumentUnavailable as exc:
        return error(exc.message, status=exc.status)
    application.refresh_from_db()
    return ok({"application": detail_with_tools(application, request=request)})


@require_POST
@json_endpoint
def application_issue_arayis(request, application_id, *, organization):
    return _issue(request, organization, application_id, documents.ARAYIS_KIND_CODE)


@require_POST
@json_endpoint
def application_issue_transcript(request, application_id, *, organization):
    return _issue(request, organization, application_id, documents.TRANSCRIPT_KIND_CODE)


__all__ = ["application_issue_arayis", "application_issue_transcript", "detail_with_tools"]
