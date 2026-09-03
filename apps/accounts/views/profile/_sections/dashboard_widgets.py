"""«Ana səhifə» (dashboard) vidjet qurucuları — rol-agnostik, İCAZƏ-qapılı.

Hər funksiya BİR vidjet qaytarır (və ya ``None`` — vidjet ümumiyyətlə
göstərilmir).  Qapı həmişə ``allowed_sections`` / ``capabilities`` üzərindədir:
istifadəçinin AÇA BİLMƏDİYİ bölmənin rəqəmi kabinet ana səhifəsində də
GÖRÜNMÜR (sayğac sızması yoxdur).

BÜDCƏ: hər vidjet bir neçə UCUZ sorğu ilə məhdudlaşır (count/aggregate,
``select_related``, ``[:5]`` dilim).  Ağır context qurucuları (jurnal xülasəsi,
analitika, sillabus əhatə hesabatı) QƏSDƏN çağırılmır — ana səhifə bölmələrin
ƏVƏZİ deyil, onlara YÖNLƏNDİRİCİDİR.  Ümumi hədd testdə
``CaptureQueriesContext`` ilə kilidlənib (``test_dashboard_section.py``).
"""

from __future__ import annotations

from django.db.models import Count, Sum
from django.urls import reverse
from django.utils.translation import pgettext

_CTX = "accounts.dashboard"

#: Vidjet siyahılarının maksimum sətir sayı (dizayn: ana səhifə = xülasə).
ROW_LIMIT = 5


# --------------------------------------------------------------------------- #
# Kiçik köməkçilər
# --------------------------------------------------------------------------- #


def section_link(section: str, label) -> dict:
    """SPA-nın tutduğu `?section=` keçidi (sidebar linkləri ilə eyni müqavilə).

    ``title`` sonradan ``dashboard.build_dashboard_section`` tərəfindən hədəf
    bölmənin RƏSMİ adı ilə doldurulur (SPA panel başlığını `data-title`-dan
    oxuyur; «Cədvələ keç» kimi əməl mətni başlıq olmamalıdır).
    """
    return {
        "section": section,
        "label": label,
        "title": "",
        "url": "%s?section=%s" % (reverse("accounts:profile"), section),
    }


def widget(key: str, title, icon: str, *, tone: str = "", stats=None, rows=None, link=None, empty="") -> dict:
    """Vahid vidjet müqaviləsi — şablon YALNIZ bu açarları oxuyur.

    ``is_empty`` BURADA hesablanır: sətir yoxdursa VƏ bütün rəqəmlər sıfırdırsa
    vidjet «boşdur» sayılır və şablon dost boş-hal mətnini göstərir.  Qərarı
    şablonda saxlasaydıq hər vidjet üçün ayrı şərt yazmaq lazım gələrdi.
    """
    stats = list(stats or ())
    rows = list(rows or ())
    return {
        "key": key,
        "title": title,
        "icon": icon,
        "tone": tone,
        "stats": stats,
        "rows": rows,
        "link": link,
        "empty": empty,
        "is_empty": not rows and all(str(item.get("value", "")).strip() in ("", "0", "0%") for item in stats),
    }


def stat(label, value, note="") -> dict:
    return {"label": label, "value": value, "note": note}


def _time_label(slot) -> str:
    start = getattr(slot, "start_time", None)
    end = getattr(slot, "end_time", None)
    if start is None:
        return ""
    return "%s–%s" % (start.strftime("%H:%M"), end.strftime("%H:%M") if end else "")


def todays_slots(slots, week_context) -> list:
    """Bu günün slotları — həftə günü + üst/alt həftə paritetinə görə süzülmüş."""
    from apps.registrar.models import WeekType

    if not slots or not week_context:
        return []
    weekday = week_context["today"].isoweekday()
    parity = week_context.get("parity")
    picked = []
    for slot in slots:
        if slot.weekday != weekday:
            continue
        # `all` hər həftə keçir; `odd`/`even` yalnız öz paritetində.
        if slot.week_type in (WeekType.ODD, WeekType.EVEN) and slot.week_type != parity:
            continue
        picked.append(slot)
    return sorted(picked, key=lambda item: item.start_time)


