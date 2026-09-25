"""«Ana səhifə» (dashboard) vidjet müqaviləsi + ortaq köməkçilər + şəxsi iş kartları.

Hər qurucu funksiya BİR vidjet qaytarır (və ya ``None`` — vidjet ümumiyyətlə
göstərilmir).  Qapı həmişə ``allowed_sections`` / ``capabilities`` üzərindədir:
istifadəçinin AÇA BİLMƏDİYİ bölmənin rəqəmi kabinet ana səhifəsində də
GÖRÜNMÜR (sayğac sızması yoxdur).

Modullar (2026-09-25 bölgüsü — hər fayl 600 sətir limitindədir):

* bu fayl — ``widget()`` müqaviləsi, keçid/format köməkçiləri, «Sillabus
  işlərim», «Dərs yüküm»;
* ``dashboard_student`` — tələbənin fənn-fənn davamiyyəti, cari balları, dərsləri;
* ``dashboard_teacher`` — müəllimin dərsləri, jurnalları, Midterm pəncərəsi;
* ``dashboard_lessons`` — «bu gün / növbəti dərs günü» kartının ortaq qurucusu;
* ``dashboard_staff_widgets`` — idarəetmə vidjetləri.

BÜDCƏ: hər vidjet bir neçə UCUZ sorğu ilə məhdudlaşır; fənn/açılış sayı artanda
sorğu sayı ARTMIR (toplu oxuma ``apps.registrar.public.dashboard_data``-dadır).
Ümumi hədd testdə ``CaptureQueriesContext`` ilə kilidlənib
(``test_dashboard_section.py``, ``test_dashboard_student_teacher.py``).
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import formats
from django.utils.translation import pgettext

_CTX = "accounts.dashboard"

#: Vidjet siyahılarının maksimum sətir sayı (dizayn: ana səhifə = xülasə).
ROW_LIMIT = 5

#: Fənn-fənn kartlarında (davamiyyət, cari ballar) sətir həddi — tələbənin
#: semestrdə adətən 6–9 fənni olur və hamısı görünməlidir.
SUBJECT_ROW_LIMIT = 10

#: «Rəqəm yoxdur» sayılan dəyərlər (``dashboard_layout._BLANK_VALUES`` ilə eyni dil).
_BLANK = ("", "0", "0%")


# --------------------------------------------------------------------------- #
# Keçidlər
# --------------------------------------------------------------------------- #


def section_link(section: str, label, *, params=None) -> dict:
    """SPA-nın tutduğu `?section=` keçidi (sidebar linkləri ilə eyni müqavilə).

    ``params`` — əlavə sorğu parametrləri (məs. fənnin jurnalına dərin keçid:
    ``period`` + ``subject``); SPA onları fraqment sorğusuna olduğu kimi ötürür.
    ``title`` sonradan ``dashboard._finalise_links`` tərəfindən hədəf bölmənin
    RƏSMİ adı ilə doldurulur (SPA panel başlığını `data-title`-dan oxuyur).
    """
    query = {"section": section}
    query.update({key: str(value) for key, value in (params or {}).items() if value not in (None, "")})
    return {
        "section": section,
        "label": label,
        "title": "",
        "url": "%s?%s" % (reverse("accounts:profile"), urlencode(query)),
        "external": False,
    }


def external_link(section: str, label, url: str) -> dict:
    """Kabinet qabığından KƏNAR səhifə (müəllim jurnalı `/jurnal/` — sidebar kimi yeni tabda).

    ``section`` yalnız QAPI üçündür (``_finalise_links`` bölmə icazəsizdirsə
    linki silir); şablon belə linkə `data-section` YAZMIR — əks halda panelin
    SPA deleqasiyası onu tutub bölmə kimi yükləməyə çalışardı.
    """
    return {"section": section, "label": label, "title": "", "url": url, "external": True}


def journal_link(period, label=None) -> dict:
    """Tələbənin «Elektron jurnal» bölməsi — ana səhifənin dövrü ilə."""
    return section_link(
        "my-journal",
        label or pgettext(_CTX, "Jurnala keç"),
        params={"period": getattr(period, "pk", None)},
    )


def subject_journal_url(period, enrollment_id) -> str:
    """Fənnin jurnal detalına dərin keçid (`_journal_student_content.html` ilə eyni forma)."""
    params = {"period": getattr(period, "pk", None), "subject": enrollment_id}
    return section_link("my-journal", "", params=params)["url"]


# --------------------------------------------------------------------------- #
# Vidjet müqaviləsi
# --------------------------------------------------------------------------- #


def widget(
    key: str,
    title,
    icon: str,
    *,
    tone: str = "",
    stats=None,
    rows=None,
    link=None,
    empty="",
    body: str = "",
    subtitle="",
    notice="",
    caption="",
    total=None,
    wide: bool = False,
    empty_without_rows: bool = False,
) -> dict:
    """Vahid vidjet müqaviləsi — şablon YALNIZ bu açarları oxuyur.

    Əsas açarlar (dəyişməz): ``key``, ``title``, ``icon``, ``tone``, ``stats``,
    ``rows``, ``link``, ``empty``, ``is_empty``.  2026-09-25 əlavələri:

    * ``body``     — sətirlərin forması: "" (başlıq + meta), "attendance",
                     "scores", "lessons", "offerings" (hər biri ayrı partial);
    * ``subtitle`` — başlığın altındakı bir cümləlik izah (məs. limit qaydası);
    * ``notice``   — kartın sonundakı əlavə qeyd;
    * ``caption``  — siyahının başlığı («Bu gün · Cümə axşamı, 25.09»);
    * ``total``    — siyahının TAM sayı («+N daha» üçün; verilməyibsə birinci rəqəm);
    * ``wide``     — geniş ekranda iki sütun tutan kart (fənn-fənn siyahılar).

    ``is_empty`` BURADA hesablanır: sətir yoxdursa VƏ bütün rəqəmlər sıfırdırsa
    vidjet «boşdur».  ``empty_without_rows`` — rəqəmlərindən asılı olmayaraq
    sətirsiz kart boşdur (məs. dərs kartında «Növbəti: yoxdur» mətni rəqəm deyil).
    """
    stats = list(stats or ())
    rows = list(rows or ())
    if empty_without_rows:
        is_empty = not rows
    else:
        is_empty = not rows and all(str(item.get("value", "")).strip() in _BLANK for item in stats)
    return {
        "key": key,
        "title": title,
        "icon": icon,
        "tone": tone,
        "stats": stats,
        "rows": rows,
        "link": link,
        "empty": empty,
        "is_empty": is_empty,
        "body": body,
        "subtitle": subtitle,
        "notice": notice,
        "caption": caption,
        "total": total,
        "wide": bool(wide),
    }


def stat(label, value, note="") -> dict:
    return {"label": label, "value": value, "note": note}


def take(queryset, limit: int = ROW_LIMIT):
    """``(ilk limit sətir, TAM say)`` — say yalnız siyahı DOLANDA ayrıca sorğulanır.

    Əvvəlki kartlar ``[:6]`` dilimini sayıb «Növbədə: 6» yazırdı (real say 40
    olsa da).  Bir sətir artıq oxunur: həddə sığırsa uzunluq TAM saydır (əlavə
    sorğu yoxdur), sığmırsa ``count()`` gedir.
    """
    rows = list(queryset[: limit + 1])
    if len(rows) <= limit:
        return rows, len(rows)
    return rows[:limit], queryset.count()


# --------------------------------------------------------------------------- #
# Format köməkçiləri
# --------------------------------------------------------------------------- #


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def fmt_number(value) -> str:
    """Saat/bal — ən çox bir onluq, dilə görə ayırıcı: 7.50 → «7,5», 15.00 → «15».

    İcazəli qayıb çox vaxt kəsrlidir (30 saatın 25%-i = 7,5); onu «8»-ə
    yuvarlaqlaşdırmaq YALANDIR — 8 saat qayıb artıq limit keçməkdir.
    """
    number = _decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if number == number.to_integral_value():
        return formats.number_format(int(number))
    return formats.number_format(number, 1)


def plain_number(value) -> str:
    """`<progress value/max>` üçün NÖQTƏLİ ədəd (lokallaşdırılmır — HTML atributudur)."""
    number = _decimal(value)
    return format(number.normalize(), "f") if number else "0"


def fmt_date(day) -> str:
    return day.strftime("%d.%m.%Y") if day else ""


def weekday_label(day) -> str:
    """Həftə gününün adı — registrar cədvəli ilə eyni tərcümə (`registrar.weekday`)."""
    from apps.registrar.public import schedule as schedule_service

    labels = dict(schedule_service.WEEKDAYS)
    return str(labels.get(day.isoweekday(), "")) if day else ""


def day_label(day) -> str:
    """«Bazar ertəsi, 29.09» — kartlarda qısa tarix."""
    if not day:
        return ""
    return "%s, %s" % (weekday_label(day), day.strftime("%d.%m"))


def time_range(slot) -> str:
    start = getattr(slot, "start_time", None)
    end = getattr(slot, "end_time", None)
    if start is None:
        return ""
    return "%s–%s" % (start.strftime("%H:%M"), end.strftime("%H:%M") if end else "")


def days_until(day, today) -> int | None:
    if not isinstance(day, datetime.date):
        return None
    return (day - today).days


# --------------------------------------------------------------------------- #
# Şəxsi iş kartları (rol-agnostik)
# --------------------------------------------------------------------------- #


def teacher_syllabus(*, request, organization, allowed_sections) -> dict | None:
    """«Sillabus işlərim» — qaralama + düzəliş tələb olunan versiyaların TAM sayı."""
    if "syllabus-list" not in allowed_sections:
        return None
    from apps.syllabus.public import SyllabusStatus, list_syllabi, resolve_actor

    actor = resolve_actor(request.user, organization, request=request)
    pending, total = take(
        list_syllabi(
            organization=organization,
            actor=actor,
            statuses=[SyllabusStatus.DRAFT, SyllabusStatus.REVISION],
        )
    )
    rows = [
        {
            "title": getattr(row.subject, "name", "") or "—",
            "meta": str(getattr(getattr(row, "current_version", None), "get_status_display", lambda: "")() or ""),
        }
        for row in pending
    ]
    return widget(
        "teacher-syllabus",
        pgettext(_CTX, "Sillabus işlərim"),
        "fa-file-signature",
        tone="warning" if rows else "",
        stats=[stat(pgettext(_CTX, "Gözləyən"), total, pgettext(_CTX, "sillabus"))],
        rows=rows,
        total=total,
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
    "SUBJECT_ROW_LIMIT",
    "day_label",
    "days_until",
    "external_link",
    "fmt_date",
    "fmt_number",
    "journal_link",
    "my_workload",
    "plain_number",
    "section_link",
    "stat",
    "subject_journal_url",
    "take",
    "teacher_syllabus",
    "time_range",
    "weekday_label",
    "widget",
]
