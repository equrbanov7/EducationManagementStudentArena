"""«Ana səhifə» — İDARƏETMƏ vidjetləri (kafedra müdiri, dekan, koordinator,
RİM, İmtahan Mərkəzi, rektorluq).

Qapı naxışı ``dashboard_widgets`` ilə eynidir: hər vidjet YALNIZ istifadəçinin
``allowed_sections``-ında olan bölmənin rəqəmini göstərir.  Bölməni aça
bilməyən rol sayğacı da GÖRMÜR — ana səhifə heç bir yeni məlumat səthi açmır,
yalnız mövcud bölmələrə yönləndirir.
"""

from __future__ import annotations

import datetime

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from .dashboard_widgets import ROW_LIMIT, section_link, stat, widget

_CTX = "accounts.dashboard"

#: Kollokvium pəncərəsinin vəziyyət etiketləri (registrar servisi ilə eyni açarlar).
_WINDOW_LABELS = {
    "not_configured": pgettext_lazy(_CTX, "qurulmayıb"),
    "inactive": pgettext_lazy(_CTX, "deaktiv"),
    "scheduled": pgettext_lazy(_CTX, "planlanıb"),
    "open": pgettext_lazy(_CTX, "açıq"),
    "closed": pgettext_lazy(_CTX, "bağlı"),
}


def _window_status(window, today) -> str:
    if window is None:
        return "not_configured"
    if not window.is_active:
        return "inactive"
    if today < window.opens_on:
        return "scheduled"
    if today > window.closes_on:
        return "closed"
    return "open"


# --------------------------------------------------------------------------- #
# Hamı üçün (aktiv üzvlüyü olan) — müraciətlər
# --------------------------------------------------------------------------- #


def applications(*, allowed_sections, pending_count: int) -> dict | None:
    """«Müraciətlər» — sayğac PROFİLİN KEŞLƏNMİŞ badge dəstindən gəlir (0 sorğu)."""
    if "applications" not in allowed_sections:
        return None
    count = int(pending_count or 0)
    return widget(
        "applications",
        pgettext(_CTX, "Müraciətlər"),
        "fa-comment-dots",
        tone="warning" if count else "",
        stats=[stat(pgettext(_CTX, "Gözləyən"), count, pgettext(_CTX, "müraciət"))],
        link=section_link("applications", pgettext(_CTX, "Müraciətlərə keç")),
        empty=pgettext(_CTX, "Hərəkət gözləyən müraciət yoxdur."),
    )


# --------------------------------------------------------------------------- #
# Kafedra müdiri / dekan / RİM — sillabus və yük
# --------------------------------------------------------------------------- #


def syllabus_review(*, request, organization, allowed_sections) -> dict | None:
    """«Sillabus təsdiqi» — növbədə gözləyən versiyaların sayı."""
    if "syllabus-review" not in allowed_sections:
        return None
    from apps.syllabus.public import has_review_scope, resolve_actor, review_queue

    actor = resolve_actor(request.user, organization, request=request)
    if not has_review_scope(actor=actor):
        return widget(
            "syllabus-review",
            pgettext(_CTX, "Sillabus təsdiqi"),
            "fa-clipboard-check",
            link=section_link("syllabus-review", pgettext(_CTX, "Növbəyə keç")),
            empty=pgettext(_CTX, "Struktur əhatəniz təyin edilməyib — növbə boşdur."),
        )
    queue = list(review_queue(organization=organization, actor=actor)[: ROW_LIMIT + 1])
    # `Syllabus.__str__` UUID cütü qaytarır — sətirdə FƏNNİN ADI göstərilir.
    # `review_queue` `syllabus__subject`-i onsuz da `select_related` edir, yəni
    # bu zəncir ƏLAVƏ sorğu yaratmır.
    rows = [
        {
            "title": str(getattr(getattr(row.syllabus, "subject", None), "name", "") or "—"),
            "meta": str(getattr(row, "get_status_display", lambda: "")() or ""),
        }
        for row in queue[:ROW_LIMIT]
    ]
    return widget(
        "syllabus-review",
        pgettext(_CTX, "Sillabus təsdiqi"),
        "fa-clipboard-check",
        tone="warning" if rows else "",
        stats=[stat(pgettext(_CTX, "Növbədə"), len(queue), pgettext(_CTX, "sillabus"))],
        rows=rows,
        link=section_link("syllabus-review", pgettext(_CTX, "Növbəyə keç")),
        empty=pgettext(_CTX, "Təsdiq gözləyən sillabus yoxdur."),
    )


