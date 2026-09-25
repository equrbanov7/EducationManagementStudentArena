"""«Ana səhifə» — MÜƏLLİM kartları (2026-09-25 yenidən qurulub).

* «Bu gün / növbəti dərslərim» — bu günün dərsləri, qalmayıbsa real növbəti dərs
  günü; «Bu həftə» üst/alt paritetinə görə sayılır (əvvəl bütün slotlar sayılırdı).
* «Jurnallarım» — TAM say (əvvəl 6-da kəsilirdi) + fənn · qrup · tələbə sayı ·
  keçirilmiş / plan saatı; keçid sidebar kimi jurnal iş sahəsinə (`/jurnal/`,
  yeni tabda) aparır — əvvəl `?section=my-journal` idi və müəllimdə boş idi.
* «Midterm — bal yazma» — İmtahan Mərkəzinin pəncərəsi (açıq → son tarix,
  planlanıb → açılış tarixi, təyin olunmayıb → izah).  2026/2027-dən 3
  kollokvium əvəzinə TƏK Midterm (0–20); köhnə dövrdə K1–K3 sətirləri.

Rəqəmlər ``apps.registrar.public.dashboard_data``-dan gəlir; açılış sayı artanda
sorğu sayı artmır.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy

from . import dashboard_lessons as lessons
from .dashboard_widgets import (
    ROW_LIMIT,
    days_until,
    external_link,
    fmt_date,
    plain_number,
    section_link,
    stat,
    widget,
)

_CTX = "accounts.dashboard"

#: Pəncərə bu qədər gün içində bağlanırsa kart «təcili» tonuna keçir.
URGENT_DAYS = 3

#: Pəncərə statusu → qısa mətn (kartın «Vəziyyət» rəqəmi).
WINDOW_STATE = {
    "open": pgettext_lazy(_CTX, "Açıqdır"),
    "scheduled": pgettext_lazy(_CTX, "Planlanıb"),
    "closed": pgettext_lazy(_CTX, "Bağlanıb"),
    "inactive": pgettext_lazy(_CTX, "Deaktivdir"),
    "not_configured": pgettext_lazy(_CTX, "Təyin olunmayıb"),
}


def _journals_link() -> dict:
    return external_link("my-journal", pgettext(_CTX, "Jurnallara keç"), reverse("registrar:journal_list"))


# --------------------------------------------------------------------------- #
# Bu gün / növbəti dərslərim
# --------------------------------------------------------------------------- #


def teacher_today(*, organization, user, period, allowed_sections, today, now) -> dict | None:
    if "my-schedule" not in allowed_sections or period is None:
        return None
    from apps.registrar.public import schedule as schedule_service

    slots = schedule_service.get_teacher_schedule(organization=organization, teacher=user, period=period)
    card = lessons.build(slots, period=period, today=today, now=now, with_group=True, journal_links=True)
    return widget(
        "teacher-today",
        pgettext(_CTX, "Bu gün / növbəti dərslərim"),
        "fa-chalkboard-teacher",
        tone="primary" if card["rows"] else "",
        stats=card["stats"],
        rows=card["rows"],
        body="lessons",
        caption=card["caption"],
        link=section_link("my-schedule", pgettext(_CTX, "Cədvələ keç")),
        empty=card["empty"] or pgettext(_CTX, "Bu semestr üçün cədvəldə dərsiniz yoxdur."),
        empty_without_rows=True,
    )


# --------------------------------------------------------------------------- #
# Jurnallarım
# --------------------------------------------------------------------------- #


def _offering_row(row) -> dict:
    meta = [row["group_name"]] if row["group_name"] else []
    meta.append(pgettext(_CTX, "%(count)s tələbə") % {"count": row["students"]})
    held, plan = row["held_hours"], row["plan_hours"]
    if plan:
        value = pgettext(_CTX, "keçirilib %(held)s / %(plan)s saat") % {"held": held, "plan": plan}
        bar = {"value": plain_number(min(held, plan)), "max": plain_number(plan)}
    else:
        value = pgettext(_CTX, "keçirilib %(held)s saat") % {"held": held}
        bar = None
    return {
        "title": row["subject_name"],
        "meta": " · ".join(meta),
        "value": value,
        "bar": bar,
        "url": reverse("registrar:journal_detail", args=[row["offering_id"]]),
    }


def teacher_offerings(*, data, period, allowed_sections) -> dict | None:
    """«Jurnallarım» — cari dövrün açılışları (TAM say) + jurnal keçidləri."""
    if "my-journal" not in allowed_sections or period is None:
        return None
    data = data or {"total": 0, "students_total": 0, "rows": []}
    total = int(data.get("total") or 0)
    return widget(
        "teacher-offerings",
        pgettext(_CTX, "Jurnallarım"),
        "fa-book-open",
        stats=[
            stat(pgettext(_CTX, "Cari semestr"), total, pgettext(_CTX, "jurnal")),
            stat(pgettext(_CTX, "Tələbə"), int(data.get("students_total") or 0), pgettext(_CTX, "cəmi")),
        ],
        rows=[_offering_row(row) for row in (data.get("rows") or [])[:ROW_LIMIT]],
        body="offerings",
        total=total,
        wide=True,
        link=_journals_link(),
        empty=pgettext(_CTX, "Cari dövrdə sizə fənn təyin olunmayıb."),
    )


# --------------------------------------------------------------------------- #
# Midterm (aralıq qiymətləndirmə) — bal yazma pəncərəsi
# --------------------------------------------------------------------------- #


def _window_notice(item) -> str:
    status = item["status"]
    if status == "open":
        text = pgettext(_CTX, "Bal yazmaq açıqdır — son tarix %(date)s.") % {"date": fmt_date(item["closes_on"])}
    elif status == "scheduled":
        text = pgettext(_CTX, "Pəncərə %(opens)s-də açılır, son tarix %(closes)s.") % {
            "opens": fmt_date(item["opens_on"]),
            "closes": fmt_date(item["closes_on"]),
        }
    elif status == "closed":
        text = pgettext(_CTX, "Pəncərə %(date)s tarixində bağlanıb.") % {"date": fmt_date(item["closes_on"])}
    elif status == "inactive":
        text = pgettext(_CTX, "Pəncərə yaradılıb, amma İmtahan Mərkəzi onu hələ aktivləşdirməyib.")
    else:
        text = pgettext(_CTX, "İmtahan Mərkəzi hələ bal yazma pəncərəsini təyin etməyib.")
    if item.get("extended"):
        text = "%s %s" % (text, pgettext(_CTX, "Bəzi bölmələr üçün müddət uzadılıb — dəqiq tarix jurnaldadır."))
    return text


def window_short_text(item) -> str:
    """Pəncərənin bir sətirlik vəziyyəti — K1–K3 sətirləri və İmtahan Mərkəzi kartı üçün."""
    status = item["status"]
    if status == "open" and item.get("closes_on"):
        return pgettext(_CTX, "açıqdır · son tarix %(date)s") % {"date": fmt_date(item["closes_on"])}
    if status == "scheduled" and item.get("opens_on"):
        return pgettext(_CTX, "%(date)s-də açılır") % {"date": fmt_date(item["opens_on"])}
    if status == "closed" and item.get("closes_on"):
        return pgettext(_CTX, "bağlanıb · %(date)s") % {"date": fmt_date(item["closes_on"])}
    return str(WINDOW_STATE.get(status, "")).lower()


def _window_stats(item) -> list:
    stats = [stat(pgettext(_CTX, "Vəziyyət"), str(WINDOW_STATE.get(item["status"], "")))]
    if item["status"] in ("open", "closed") and item.get("closes_on"):
        stats.append(stat(pgettext(_CTX, "Son tarix"), fmt_date(item["closes_on"])))
    elif item["status"] == "scheduled" and item.get("opens_on"):
        stats.append(stat(pgettext(_CTX, "Açılır"), fmt_date(item["opens_on"])))
    return stats


def teacher_midterm(*, windows, has_offerings: bool, period, allowed_sections, today) -> dict | None:
    """İmtahan Mərkəzinin aralıq qiymətləndirmə pəncərəsi — müəllim nə vaxt bal yaza bilər.

    Pəncərə org səviyyəlidir (dövr başına bir sorğu); açılışa xas uzatmalar
    kartda yalnız «uzadılıb» qeydi kimi görünür.  Fənni olmayan müəllimdə
    kart göstərilmir (yazacaq balı yoxdur).
    """
    if "my-journal" not in allowed_sections or period is None or not has_offerings or not windows:
        return None
    spec = windows["spec"]
    items = windows.get("windows") or []
    title = pgettext(_CTX, "%(title)s — bal yazma") % {"title": spec.title}
    if spec.is_midterm and items:
        item = items[0]
        left = days_until(item.get("closes_on"), today)
        if item["status"] == "open":
            tone = "warning" if left is not None and left <= URGENT_DAYS else "success"
        else:
            tone = "primary" if item["status"] == "scheduled" else ""
        return widget(
            "teacher-midterm",
            title,
            "fa-pen-to-square",
            tone=tone,
            stats=_window_stats(item),
            subtitle=spec.description,
            notice=_window_notice(item),
            link=_journals_link(),
        )
    rows = [{"title": item["label"], "meta": window_short_text(item)} for item in items]
    return widget(
        "teacher-midterm",
        title,
        "fa-pen-to-square",
        tone="success" if windows.get("open_count") else "",
        stats=[stat(pgettext(_CTX, "Açıq"), int(windows.get("open_count") or 0), pgettext(_CTX, "pəncərə"))],
        rows=rows,
        subtitle=spec.description,
        link=_journals_link(),
        empty=pgettext(_CTX, "İmtahan Mərkəzi hələ bal yazma pəncərəsini təyin etməyib."),
    )


__all__ = [
    "URGENT_DAYS",
    "WINDOW_STATE",
    "teacher_midterm",
    "teacher_offerings",
    "teacher_today",
    "window_short_text",
]
