"""«Ana səhifə» — TƏLƏBƏ kartları (2026-09-25 yenidən qurulub).

Sahibin iradı: «davamiyyət kartı — nəyin davamiyyəti, hansı fənnin qayıbı? Heç
aydın deyil».  Köhnə kart bütün fənlərin qayıb saatını CƏMLƏYİB proqramın xam
limitini («25%») yanına yazırdı — halbuki limit HƏR FƏNN ÜZRƏ ayrıcadır (fənnin
dərs saatlarının N %-i).  İndi hər kart bir suala cavab verir:

* «Davamiyyət — fənlər üzrə» — hər fənndə neçə saat qayıb, icazə neçə saatdır,
  status nədir (riskli fənlər yuxarıda);
* «Cari ballar — fənlər üzrə» — giriş balı X / 50 + Midterm X / 20 (köhnə
  dövrdə K1–K3); köhnə arxiv komponentləri HEÇ VAXT göstərilmir;
* «Bu gün / növbəti dərslər» — bu günün dərsləri, yoxdursa real növbəti dərs günü.

Rəqəmlər ``apps.registrar.public.dashboard_data.student_subjects``-dən gəlir
(bir dəfə hesablanır, iki kart paylaşır) — qaydalar burada TƏKRAR YAZILMIR.
"""

from __future__ import annotations

from collections import Counter

from django.utils.translation import pgettext, pgettext_lazy

from . import dashboard_lessons as lessons
from .dashboard_widgets import (
    SUBJECT_ROW_LIMIT,
    fmt_number,
    journal_link,
    plain_number,
    section_link,
    stat,
    subject_journal_url,
    widget,
)

_CTX = "accounts.dashboard"

#: Buraxılış statusu → çip (mətn + ton).  Açarlar ``exam_eligibility`` status
#: ailəsidir (``student_subjects_context.eligibility_status``); mətn davamiyyət
#: kontekstinə uyğunlaşdırılıb — rəng yalnız köməkçi siqnaldır (handoff §7).
STATUS_CHIPS = {
    "ok": (pgettext_lazy(_CTX, "Normal"), "success"),
    "near": (pgettext_lazy(_CTX, "Limitə yaxın"), "warning"),
    "barred": (pgettext_lazy(_CTX, "Limit keçib — imtahana buraxılmır"), "danger"),
    "frozen": (pgettext_lazy(_CTX, "Köhnə sistemdən"), "muted"),
    "unknown": (pgettext_lazy(_CTX, "Məlumat yoxdur"), "neutral"),
}

#: Çipin izahı (``title`` atributu) — «limitə yaxın» nə deməkdir və s.
STATUS_HINTS = {
    "ok": pgettext_lazy(_CTX, "Qayıb icazə verilən həddin altındadır."),
    "near": pgettext_lazy(_CTX, "İcazə verilən qayıbın 75%-i keçilib — davamiyyətə diqqət edin."),
    "barred": pgettext_lazy(_CTX, "Qayıb həddi keçilib — bu fəndən yekun imtahana buraxılmırsınız."),
    "frozen": pgettext_lazy(_CTX, "Köhnə sistemdən köçürülmüş bağlı semestr — status yenidən hesablanmır."),
    "unknown": pgettext_lazy(_CTX, "Fənnin dərs saatı təyin olunmayıb — limit hesablana bilmir."),
}


def _no_record_widget(key, title, icon, link):
    return widget(
        key,
        title,
        icon,
        link=link,
        empty=pgettext(_CTX, "Akademik qeydiniz tapılmadı — RİM-ə müraciət edin."),
    )


# --------------------------------------------------------------------------- #
# Bu gün / növbəti dərslər
# --------------------------------------------------------------------------- #