def workload_distribution(*, request, organization, allowed_sections) -> dict | None:
    """«Yük bölgüsü» — kafedra sayı və cari tapşırığın statusu."""
    if "workload-distribution" not in allowed_sections:
        return None
    from apps.workload.public import build_distribution_context

    payload = build_distribution_context(request, organization=organization)
    if not payload.get("has_access"):
        return None
    task = payload.get("task") or {}
    chairs = payload.get("chairs") or []
    return widget(
        "workload-distribution",
        pgettext(_CTX, "Yük bölgüsü"),
        "fa-diagram-project",
        tone="success" if task.get("status") in ("distributed", "amended") else "warning",
        stats=[
            stat(pgettext(_CTX, "Kafedra"), len(chairs), pgettext(_CTX, "əhatədə")),
            stat(
                pgettext(_CTX, "Status"),
                task.get("status_label") or pgettext(_CTX, "tapşırıq yoxdur"),
                payload.get("academic_year") or "",
            ),
        ],
        rows=[{"title": row["name"], "meta": ""} for row in chairs[:ROW_LIMIT]],
        link=section_link("workload-distribution", pgettext(_CTX, "Bölgüyə keç")),
        empty=pgettext(_CTX, "Əhatənizdə kafedra tapılmadı."),
    )


# --------------------------------------------------------------------------- #
# Koordinator / cədvəl
# --------------------------------------------------------------------------- #


def schedule_scope(*, request, organization, allowed_sections) -> dict | None:
    """«Cədvəl idarəetməsi» — səlahiyyət sahəsindəki qrupların sayı."""
    if "schedule-manage" not in allowed_sections:
        return None
    from apps.registrar import schedule_manage

    groups = list(schedule_manage.scoped_groups(request.user, organization).values_list("name", flat=True)[:50])
    return widget(
        "schedule-scope",
        pgettext(_CTX, "Cədvəl idarəetməsi"),
        "fa-table-list",
        stats=[stat(pgettext(_CTX, "Qrup"), len(groups), pgettext(_CTX, "səlahiyyət sahənizdə"))],
        rows=[{"title": name, "meta": ""} for name in groups[:ROW_LIMIT]],
        link=section_link("schedule-manage", pgettext(_CTX, "Cədvələ keç")),
        empty=pgettext(_CTX, "Səlahiyyət sahənizdə qrup yoxdur."),
    )


# --------------------------------------------------------------------------- #
# RİM (ikt_rehber)
# --------------------------------------------------------------------------- #


def corrections(*, organization, capabilities) -> dict | None:
    """«Jurnal düzəlişləri» — bu gün / bu həftə edilmiş auditli düzəlişlər."""
    if not capabilities.get("can_watch_legacy_grades"):
        return None
    from apps.registrar.models import JournalCorrection

    today = timezone.localdate()
    week_start = today - datetime.timedelta(days=today.weekday())
    totals = JournalCorrection.objects.filter(organization=organization).aggregate(
        today_count=Count("id", filter=Q(created_at__date=today)),
        week_count=Count("id", filter=Q(created_at__date__gte=week_start)),
    )
    return widget(
        "corrections",
        pgettext(_CTX, "Jurnal düzəlişləri"),
        "fa-pen-to-square",
        stats=[
            stat(pgettext(_CTX, "Bu gün"), int(totals.get("today_count") or 0), pgettext(_CTX, "düzəliş")),
            stat(pgettext(_CTX, "Bu həftə"), int(totals.get("week_count") or 0), pgettext(_CTX, "düzəliş")),
        ],
        link=section_link("my-journal", pgettext(_CTX, "Jurnala keç")),
        empty=pgettext(_CTX, "Bu həftə düzəliş edilməyib."),
    )


