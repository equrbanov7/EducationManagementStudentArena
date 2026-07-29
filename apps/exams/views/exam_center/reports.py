"""exam_center paketi — hesabatlar (oturum tarixçəsi + tələbə iştirakı)."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import Exam, ExamRoom
from apps.exams.services.final_center import (
    build_final_report_workbook,
    filter_sessions,
    filter_tickets,
)
from core.audit import log_action
from core.constants import AuditAction

from ._shared import center_org_or_403

# Bir eksportda emal olunan maksimum bilet sayı. Universitet miqyasında bir
# günün hesabatı bir neçə mindən çox olmur; hədd təsadüfi "bütün tarix"
# sorğusunun yaddaşı yeməsinin qarşısını alır (aşanda istifadəçi tarix daraldır).
EXPORT_ROW_CAP = 20000


@login_required
def exam_center_reports(request):
    """
    Hesabat səhifəsi: tab=sessions | tickets. Server-tərəfli filtr + pagination.
    ``export=xlsx`` cari filtrlə çoxvərəqli Excel hesabatı qaytarır (hər zal öz
    vərəqində + pozuntu jurnalı); PIN/cavab məlumatı YOXDUR və export audit-ə
    yazılır.
    """
    organization = center_org_or_403(request)
    tab = request.GET.get("tab") or "sessions"
    if tab not in ("sessions", "tickets"):
        tab = "sessions"

    if request.GET.get("export") == "xlsx":
        return _export_xlsx(request, organization)

    if tab == "sessions":
        queryset = filter_sessions(organization, request.GET)
    else:
        queryset = filter_tickets(organization, request.GET)

    page_obj = Paginator(queryset, 25).get_page(request.GET.get("page"))
    rooms = ExamRoom.objects.filter(organization=organization).order_by("name")
    exams = (
        Exam.objects.filter(organization=organization, final_tickets__isnull=False)
        .distinct()
        .order_by("title")
        .only("id", "title")
    )
    query_string = request.GET.copy()
    query_string.pop("page", None)
    # "Sıfırla" düyməsi yalnız faktiki filtr varsa göstərilir (tab/page filtr deyil).
    has_filters = any(
        (request.GET.get(key) or "").strip() for key in ("state", "room", "exam", "status", "date_from", "date_to", "q")
    )

    return render(
        request,
        "exams/exam_center/reports.html",
        {
            "tab": tab,
            "page_obj": page_obj,
            "rooms": rooms,
            "exams": exams,
            "organization": organization,
            "params": request.GET,
            "extra_query": query_string.urlencode(),
            "has_filters": has_filters,
        },
    )


def _filter_summary(params, organization):
    """Xülasə vərəqinə yazılan "bu fayl hansı filtrlə çıxarılıb" sətirləri."""
    rows = []
    date_from = (params.get("date_from") or "").strip()
    date_to = (params.get("date_to") or "").strip()
    if date_from or date_to:
        rows.append(
            (
                pgettext("exams.final_center.report", "Tarix aralığı"),
                f"{date_from or '…'} — {date_to or '…'}",
            )
        )
    else:
        rows.append(
            (
                pgettext("exams.final_center.report", "Tarix aralığı"),
                pgettext("exams.final_center.report", "Bütün tarixlər"),
            )
        )

    room_id = (params.get("room") or "").strip()
    if room_id.isdigit():
        room = ExamRoom.objects.filter(organization=organization, pk=int(room_id)).first()
        if room:
            rows.append((pgettext("exams.final_center.report", "Zal"), f"{room.name} ({room.code})"))

    exam_id = (params.get("exam") or "").strip()
    if exam_id.isdigit():
        exam = Exam.objects.filter(organization=organization, pk=int(exam_id)).first()
        if exam:
            rows.append((pgettext("exams.final_center.report", "İmtahan"), exam.title))

    status = (params.get("status") or "").strip()
    if status:
        rows.append((pgettext("exams.final_center.report", "Status"), status))

    query = (params.get("q") or "").strip()
    if query:
        rows.append((pgettext("exams.final_center.report", "Axtarış"), query))
    return rows


def _export_xlsx(request, organization):
    """Cari filtrə uyğun tam Excel hesabatı.

    Həmişə BİLET (tələbə) qatından qurulur — aktiv tab-dan asılı olmayaraq:
    hesabatın mənası "həmin gün kim, harada, hansı nəticə ilə imtahan verdi"
    sualıdır və oturum sətirləri bunu tək başına vermir.
    """
    tickets = filter_tickets(organization, request.GET)[:EXPORT_ROW_CAP]

    log_action(
        AuditAction.EXPORT,
        user=request.user,
        organization=organization,
        reason="final_center_report_export[xlsx]",
        request=request,
        resource_type="final_center_report",
    )

    meta_rows = [
        (
            pgettext("exams.final_center.report", "Hesabatı çıxaran"),
            (request.user.get_full_name() or "").strip() or request.user.username,
        ),
        *_filter_summary(request.GET, organization),
    ]
    workbook = build_final_report_workbook(organization, tickets, meta_rows=meta_rows)

    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    if date_from and date_from == date_to:
        stamp = date_from.replace("-", "")
    else:
        stamp = timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M")

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="imtahan_hesabati_{stamp}.xlsx"'
    workbook.save(response)
    return response


__all__ = ["exam_center_reports"]