def upcoming_slots(slots, week_context):
    """Bu gündən SONRAKI ilk dərsli gün → ``(gün adı, slotlar)``.

    Cari həftənin qalan günlərinə baxır (pariteti nəzərə alır); tapılmasa boş
    qaytarır.  ƏLAVƏ SORĞU ETMİR — çağıran onsuz da yüklədiyi slot siyahısını
    ötürür (ana səhifə sorğu büdcəsi).
    """
    from apps.registrar.models import WeekType

    if not slots or not week_context:
        return "", []
    weekday = week_context["today"].isoweekday()
    parity = week_context.get("parity")
    ahead = {}
    for slot in slots:
        if slot.weekday <= weekday:
            continue
        if slot.week_type in (WeekType.ODD, WeekType.EVEN) and slot.week_type != parity:
            continue
        ahead.setdefault(slot.weekday, []).append(slot)
    if not ahead:
        return "", []
    day = min(ahead)
    from apps.registrar import schedule as schedule_service

    labels = {index: label for index, label in schedule_service.WEEKDAYS}
    return str(labels.get(day, "")), sorted(ahead[day], key=lambda item: item.start_time)


def _slot_rows(slots) -> list:
    rows = []
    for slot in slots[:ROW_LIMIT]:
        offering = slot.offering
        subject = getattr(offering, "subject", None)
        meta = [_time_label(slot)]
        if slot.room:
            meta.append(slot.room)
        group = getattr(offering, "group", None)
        if group is not None:
            meta.append(group.name)
        rows.append({"title": getattr(subject, "name", "") or "—", "meta": " · ".join(part for part in meta if part)})
    return rows


# --------------------------------------------------------------------------- #
# Tələbə vidjetləri
# --------------------------------------------------------------------------- #


def student_today(*, organization, record, period, allowed_sections) -> dict | None:
    """«Bu gün dərslər» — SAR qrupunun cədvəli, bu günə + həftə paritetinə görə.

    Akademik qeydi (SAR) və ya cari semestri OLMAYAN tələbədə vidjet YOX OLMUR
    — boş vəziyyət göstərir.  Səbəb: köçürülmüş bazada qeydsiz hesablar var və
    «heç nə görünmür» onlar üçün nasazlıqdan fərqlənmir.
    """
    if "my-schedule" not in allowed_sections:
        return None
    from apps.registrar import schedule as schedule_service

    group = getattr(record, "group", None) if record is not None else None
    if period is None or group is None:
        return widget(
            "student-today",
            pgettext(_CTX, "Bu gün dərslər"),
            "fa-calendar-day",
            link=section_link("my-schedule", pgettext(_CTX, "Cədvələ keç")),
            empty=pgettext(_CTX, "Cari semestr üçün qrup cədvəliniz tapılmadı."),
        )
    slots = schedule_service.get_group_schedule(organization=organization, group=group, period=period)
    week_context = schedule_service.build_week_context(period)
    today = todays_slots(slots, week_context)
    # Ekran 10: kart «bu gün / növbəti dərslər»dir.  Bu gün dərs yoxdursa
    # bomboş qalmır — həftənin NÖVBƏTİ dərsli günü göstərilir (eyni slot
    # siyahısından, ƏLAVƏ SORĞU YOXDUR).
    upcoming_day, upcoming = ("", [])
    if not today:
        upcoming_day, upcoming = upcoming_slots(slots, week_context)
    shown = today or upcoming
    next_label = _time_label(shown[0]) if shown else pgettext(_CTX, "yoxdur")
    return widget(
        "student-today",
        pgettext(_CTX, "Bu gün / növbəti dərslər"),
        "fa-calendar-day",
        tone="primary",
        stats=[
            stat(pgettext(_CTX, "Bu gün"), len(today), pgettext(_CTX, "dərs")),
            stat(
                pgettext(_CTX, "Növbəti"),
                next_label,
                upcoming_day if not today else "",
            ),
        ],
        rows=_slot_rows(shown),
        link=section_link("my-schedule", pgettext(_CTX, "Cədvələ keç")),
        empty=pgettext(_CTX, "Bu gün üçün cədvəldə dərs yoxdur."),
    )


