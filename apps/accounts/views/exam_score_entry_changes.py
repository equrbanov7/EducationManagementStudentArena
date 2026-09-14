"""İmtahan Mərkəzi — «Dəyişən nəticələr» CSV ixracı (W2 `w2paper`, 2026-09-14).

Sahib: «apellyasiyadan və ya nədənsə sonra DƏYİŞƏN nəticələrin izlənməsi
lazımdır». Bölmədəki cədvəl (``?ese_view=changes``) ilə EYNİ filtr həlli
(``_sections.exam_score_changes.resolve_changes_filters``) və eyni əhatə
(``final_score.entry`` — org-wide / unit alt-ağacı, superadmin cross-org).
Yazıcı ``core.export_safety.safe_csv_writer`` — formula neytrallaşdırma.

Fail-closed: icazəsiz aktor 403; semestr tapılmasa 404.
"""

from __future__ import annotations

import io

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar.public import exam_score_entry as service
from apps.registrar.public import exam_score_sheets as sheets_service
from core.export_safety import safe_csv_writer

from ._helpers import _get_active_organization, _is_superadmin_user
from .exam_score_entry import _can_manage, _resolve_target_org
from .profile._sections.exam_score_changes import changes_queryset_for, resolve_changes_filters
from .profile._sections.exam_score_entry import _resolve_period, _scope_group_ids

_CTX = "accounts.exam_score_entry"


def _period_for(request, organization):
    """``ese_period`` (və ya ``ese_year``) → semestr; bölmə ilə eyni heuristika."""
    from apps.organizations.models import AcademicPeriod

    all_periods = list(AcademicPeriod.objects.filter(organization=organization).order_by("-start_date"))
    _years, _year, _periods, period = _resolve_period(request, all_periods, timezone.localdate())
    return period


@never_cache
@login_required
@require_GET
def exam_score_changes_export(request):
    """Dəyişən nəticələrin CSV-si — cədvəldəki filtrlərlə (ən çox ``EXPORT_LIMIT`` sətir)."""
    organization = _resolve_target_org(request)
    if organization is None or not _can_manage(request.user, organization or _get_active_organization(request)):
        return HttpResponseForbidden(
            pgettext(_CTX, "Bu bölmə yalnız imtahan balı daxil etmə səlahiyyəti olanlar üçündür.")
        )
    period = _period_for(request, organization)
    if period is None:
        return HttpResponse(status=404)
    is_superadmin = _is_superadmin_user(request.user)
    allowed_group_ids = None if is_superadmin else _scope_group_ids(request.user, organization, service)
    resolved = resolve_changes_filters(
        request,
        service=service,
        sheets_service=sheets_service,
        organization=organization,
        period=period,
        allowed_group_ids=allowed_group_ids,
    )
    queryset = changes_queryset_for(
        request, service=service, organization=organization, query=resolved["query"], is_superadmin=is_superadmin
    )
    changes = service.exam_score_changes
    buffer = io.StringIO()
    writer = safe_csv_writer(buffer)
    writer.writerow(changes.csv_header())
    writer.writerows(changes.csv_rows(queryset))
    payload = ("﻿" + buffer.getvalue()).encode("utf-8")
    response = HttpResponse(payload, content_type="text/csv; charset=utf-8")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = 'attachment; filename="deyisen_neticeler_%s.csv"' % stamp
    response["X-Content-Type-Options"] = "nosniff"
    return response


__all__ = ["exam_score_changes_export"]
