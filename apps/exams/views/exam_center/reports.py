"""exam_center paketi — hesabatlar (oturum tarixçəsi + tələbə iştirakı)."""

import csv

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.exams.models import ExamRoom
from apps.exams.services.final_center import filter_sessions, filter_tickets
from core.audit import log_action
from core.constants import AuditAction

from ._shared import center_org_or_403


@login_required
def exam_center_reports(request):
    """
    Hesabat səhifəsi: tab=sessions | tickets. Server-tərəfli filtr + pagination.
    ``export=csv`` cari filtrlə CSV qaytarır (yalnız əməliyyat sahələri —
    PIN/cavab məlumatı YOXDUR) və export audit-ə yazılır.
    """
    organization = center_org_or_403(request)
    tab = request.GET.get("tab") or "sessions"
    if tab not in ("sessions", "tickets"):
        tab = "sessions"

    if tab == "sessions":
        queryset = filter_sessions(organization, request.GET)
    else:
        queryset = filter_tickets(organization, request.GET)

    if request.GET.get("export") == "csv":
        return _export_csv(request, organization, tab, queryset)

    page_obj = Paginator(queryset, 25).get_page(request.GET.get("page"))
    rooms = ExamRoom.objects.filter(organization=organization).order_by("name")
    query_string = request.GET.copy()
    query_string.pop("page", None)

    return render(
        request,
        "exams/exam_center/reports.html",
        {
            "tab": tab,
            "page_obj": page_obj,
            "rooms": rooms,
            "organization": organization,
            "params": request.GET,
            "extra_query": query_string.urlencode(),
        },
    )


def _local_iso(value):
    """UTC saxlanan tarixi yerli zonaya (Asia/Baku) çevirib ISO qaytar — CSV
    UI ilə eyni saatı göstərsin (əvvəl xam UTC isoformat verilirdi, 4 saat geri)."""
    return timezone.localtime(value).isoformat() if value else ""


def _export_csv(request, organization, tab, queryset):
    log_action(
        AuditAction.EXPORT,
        user=request.user,
        organization=organization,
        reason=f"final_center_report_export[{tab}]",
        request=request,
        resource_type="final_center_report",
    )
    timestamp = timezone.now().strftime("%Y%m%d_%H%M")
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="final_{tab}_{timestamp}.csv"'
    writer = csv.writer(response)

    if tab == "sessions":
        writer.writerow(
            [
                "room",
                "state",
                "scheduled_start",
                "scheduled_end",
                "started_at",
                "ended_at",
                "invigilator",
                "tickets",
                "completed",
                "removed",
                "absent",
            ]
        )
        for s in queryset.iterator(chunk_size=500):
            writer.writerow(
                [
                    f"{s.room.name} ({s.room.code})",
                    s.state,
                    _local_iso(s.scheduled_start),
                    _local_iso(s.scheduled_end),
                    _local_iso(s.started_at),
                    _local_iso(s.ended_at),
                    (s.invigilator.get_full_name() or s.invigilator.username) if s.invigilator else "",
                    s.ticket_total,
                    s.ticket_completed,
                    s.ticket_removed,
                    s.ticket_absent,
                ]
            )
    else:
        writer.writerow(
            [
                "student",
                "username",
                "exam",
                "room",
                "status",
                "language",
                "seat",
                "entry_validated_at",
                "started_at",
                "completed_at",
                "removal_action",
                "removal_reason",
            ]
        )
        for t in queryset.iterator(chunk_size=500):
            writer.writerow(
                [
                    t.student.get_full_name() or t.student.username,
                    t.student.username,
                    t.exam.title,
                    t.session.room.name,
                    t.status,
                    t.language,
                    t.seat_number or "",
                    _local_iso(t.entry_validated_at),
                    _local_iso(t.started_at),
                    _local_iso(t.completed_at),
                    t.removal_action,
                    t.removal_reason,
                ]
            )
    return response


__all__ = ["exam_center_reports"]