def student_grades(*, organization, user, allowed_sections) -> dict | None:
    """«Son qiymətlər» — sonuncu 5 komponent balı (kollokvium/seminar/SDF…)."""
    if "my-journal" not in allowed_sections:
        return None
    from apps.registrar.models import ComponentScore

    scores = list(
        ComponentScore.objects.filter(organization=organization, enrollment__student=user)
        .select_related("component", "enrollment__offering__subject")
        .order_by("-created_at")[:ROW_LIMIT]
    )
    rows = [
        {
            "title": getattr(row.enrollment.offering.subject, "name", "") or "—",
            "meta": "%s · %s" % (row.component.name, row.score),
        }
        for row in scores
    ]
    return widget(
        "student-grades",
        pgettext(_CTX, "Son qiymətlər"),
        "fa-star",
        stats=[stat(pgettext(_CTX, "Yazılan bal"), len(rows), pgettext(_CTX, "sonuncu"))],
        rows=rows,
        link=section_link("my-journal", pgettext(_CTX, "Jurnala keç")),
        empty=pgettext(_CTX, "Hələ heç bir bal yazılmayıb."),
    )


def student_attendance(*, organization, user, record, period, allowed_sections) -> dict | None:
    """«Davamiyyət» — cari dövrün qayıb saatları və proqramın buraxılış limiti."""
    if "my-journal" not in allowed_sections:
        return None
    if record is None or period is None:
        return widget(
            "student-attendance",
            pgettext(_CTX, "Davamiyyət"),
            "fa-user-check",
            link=section_link("my-journal", pgettext(_CTX, "Jurnala keç")),
            empty=pgettext(_CTX, "Akademik qeydiniz tapılmadı — RİM-ə müraciət edin."),
        )
    from apps.registrar.models import Enrollment

    summary = Enrollment.objects.filter(organization=organization, student=user, offering__period=period).aggregate(
        absence=Sum("absence_hours"), subjects=Count("id")
    )
    absence = int(summary.get("absence") or 0)
    limit_percent = int(getattr(getattr(record, "program", None), "absence_limit_percent", 0) or 0)
    return widget(
        "student-attendance",
        pgettext(_CTX, "Davamiyyət"),
        "fa-user-check",
        tone="warning" if absence else "",
        stats=[
            stat(pgettext(_CTX, "Qayıb"), absence, pgettext(_CTX, "saat")),
            stat(pgettext(_CTX, "Fənn"), int(summary.get("subjects") or 0), pgettext(_CTX, "cari dövr")),
            stat(pgettext(_CTX, "Limit"), "%s%%" % limit_percent, pgettext(_CTX, "proqram üzrə")),
        ],
        link=section_link("my-journal", pgettext(_CTX, "Jurnala keç")),
        empty=pgettext(_CTX, "Cari dövrdə qeydiyyat yoxdur."),
    )


# --------------------------------------------------------------------------- #
# Müəllim vidjetləri
# --------------------------------------------------------------------------- #


def teacher_today(*, organization, user, period, allowed_sections) -> dict | None:
    if "my-schedule" not in allowed_sections or period is None:
        return None
    from apps.registrar import schedule as schedule_service

    slots = schedule_service.get_teacher_schedule(organization=organization, teacher=user, period=period)
    week_context = schedule_service.build_week_context(period)
    today = todays_slots(slots, week_context)
    return widget(
        "teacher-today",
        pgettext(_CTX, "Bu gün dərslərim"),
        "fa-chalkboard-teacher",
        tone="primary",
        stats=[
            stat(pgettext(_CTX, "Bu gün"), len(today), pgettext(_CTX, "dərs")),
            stat(pgettext(_CTX, "Həftədə"), len(slots), pgettext(_CTX, "slot")),
        ],
        rows=_slot_rows(today),
        link=section_link("my-schedule", pgettext(_CTX, "Cədvələ keç")),
        empty=pgettext(_CTX, "Bu gün üçün cədvəldə dərsiniz yoxdur."),
    )


