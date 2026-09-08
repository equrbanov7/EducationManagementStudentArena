"""Ekran 21 «Keçilmiş dərslər» — CSV ixracı.

Səth OXU-ONLYdır və EYNİ əhatə qaydasından keçir (README §8/8): müəllim yalnız
öz dərslərini ixrac edir; ``teacher`` filtri YALNIZ ``journal.roster`` daşıyan
nəzarətçiyə açıqdır — adi müəllim başqasının müəllim id-si ilə sorğu atsa
**403** alır (səssiz «öz datası» fallback-i deyil: parametr qəsdən yazılıb).
"""

from __future__ import annotations

import csv

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from apps.registrar import lessons_log as service
from apps.registrar import schedule as schedule_service
from core.tenancy import get_request_organization, request_has_active_organization_context

_CTX = "registrar.lessons_log"

PREFIX = "ll_"

#: İxracın sətir tavanı — hesabat faylı, sonsuz axın deyil.
EXPORT_CAP = 5000


def _param(request, name: str, default: str = "") -> str:
    return (request.GET.get(PREFIX + name) or default).strip()[:80]


@login_required
@require_GET
def lessons_log_csv(request):
    """Seçilmiş dövrün dərs qeydlərini CSV kimi qaytarır."""
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return HttpResponseForbidden("no_active_organization", content_type="text/plain; charset=utf-8")

    supervisor = service.is_supervisor(request.user, organization)
    teacher_id = _param(request, "teacher")
    if teacher_id and not supervisor:
        return HttpResponseForbidden("teacher_filter_forbidden", content_type="text/plain; charset=utf-8")

    legacy_period = _param(request, "period")
    period_view = schedule_service.resolve_display_period(organization, requested=legacy_period)
    # Bölmə ilə EYNİ dövr/aralıq həlli və EYNİ süzgəc zənciri (tək mənbə:
    # `lessons_log.resolve_selection` + `apply_filters`) — ixrac panelə uyğun gəlsin.
    selection = service.resolve_selection(
        organization,
        current=period_view["period"],
        year=_param(request, "year"),
        season=_param(request, "season"),
        legacy_period=legacy_period,
        range_key=_param(request, "range", service.RANGE_SEMESTER),
        start_raw=_param(request, "from"),
        end_raw=_param(request, "to"),
    )
    window = selection["window"]

    lessons = service.scoped_lessons(request.user, organization, supervisor=supervisor)
    lessons = lessons.filter(date__gte=window["start"], date__lte=window["end"])
    if selection["apply_period_filter"]:
        lessons = lessons.filter(offering__period__in=selection["periods"])
    lessons = service.apply_filters(
        lessons,
        q=_param(request, "q"),
        offering=_param(request, "offering"),
        kind=_param(request, "kind"),
        group=_param(request, "group"),
        teacher=teacher_id,
        form=_param(request, "form"),
        supervisor=supervisor,
    )

    rows = service.build_rows(lessons, limit=EXPORT_CAP)
    if _param(request, "flagged") == "1":
        rows = [row for row in rows if row["note"] != service.NOTE_ON_TIME]

    filename = "kecilmis-dersler-%s.csv" % timezone.localdate().isoformat()
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    # BOM — Excel UTF-8 Azərbaycan hərflərini düzgün oxusun.
    response.write("﻿")
    writer = csv.writer(response)
    for line in service.csv_rows(rows):
        writer.writerow(line)
    response.write(
        "%s,%s,%s\r\n"
        % (
            pgettext(_CTX, "Dövr"),
            window["start"].isoformat(),
            window["end"].isoformat(),
        )
    )
    return response


__all__ = ["EXPORT_CAP", "lessons_log_csv"]