def student_today(*, organization, record, period, allowed_sections, today, now) -> dict | None:
    """Qrup cədvəli — bu günün dərsləri, qalmayıbsa real NÖVBƏTİ dərs günü.

    Akademik qeydi (SAR), qrupu və ya cari dövrü OLMAYAN tələbədə vidjet YOX
    OLMUR — boş vəziyyət göstərir: köçürülmüş bazada qeydsiz hesablar var və
    «heç nə görünmür» onlar üçün nasazlıqdan fərqlənmir.
    """
    if "my-schedule" not in allowed_sections:
        return None
    title = pgettext(_CTX, "Bu gün / növbəti dərslər")
    link = section_link("my-schedule", pgettext(_CTX, "Cədvələ keç"))
    group = getattr(record, "group", None) if record is not None else None
    if period is None or group is None:
        return widget(
            "student-today",
            title,
            "fa-calendar-day",
            link=link,
            empty=pgettext(_CTX, "Cari semestr üçün qrup cədvəliniz tapılmadı."),
            empty_without_rows=True,
        )
    from apps.registrar.public import schedule as schedule_service

    slots = schedule_service.get_group_schedule(organization=organization, group=group, period=period)
    card = lessons.build(slots, period=period, today=today, now=now, with_group=False)
    return widget(
        "student-today",
        title,
        "fa-calendar-day",
        tone="primary" if card["rows"] else "",
        stats=card["stats"],
        rows=card["rows"],
        body="lessons",
        caption=card["caption"],
        link=link,
        empty=card["empty"]
        or pgettext(
            _CTX, "Bu semestr üçün qrupunuzun dərs cədvəli hələ qurulmayıb — cədvəl dərc olunanda burada görünəcək."
        ),
        empty_without_rows=True,
    )


# --------------------------------------------------------------------------- #
# Davamiyyət — fənlər üzrə
# --------------------------------------------------------------------------- #


def _attendance_row(row, period) -> dict:
    status = row["status"]
    label, tone = STATUS_CHIPS.get(status, STATUS_CHIPS["unknown"])
    allowed = row["allowed_hours"]
    absent = row["absence_hours"]
    if allowed > 0:
        value = pgettext(_CTX, "qayıb %(absent)s / icazə %(allowed)s saat") % {
            "absent": fmt_number(absent),
            "allowed": fmt_number(allowed),
        }
        bar = {"value": plain_number(min(absent, allowed)), "max": plain_number(allowed)}
    else:
        value = pgettext(_CTX, "qayıb %(absent)s saat · fənnin dərs saatı təyin olunmayıb") % {
            "absent": fmt_number(absent)
        }
        bar = None
    return {
        "title": row["subject_name"],
        "url": subject_journal_url(period, row["enrollment_id"]),
        "value": value,
        "bar": bar,
        "status": status,
        "status_label": str(label),
        "status_hint": str(STATUS_HINTS.get(status, "")),
        "tone": tone,
    }


def student_attendance(*, record, period, subjects, allowed_sections) -> dict | None:
    """Hər fənn üçün «qayıb X / icazə Y saat» + limit zolağı + status çipi."""
    if "my-journal" not in allowed_sections:
        return None
    key, title, icon = "student-attendance", pgettext(_CTX, "Davamiyyət — fənlər üzrə"), "fa-user-check"
    link = journal_link(period)
    if record is None:
        return _no_record_widget(key, title, icon, link)
    if period is None:
        return widget(key, title, icon, link=link, empty=pgettext(_CTX, "Cari tədris dövrü müəyyən edilməyib."))
    data_rows = (subjects or {}).get("rows") or []
    subtitle = pgettext(_CTX, "Limit hər fənn üzrə ayrıca hesablanır: fənnin dərs saatlarının %(percent)s%%-i.") % {
        "percent": (subjects or {}).get("limit_percent", 25)
    }
    if not data_rows:
        return widget(
            key,
            title,
            icon,
            subtitle=subtitle,
            link=link,
            empty=pgettext(_CTX, "Cari semestrdə fənn qeydiyyatınız yoxdur — sualınız varsa dekanlığa müraciət edin."),
        )
    counts = Counter(row["status"] for row in data_rows)
    near, barred = counts.get("near", 0), counts.get("barred", 0)
    stats = [
        stat(pgettext(_CTX, "Limitə yaxın"), near, pgettext(_CTX, "fənn")),
        stat(pgettext(_CTX, "Limit keçib"), barred, pgettext(_CTX, "fənn")),
        stat(pgettext(_CTX, "Cəmi"), len(data_rows), pgettext(_CTX, "fənn")),
    ]
    if barred:  # ən ağır hal əvvəl — hero zolağı da onu götürür
        stats[0], stats[1] = stats[1], stats[0]
    notice = ""
    if subjects.get("exempt"):
        notice = pgettext(_CTX, "İdmançı istisnası: limit keçilsə də imtahana buraxılırsınız.")
    return widget(
        key,
        title,
        icon,
        tone="danger" if barred else ("warning" if near else "success"),
        stats=stats,
        rows=[_attendance_row(row, period) for row in data_rows[:SUBJECT_ROW_LIMIT]],
        body="attendance",
        subtitle=subtitle,
        notice=notice,
        total=len(data_rows),
        wide=True,
        link=link,
    )