def journal_close(*, organization, allowed_sections) -> dict | None:
    """«Jurnal bağlama» — aktiv bağlanma bildirişləri."""
    if "journal-close" not in allowed_sections:
        return None
    from apps.registrar.models import JournalCloseNotice

    notices = list(
        JournalCloseNotice.objects.filter(organization=organization, is_active=True).order_by("closes_on")[:ROW_LIMIT]
    )
    return widget(
        "journal-close",
        pgettext(_CTX, "Jurnal bağlama"),
        "fa-lock",
        stats=[stat(pgettext(_CTX, "Aktiv"), len(notices), pgettext(_CTX, "bildiriş"))],
        rows=[{"title": str(row.closes_on), "meta": row.message or ""} for row in notices],
        link=section_link("journal-close", pgettext(_CTX, "Bağlamaya keç")),
        empty=pgettext(_CTX, "Aktiv jurnal bağlama bildirişi yoxdur."),
    )


def student_intake(*, allowed_sections) -> dict | None:
    """«Tələbə idxalı» — yalnız keçid kartı (sorğu YOXDUR)."""
    if "student-intake" not in allowed_sections:
        return None
    return widget(
        "student-intake",
        pgettext(_CTX, "Tələbə idxalı"),
        "fa-user-plus",
        link=section_link("student-intake", pgettext(_CTX, "İdxala keç")),
        empty=pgettext(_CTX, "CSV ilə toplu tələbə hesabı yaradın."),
    )


# --------------------------------------------------------------------------- #
# Dizayn dalğası (22 ekran) — keçid kartları (sorğu YOXDUR)
# --------------------------------------------------------------------------- #

#: (bölmə, başlıq, ikon, boş-hal/izah mətni, keçid etiketi) — sıra = prioritet.
#: Hər kart YALNIZ bölmə ``allowed_sections``-da olanda çıxır; rəqəm/sorğu
#: yoxdur, yəni ana səhifə heç bir yeni məlumat səthi açmır (QA dalğa-2, P2-1).
_DESIGN_LINK_CARDS: tuple[tuple[str, object, str, object, object], ...] = (
    (
        "workload-center",
        pgettext_lazy(_CTX, "Dərs yükü mərkəzi"),
        "fa-layer-group",
        pgettext_lazy(_CTX, "Tədris planından dərs yükü tapşırığı yaradın, dilimlərə bölün, vizaları izləyin."),
        pgettext_lazy(_CTX, "Mərkəzə keç"),
    ),
    (
        "workload-visa",
        pgettext_lazy(_CTX, "Yük vizası"),
        "fa-stamp",
        pgettext_lazy(_CTX, "Fakültə diliminə koordinator vizası verin və ya geri qaytarın."),
        pgettext_lazy(_CTX, "Vizaya keç"),
    ),
    (
        "workload-approval",
        pgettext_lazy(_CTX, "Yük təsdiqi"),
        "fa-check-double",
        pgettext_lazy(_CTX, "Dekanlıq təsdiqi gözləyən fakültə dilimləri."),
        pgettext_lazy(_CTX, "Təsdiqə keç"),
    ),
    (
        "workload-overview",
        pgettext_lazy(_CTX, "Yük — ümumi baxış"),
        "fa-chart-column",
        pgettext_lazy(_CTX, "Universitet üzrə dərs yükü zəncirinin gedişi."),
        pgettext_lazy(_CTX, "Baxışa keç"),
    ),
    (
        "question-chair-review",
        pgettext_lazy(_CTX, "Sual təsdiqi"),
        "fa-clipboard-check",
        pgettext_lazy(_CTX, "İmtahan Mərkəzinə getməzdən əvvəl kafedra təsdiqi gözləyən sual göndərişləri."),
        pgettext_lazy(_CTX, "Təsdiqə keç"),
    ),
    (
        "curriculum-editor",
        pgettext_lazy(_CTX, "Tədris planı"),
        "fa-table-list",
        pgettext_lazy(_CTX, "İxtisas üzrə tədris planı sətirləri və təsdiq zənciri."),
        pgettext_lazy(_CTX, "Plana keç"),
    ),
    (
        "semester-opening",
        pgettext_lazy(_CTX, "Semestr açılışı"),
        "fa-door-open",
        pgettext_lazy(_CTX, "Təsdiqlənmiş plandan açılışları yaradın və semestri kilidləyin."),
        pgettext_lazy(_CTX, "Açılışa keç"),
    ),
    (
        "groups-registry",
        pgettext_lazy(_CTX, "Qruplar reyestri"),
        "fa-people-group",
        pgettext_lazy(_CTX, "Kurs/ixtisas üzrə qruplar və dil sektorları."),
        pgettext_lazy(_CTX, "Reyestrə keç"),
    ),
    (
        "student-admission",
        pgettext_lazy(_CTX, "Tələbə qəbulu"),
        "fa-file-import",
        pgettext_lazy(_CTX, "ATİS qəbul siyahısından tələbə hesabı və akademik qeyd yaradın."),
        pgettext_lazy(_CTX, "Qəbula keç"),
    ),
    (
        "student-registry",
        pgettext_lazy(_CTX, "Tələbə reyestri"),
        "fa-address-book",
        pgettext_lazy(_CTX, "Köçürmə, akademik məzuniyyət, xaric və bərpa hərəkətləri."),
        pgettext_lazy(_CTX, "Reyestrə keç"),
    ),
    (
        "lessons-log",
        pgettext_lazy(_CTX, "Keçilmiş dərslər"),
        "fa-list-check",
        pgettext_lazy(_CTX, "Plan saatı ilə faktiki keçilmiş dərslərin müqayisəsi."),
        pgettext_lazy(_CTX, "Jurnala keç"),
    ),
    (
        "org-structure-tree",
        pgettext_lazy(_CTX, "Universitet strukturu"),
        "fa-sitemap",
        pgettext_lazy(_CTX, "Fakültə → kafedra → ixtisas ağacı və rəhbər təyinatları."),
        pgettext_lazy(_CTX, "Struktura keç"),
    ),
)


