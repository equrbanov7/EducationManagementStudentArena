"""«Fərdi tədris planı» DOCX yükləməsi — bütöv qrup və ya tək tələbə.

URL: ``registrar:group_individual_plan`` (`qrup/<uuid>/ferdi-plan.docx`), tək
tələbə üçün ``?student=<record_id>``. QAPI «Qruplar» ekranı ilə EYNİDİR
(`unit.view` + struktur əhatəsi + görünən qrup) — proqram koordinatoru, dekanlıq,
tədris şöbəsi öz əhatəsindəki qrup üçün yükləyir; əhatədən kənar qrup 404.
Sənəd :mod:`apps.registrar.individual_plan` ilə rəsmi şablondan qurulur.
"""

from __future__ import annotations

from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.organizations.public import can_view_groups, group_scope, visible_group
from core.tenancy import get_request_organization

from . import individual_plan


@never_cache
@login_required
@require_GET
def group_individual_plan(request, group_id):
    organization = get_request_organization(request)
    if organization is None or not can_view_groups(request):
        raise Http404
    scope = group_scope(request, organization)
    if not scope.has_structure_access:
        raise Http404
    group = visible_group(organization, scope, str(group_id), include_archived=True)
    if group is None:
        raise Http404

    record_id = (request.GET.get("student") or "").strip() or None
    filename, payload, count = individual_plan.build_group_document(organization, group, record_id=record_id)
    if record_id and count == 0:
        raise Http404

    response = HttpResponse(payload, content_type=individual_plan.DOCX_CONTENT_TYPE)
    ascii_name = filename.encode("ascii", "ignore").decode("ascii") or "ferdi-tedris-plani.docx"
    response["Content-Disposition"] = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    response["X-Students"] = str(count)
    return response


__all__ = ["group_individual_plan"]