# --------------------------------------------------------------------------- #
# Cari ballar — fənlər üzrə
# --------------------------------------------------------------------------- #


def _interim_chip(item, *, compact: bool) -> dict:
    written = item["score"] is not None
    if written:
        text = "%s / %s" % (fmt_number(item["score"]), item["max"])
    else:
        text = "—" if compact else pgettext(_CTX, "hələ yazılmayıb")
    return {"label": item["label"], "text": text, "written": written}


def _score_row(row, period, spec) -> dict:
    entry, cap = row["entry_score"], row["entry_max"]
    return {
        "title": row["subject_name"],
        "url": subject_journal_url(period, row["enrollment_id"]),
        "entry": fmt_number(entry),
        "entry_max": cap,
        "bar": {"value": plain_number(min(entry, cap)), "max": plain_number(cap)} if cap else None,
        "interim": [_interim_chip(item, compact=not spec.is_midterm) for item in row["interim"]],
    }


def student_scores(*, record, period, subjects, allowed_sections) -> dict | None:
    """Giriş balı (imtahana qədər toplanan) + aralıq qiymətləndirmə — fənn-fənn.

    Açar köhnə «Son qiymətlər» kartınınkıdır (``student-grades``): bölmə xəritəsi
    və mövcud QA ssenariləri dəyişmir, məzmun isə yalnız CARİ dövrdür.
    """
    if "my-journal" not in allowed_sections:
        return None
    key, title, icon = "student-grades", pgettext(_CTX, "Cari ballar — fənlər üzrə"), "fa-star"
    link = journal_link(period)
    if record is None:
        return _no_record_widget(key, title, icon, link)
    data_rows = sorted((subjects or {}).get("rows") or [], key=lambda row: row["subject_name"].lower())
    spec = (subjects or {}).get("spec")
    if period is None or not data_rows or spec is None:
        return widget(
            key,
            title,
            icon,
            link=link,
            empty=pgettext(_CTX, "Cari semestrdə bal yazılan fənniniz yoxdur."),
        )
    count = len(data_rows)
    average = sum(row["entry_score"] for row in data_rows) / count
    caps = {row["entry_max"] for row in data_rows}
    written = sum(1 for row in data_rows if any(item["score"] is not None for item in row["interim"]))
    subtitle = pgettext(_CTX, "Giriş balı — imtahana qədər toplanan bal (maks. %(max)s).") % {
        "max": caps.pop() if len(caps) == 1 else 50
    }
    return widget(
        key,
        title,
        icon,
        stats=[
            stat(pgettext(_CTX, "Orta giriş balı"), fmt_number(average), pgettext(_CTX, "fənlər üzrə")),
            stat(spec.title, "%s / %s" % (written, count), pgettext(_CTX, "fəndə yazılıb")),
        ],
        rows=[_score_row(row, period, spec) for row in data_rows[:SUBJECT_ROW_LIMIT]],
        body="scores",
        subtitle=subtitle,
        notice=spec.description,
        total=count,
        wide=True,
        link=link,
    )


__all__ = ["STATUS_CHIPS", "STATUS_HINTS", "student_attendance", "student_scores", "student_today"]