def design_link_cards(*, allowed_sections) -> list[dict]:
    """22-ekran dalğasının bölmələrinə keçid kartları — rol qapısı ``allowed_sections``."""
    cards = []
    for section, title, icon, hint, label in _DESIGN_LINK_CARDS:
        if section not in allowed_sections:
            continue
        cards.append(
            widget(
                section,
                str(title),
                icon,
                link=section_link(section, str(label)),
                empty=str(hint),
            )
        )
    return cards


# --------------------------------------------------------------------------- #
# İmtahan Mərkəzi
# --------------------------------------------------------------------------- #


def kollokvium_windows(*, organization, period, allowed_sections) -> dict | None:
    """«Kollokvium pəncərələri» — K1/K2/K3-ün cari vəziyyəti."""
    if "kollokvium-windows" not in allowed_sections or period is None:
        return None
    from apps.registrar.models import KOLLOKVIUM_WINDOW_COUNT, KollokviumWindow

    today = timezone.localdate()
    windows = {row.k_index: row for row in KollokviumWindow.objects.filter(organization=organization, period=period)}
    rows = []
    open_count = 0
    for index in range(KOLLOKVIUM_WINDOW_COUNT):
        status = _window_status(windows.get(index), today)
        if status == "open":
            open_count += 1
        rows.append({"title": "K%s" % (index + 1), "meta": _WINDOW_LABELS[status]})
    return widget(
        "kollokvium-windows",
        pgettext(_CTX, "Kollokvium pəncərələri"),
        "fa-door-open",
        tone="success" if open_count else "",
        stats=[stat(pgettext(_CTX, "Açıq"), open_count, pgettext(_CTX, "pəncərə"))],
        rows=rows,
        link=section_link("kollokvium-windows", pgettext(_CTX, "Pəncərələrə keç")),
        empty=pgettext(_CTX, "Cari dövr üçün pəncərə qurulmayıb."),
    )


def upcoming_exams(*, organization, allowed_sections) -> dict | None:
    """«Yaxın imtahanlar» — bu andan sonra başlayacaq imtahanların sayı."""
    if "exam-center-stats" not in allowed_sections:
        return None
    from apps.exams.models import Exam

    now = timezone.now()
    exams = list(
        Exam.objects.filter(organization=organization, is_deleted=False, start_datetime__gte=now)
        .order_by("start_datetime")
        .values_list("title", "start_datetime")[: ROW_LIMIT + 1]
    )
    return widget(
        "upcoming-exams",
        pgettext(_CTX, "Yaxın imtahanlar"),
        "fa-file-pen",
        stats=[stat(pgettext(_CTX, "Planlanıb"), len(exams), pgettext(_CTX, "imtahan"))],
        rows=[
            {"title": title or "—", "meta": timezone.localtime(starts).strftime("%d.%m.%Y %H:%M") if starts else ""}
            for title, starts in exams[:ROW_LIMIT]
        ],
        link=section_link("exam-center-stats", pgettext(_CTX, "Statistikaya keç")),
        empty=pgettext(_CTX, "Planlanmış imtahan yoxdur."),
    )