def teacher_offerings(*, organization, user, period, allowed_sections) -> dict | None:
    """«Fənlərim» — cari dövrdə apardığı açılışların sayı + jurnal keçidi."""
    if "my-journal" not in allowed_sections or period is None:
        return None
    from apps.registrar.models import CourseOffering

    offerings = list(
        CourseOffering.objects.filter(
            organization=organization, instructor=user, period=period, is_active=True
        ).select_related("subject", "group")[: ROW_LIMIT + 1]
    )
    rows = [
        {
            "title": getattr(row.subject, "name", "") or "—",
            "meta": getattr(getattr(row, "group", None), "name", "") or "",
        }
        for row in offerings[:ROW_LIMIT]
    ]
    return widget(
        "teacher-offerings",
        pgettext(_CTX, "Fənlərim"),
        "fa-book-open",
        stats=[stat(pgettext(_CTX, "Cari dövr"), len(offerings), pgettext(_CTX, "açılış"))],
        rows=rows,
        link=section_link("my-journal", pgettext(_CTX, "Jurnala keç")),
        empty=pgettext(_CTX, "Cari dövrdə sizə fənn təyin olunmayıb."),
    )


def teacher_syllabus(*, request, organization, allowed_sections) -> dict | None:
    """«Sillabus işlərim» — qaralama + düzəliş tələb olunan versiyaların sayı."""
    if "syllabus-list" not in allowed_sections:
        return None
    from apps.syllabus.public import SyllabusStatus, list_syllabi, resolve_actor

    actor = resolve_actor(request.user, organization, request=request)
    pending = list_syllabi(
        organization=organization,
        actor=actor,
        statuses=[SyllabusStatus.DRAFT, SyllabusStatus.REVISION],
    )
    rows = [
        {
            "title": getattr(row.subject, "name", "") or "—",
            "meta": str(getattr(getattr(row, "current_version", None), "get_status_display", lambda: "")() or ""),
        }
        for row in pending[:ROW_LIMIT]
    ]
    return widget(
        "teacher-syllabus",
        pgettext(_CTX, "Sillabus işlərim"),
        "fa-file-signature",
        tone="warning" if rows else "",
        stats=[stat(pgettext(_CTX, "Gözləyən"), len(rows), pgettext(_CTX, "sillabus"))],
        rows=rows,
        link=section_link("syllabus-list", pgettext(_CTX, "Sillabuslara keç")),
        empty=pgettext(_CTX, "Qaralama və ya düzəliş gözləyən sillabus yoxdur."),
    )


def my_workload(*, organization, user, allowed_sections, is_teacher: bool = False) -> dict | None:
    """«Dərs yüküm» — təsdiqlənmiş illik saat + norma doluluğu."""
    if "my-workload" not in allowed_sections:
        return None
    from apps.workload.public import teacher_workload_summary, teacher_years

    years = teacher_years(organization=organization, teacher=user)
    year = years[0] if years else ""
    summary = teacher_workload_summary(organization=organization, teacher=user, academic_year=year)
    total = int(summary.get("total_hours") or 0)
    # `workload.view` açarı dekan/koordinator/rektorda da var (FAZA 21 §1 qeydi);
    # onlarda sətir HEÇ VAXT olmur.  Sıfır saatlıq «0/500/0%» kartı ana səhifədə
    # sırf səs-küydür — tədris aparmayan aktora GÖSTƏRİLMİR.
    if not total and not is_teacher:
        return None
    return widget(
        "my-workload",
        pgettext(_CTX, "Dərs yüküm"),
        "fa-briefcase",
        tone="success" if total else "",
        stats=[
            stat(pgettext(_CTX, "İllik cəmi"), total, pgettext(_CTX, "saat")),
            stat(pgettext(_CTX, "Norma"), int(summary.get("norm_hours") or 0), pgettext(_CTX, "saat")),
            stat(pgettext(_CTX, "Doluluq"), "%s%%" % int(summary.get("fill_percent") or 0), year),
        ],
        link=section_link("my-workload", pgettext(_CTX, "Dərs yükünə keç")),
        empty=pgettext(_CTX, "Təsdiqlənmiş dərs yükü yoxdur."),
    )


__all__ = [
    "ROW_LIMIT",
    "my_workload",
    "section_link",
    "stat",
    "student_attendance",
    "student_grades",
    "student_today",
    "teacher_offerings",
    "teacher_syllabus",
    "teacher_today",
    "todays_slots",
    "upcoming_slots",
    "widget",
]
