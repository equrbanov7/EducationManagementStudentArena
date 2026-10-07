"""exam_center paketi — hesabatlar (oturum tarixçəsi + tələbə iştirakı)."""

import datetime

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.utils.translation import pgettext

from apps.exams.models import Exam, ExamRoom, ExamRoomSession
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
    # Süzgəc seçimləri: imtahan zalları + oturum tarixçəsi olan otaqlar (2026-10-01) —
    # 150+ adi sinif otağı siyahını doldurmasın, keçmiş oturumların zalı isə itməsin.
    rooms = (
        ExamRoom.objects.filter(organization=organization)
        .filter(Q(is_exam_hall=True) | Q(Exists(ExamRoomSession.objects.filter(room_id=OuterRef("pk")))))
        .order_by("name")
    )
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
            "kpis": _report_kpis(tab, queryset),
        },
    )


def _report_kpis(tab, queryset) -> dict:
    """Səhifə başındakı rəqəmlər — cari filtr üzrə TƏK aqreqat sorğu.

    Oturum tabında sətirlər onsuz da bilet sayğaclarını daşıyır
    (``session_list_annotations``), bilet tabında isə status üzrə sayılır.
    """
    from django.db.models import Count, Q, Sum

    if tab == "sessions":
        totals = queryset.aggregate(
            students=Sum("ticket_total"),
            completed=Sum("ticket_completed"),
            removed=Sum("ticket_removed"),
            absent=Sum("ticket_absent"),
        )
        return {
            "total": queryset.count(),
            "students": totals["students"] or 0,
            "completed": totals["completed"] or 0,
            "problem": (totals["removed"] or 0) + (totals["absent"] or 0),
        }
    totals = queryset.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status="completed")),
        removed=Count("id", filter=Q(status="removed")),
        absent=Count("id", filter=Q(status="absent")),
    )
    return {
        "total": totals["total"] or 0,
        "students": totals["total"] or 0,
        "completed": totals["completed"] or 0,
        "problem": (totals["removed"] or 0) + (totals["absent"] or 0),
    }


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

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = content_disposition_header(
        True, f"imtahan_hesabati_{_export_stamp(request.GET)}.xlsx"
    )
    workbook.save(response)
    return response


def _iso_date(value):
    """URL parametrini TARİX kimi yoxlayır; yararsız dəyər → ``None``."""
    try:
        return datetime.date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def _export_stamp(params) -> str:
    """Fayl adı damğası — yalnız rəqəm/alt xətt.

    Audit 2026-10-07: damğa xam ``date_from``-dan qurulurdu — dırnaq/``;``
    ``Content-Disposition`` fayl adını dəyişə bilirdi. İndi tarix əvvəlcə
    yoxlanır və ``strftime`` ilə yazılır; tək gün seçilməyibsə indiki vaxt.
    """
    date_from = _iso_date(params.get("date_from"))
    if date_from is not None and date_from == _iso_date(params.get("date_to")):
        return date_from.strftime("%Y%m%d")
    return timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M")


__all__ = ["exam_center_reports"]