def appeals(*, capabilities, pending_count: int) -> dict | None:
    """«Apellyasiyalar» — qərar gözləyənlərin sayı.

    Sayğac profil context-ində ARTIQ hesablanıb (``_stage1``) — burada təkrar
    sorğu getmir.
    """
    if not capabilities.get("can_manage_appeals"):
        return None
    count = int(pending_count or 0)
    return widget(
        "appeals",
        pgettext(_CTX, "Apellyasiyalar"),
        "fa-scale-balanced",
        tone="warning" if count else "",
        stats=[stat(pgettext(_CTX, "Gözləyən"), count, pgettext(_CTX, "apellyasiya"))],
        link=section_link("manage-appeals", pgettext(_CTX, "Apellyasiyalara keç")),
        empty=pgettext(_CTX, "Qərar gözləyən apellyasiya yoxdur."),
    )


# --------------------------------------------------------------------------- #
# Rektor / prorektor — org KPI-ları
# --------------------------------------------------------------------------- #


def org_kpis(*, request, organization, allowed_sections) -> dict | None:
    """«Universitet göstəriciləri» — YALNIZ org-səviyyə əhatəsi olan aktora.

    Fakültə/kafedra əhatəli rol (dekan, kafedra müdiri) bu vidjeti GÖRMÜR:
    kataloq bölməsi onun rəqəmlərini alt-ağaca görə süzür, ana səhifədə isə
    süzgəcsiz org rəqəmi göstərmək sızma olardı.
    """
    if "people-students" not in allowed_sections and "people-teachers" not in allowed_sections:
        return None
    from apps.accounts.services.people.permissions import PERM_VIEW_STUDENTS, PERM_VIEW_TEACHERS
    from apps.organizations.public import get_permission_scope

    privileged = bool(getattr(request.user, "is_superuser", False)) or getattr(
        organization, "owner_id", None
    ) == getattr(request.user, "pk", None)
    students_wide = privileged or get_permission_scope(request.user, organization, PERM_VIEW_STUDENTS).is_org_wide
    teachers_wide = privileged or get_permission_scope(request.user, organization, PERM_VIEW_TEACHERS).is_org_wide
    if not (students_wide or teachers_wide):
        return None

    stats = []
    if students_wide and "people-students" in allowed_sections:
        from apps.registrar.models import StudentAcademicRecord

        stats.append(
            stat(
                pgettext(_CTX, "Tələbə"),
                StudentAcademicRecord.objects.filter(organization=organization, is_active=True).count(),
                pgettext(_CTX, "aktiv"),
            )
        )
    if teachers_wide and "people-teachers" in allowed_sections:
        from apps.organizations.models import Membership

        stats.append(
            stat(
                pgettext(_CTX, "Müəllim"),
                Membership.objects.filter(
                    organization=organization,
                    is_active=True,
                    role__name__in=("teacher", "assistant_teacher"),
                )
                .values("user_id")
                .distinct()
                .count(),
                pgettext(_CTX, "aktiv"),
            )
        )
    if not stats:
        return None
    return widget(
        "org-kpis",
        pgettext(_CTX, "Universitet göstəriciləri"),
        "fa-chart-pie",
        tone="primary",
        stats=stats,
        link=section_link(
            "people-students" if "people-students" in allowed_sections else "people-teachers",
            pgettext(_CTX, "Kataloqa keç"),
        ),
    )


__all__ = [
    "appeals",
    "applications",
    "corrections",
    "design_link_cards",
    "journal_close",
    "kollokvium_windows",
    "org_kpis",
    "schedule_scope",
    "student_intake",
    "syllabus_review",
    "upcoming_exams",
    "workload_distribution",
]
