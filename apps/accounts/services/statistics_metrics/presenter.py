"""«Statistika» — metrik modelini `ems_ui` kart/blok müqaviləsinə çevirən qat.

Niyə ayrı qat: metrik modulları YALNIZ rəqəm qaytarır və qısa keşlənir
(`core.cache.get_or_set_cached_statistics`); etiketlər isə hər sorğuda aktiv
dilə görə burada qurulur — keşə heç bir tərcümə obyekti düşmür. Qayda (sahib,
2026-09-12): sıfır məxrəcli / rola aid olmayan kart RENDER OLUNMUR — hər
kartın etiketi, dəyəri, vahidi/məxrəci və (ucuz olanda) izah qeydi var.

Kart lüğəti `partials/ems_ui/_kpi_tile.html` müqaviləsidir (label, value,
unit, note, tone, has_bar, pct, key); blok lüğəti `_statistics.html`-in
`bars` / `table` növləridir.
"""

from __future__ import annotations

from datetime import date, datetime

from django.utils import timezone
from django.utils.translation import pgettext

from ._shared import clamp_pct

_CTX = "profile.statistics"
NBSP = "\u00a0"
#: Yuxarı zolaqda maksimum kart (dashboard qaydası: 4–6 KPI).
MAX_TILES = 6


def t(text: str) -> str:
    return pgettext(_CTX, text)


def fmt_int(value) -> str:
    """Min ayırıcılı tam ədəd («8 622»)."""
    try:
        return f"{int(value or 0):,}".replace(",", NBSP)
    except (TypeError, ValueError):
        return "0"


def fmt_dec(value, digits: int = 1) -> str:
    """Onluq ədəd — vergüllü («72,5»)."""
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}".replace(".", ",")


def fmt_pct(value) -> str:
    return "—" if value is None else fmt_dec(value, 1) + "%"


def fmt_date(value) -> str:
    """ISO tarix/vaxt sətri → «dd.mm.yyyy» (vaxt varsa «dd.mm.yyyy HH:MM»)."""
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        try:
            return date.fromisoformat(str(value)).strftime("%d.%m.%Y")
        except ValueError:
            return str(value)
    if timezone.is_aware(parsed):
        parsed = timezone.localtime(parsed)
    if parsed.hour == 0 and parsed.minute == 0:
        return parsed.strftime("%d.%m.%Y")
    return parsed.strftime("%d.%m.%Y %H:%M")


def tile(key, label, value, *, unit=None, note=None, tone=None, pct=None):
    """`_kpi_tile.html` kartı; `pct` verilərsə tərəqqi zolağı çəkilir."""
    item = {"key": key, "label": label, "value": value, "unit": unit, "note": note, "tone": tone}
    if pct is not None:
        item["has_bar"] = True
        item["pct"] = clamp_pct(pct)
    return item


def ratio_tile(key, label, done, total, *, note=None, tone=None):
    """«N / M» kartı — dəyər tamamlanmış, vahid məxrəc, zolaq faiz."""
    share = (float(done) * 100.0 / float(total)) if total else 0.0
    return tile(key, label, fmt_int(done), unit=f"/ {fmt_int(total)}", note=note, tone=tone, pct=share)


def cap_tiles(tiles) -> list[dict]:
    """None-ları at, MAX_TILES-a qədər saxla (prioritet = sıra)."""
    return [item for item in tiles if item is not None][:MAX_TILES]


def bars_block(key, title, items, *, sub=None, empty=None):
    """Paylanma bloku: items = [{label, value_label, sub, pct, tone}]."""
    return {"key": key, "kind": "bars", "title": title, "sub": sub, "bars": list(items), "empty": empty}


def table_block(key, title, columns, rows, *, sub=None, empty=None):
    """Cədvəl bloku — `partials/ems_ui/_data_table.html` müqaviləsi ilə."""
    return {
        "key": key,
        "kind": "table",
        "title": title,
        "sub": sub,
        "columns": columns,
        "rows": rows,
        "state": "ready" if rows else "empty",
        "empty": empty,
    }


def col(key, label, *, num=False):
    return {"key": key, "label": label, "align": "right" if num else "left"}


def cell(text, *, num=False, muted=False):
    return {"text": text, "num": num, "muted": muted}


def chip(text, tone="neutral"):
    """Rəngli çip xanası — `sections/statistics/_cell_chip.html`."""
    return {"text": text, "tone": tone, "include": "accounts/profile/sections/statistics/_cell_chip.html"}


def attendance_tone(value) -> str | None:
    if value is None:
        return None
    if value >= 85:
        return "accent-success"
    if value >= 75:
        return "accent-warning"
    return "accent-danger"


def lifecycle_bars(exams: dict) -> list[dict]:
    """İmtahan həyat dövrü paylanması (draft/scheduled/running/finished)."""
    order = (
        ("draft", t("Qaralama"), "neutral"),
        ("scheduled", t("Planlaşdırılıb"), "info"),
        ("running", t("Aktiv"), "success"),
        ("finished", t("Bitib"), "muted"),
    )
    top = max((int(exams.get(key) or 0) for key, _label, _tone in order), default=0)
    return [
        {
            "label": label,
            "value_label": fmt_int(exams.get(key)),
            "sub": "",
            "pct": clamp_pct(float(exams.get(key) or 0) * 100.0 / top) if top else 0,
            "tone": tone,
        }
        for key, label, tone in order
    ]


def distribution_bars(items, *, unit_label) -> list[dict]:
    """`_shared.distribution` nəticəsi → blok sətirləri («34% · 120 tələbə»)."""
    return [
        {
            "label": item["label"],
            "value_label": fmt_int(item["count"]),
            "sub": (fmt_pct(item["share"]) + " · " + unit_label) if item.get("share") is not None else unit_label,
            "pct": item["pct"],
            "tone": None,
        }
        for item in items
    ]


def exam_status_chip(*, is_active, start, end, now) -> dict:
    """Cədvəl xanası üçün həyat dövrü çipi (presenter tərəfində, sorğusuz)."""
    if not is_active:
        return chip(t("Qaralama"), "neutral")
    start_at = datetime.fromisoformat(start) if start else None
    end_at = datetime.fromisoformat(end) if end else None
    if start_at and start_at > now:
        return chip(t("Planlaşdırılıb"), "info")
    if end_at and end_at < now:
        return chip(t("Bitib"), "muted")
    return chip(t("Aktiv"), "success")


# ── Tələbə ────────────────────────────────────────────────────────────────────


def present_student(m: dict) -> dict:
    academic = m["academic"]
    exams = m["exams"]
    assignments = m["assignments"]
    appeals = m["appeals"]
    periods = academic["periods"]

    tiles = []
    if academic["enrollments"] or academic["has_record"]:
        total_ects = academic["program_ects_total"]
        note_parts = []
        if total_ects:
            note_parts.append(t("proqram tələbi: %(total)s ECTS") % {"total": fmt_int(total_ects)})
        if academic["credits_in_progress"]:
            note_parts.append(t("davam edir: %(n)s ECTS") % {"n": fmt_int(academic["credits_in_progress"])})
        tiles.append(
            tile(
                "credits",
                t("Toplanmış kredit"),
                fmt_int(academic["credits_earned"]),
                unit="ECTS",
                note=" · ".join(note_parts) or None,
                tone="primary",
                pct=(academic["credits_earned"] * 100.0 / total_ects) if total_ects else None,
            )
        )
    if academic["gpa"] is not None:
        graded_periods = [p for p in periods if p["avg_total"] is not None]
        note = t("%(n)s qiymətləndirilmiş fənn") % {"n": fmt_int(academic["graded"])}
        if len(graded_periods) >= 2:
            delta = graded_periods[0]["avg_total"] - graded_periods[1]["avg_total"]
            sign = "+" if delta >= 0 else "−"
            note += " · " + t("əvvəlki semestrə görə %(delta)s bal") % {"delta": sign + fmt_dec(abs(delta), 1)}
        # Backend auditi 2026-09-13, F-05: bu kart 4.0 şkalalı, kredit-çəkili
        # GPA-dır (`student.py`: Σ(GPA nöqtəsi×kredit)/Σkredit); transkriptdəki
        # «Kumulyativ ÜOMG» isə 100 ballıq ortadır (`exam_eligibility.uomg_from`).
        # Eyni «ÜOMG» adı ilə iki fərqli rəqəm göstərilirdi (3.50 vs 78.40) —
        # düsturlar dəyişmir, ETİKET fərqləndirilir.
        note = t("4.0 şkalası") + " · " + note
        tiles.append(tile("gpa", t("Orta GPA (4.0)"), fmt_dec(academic["gpa"], 2), note=note))
    if academic["lesson_hours"]:
        tiles.append(
            tile(
                "attendance",
                t("Davamiyyət"),
                fmt_dec(academic["attendance_pct"], 1),
                unit="%",
                note=t("%(absent)s saat qayıb / %(hours)s saat")
                % {"absent": fmt_int(academic["absence_hours"]), "hours": fmt_int(academic["lesson_hours"])},
                tone=attendance_tone(academic["attendance_pct"]),
            )
        )
    if exams["finished"]:
        tiles.append(
            tile(
                "exams",
                t("İmtahan cəhdləri"),
                fmt_int(exams["finished"]),
                note=t("keçid %(rate)s · orta bal %(avg)s")
                % {"rate": fmt_pct(exams["pass_rate"]), "avg": fmt_pct(exams["avg_score"])},
            )
        )
    if assignments["total"]:
        tiles.append(
            tile(
                "assignments",
                t("Gözləyən tapşırıq"),
                fmt_int(assignments["pending"]),
                unit=f"/ {fmt_int(assignments['total'])}",
                note=t("gecikmiş %(late)s · göndərilmiş %(sent)s")
                % {"late": fmt_int(assignments["overdue"]), "sent": fmt_int(assignments["submitted"])},
                tone="accent-warning" if assignments["overdue"] else None,
            )
        )
    if academic["enrollments"]:
        in_progress = max(academic["enrollments"] - academic["graded"], 0)
        tiles.append(
            tile(
                "subjects",
                t("Keçilmiş fənn"),
                fmt_int(academic["passed"]),
                note=t("kəsilmiş %(failed)s · davam edən %(open)s")
                % {"failed": fmt_int(academic["failed"]), "open": fmt_int(in_progress)},
                tone="accent-danger" if academic["failed"] else None,
            )
        )
    if appeals["total"]:
        tiles.append(
            tile(
                "appeals",
                t("Açıq apellyasiya"),
                fmt_int(appeals["open"]),
                unit=f"/ {fmt_int(appeals['total'])}",
                tone="accent-warning" if appeals["open"] else None,
            )
        )

    period_bars = [
        {
            "label": p["label"],
            "value_label": (fmt_dec(p["avg_total"], 1) + " " + t("bal")) if p["avg_total"] is not None else "—",
            "sub": t("%(n)s fənn · %(credits)s ECTS · keçid %(passed)s/%(graded)s")
            % {
                "n": fmt_int(p["enrollments"]),
                "credits": fmt_int(p["credits"]),
                "passed": fmt_int(p["passed"]),
                "graded": fmt_int(p["graded"]),
            },
            "pct": clamp_pct(p["avg_total"]),
            "tone": None,
        }
        for p in periods
    ]
    attempt_rows = [
        {
            "row_head": row["title"],
            "cells": [
                cell(fmt_date(row["finished_at"]), muted=True),
                cell(fmt_pct(row["score_pct"]), num=True),
                (
                    chip(t("Gözləyir"), "warning")
                    if row["score_pct"] is None
                    else chip(t("Keçib"), "success") if row["score_pct"] >= 50 else chip(t("Kəsilib"), "danger")
                ),
                cell(t("Yoxlanılıb") if row["checked"] else t("Gözləyir"), muted=not row["checked"]),
            ],
        }
        for row in m["recent_attempts"]
    ]
    blocks = [
        bars_block(
            "periods",
            t("Semestr üzrə nəticə"),
            period_bars,
            sub=t("Orta yekun bal (0–100) və keçid — ən yeni semestr yuxarıda."),
            empty=t("Hələ qiymətləndirilmiş semestr yoxdur."),
        ),
        table_block(
            "attempts",
            t("Son imtahan nəticələri"),
            [
                col("exam", t("İmtahan")),
                col("date", t("Tarix")),
                col("score", t("Bal"), num=True),
                col("result", t("Nəticə")),
                col("check", t("Yoxlama")),
            ],
            attempt_rows,
            empty=t("Yekunlaşmış imtahan cəhdi yoxdur."),
        ),
    ]
    return {
        "profile": "student",
        "scope_label": academic["program_name"] or "",
        "kpis": cap_tiles(tiles),
        "blocks": blocks,
        "extra": [],
    }


# ── Müəllim ───────────────────────────────────────────────────────────────────


def present_teacher(m: dict) -> dict:
    offerings = m["offerings"]
    courses = m["courses"]
    exams = m["exams"]
    outcome = exams["outcome"]
    now = timezone.now()

    tiles = []
    if offerings["total"]:
        tiles.append(
            tile(
                "offerings",
                t("Fənn açılışı"),
                fmt_int(offerings["total"]),
                note=t("%(groups)s qrup · %(students)s tələbə")
                % {"groups": fmt_int(offerings["groups"]), "students": fmt_int(offerings["students"])},
                tone="primary",
            )
        )
        tiles.append(
            ratio_tile(
                "journals",
                t("Bağlı jurnal"),
                offerings["journals_published"],
                offerings["total"],
                note=t("cari dövrün açılışları üzrə"),
            )
        )
    if offerings["attendance_marks"]:
        tiles.append(
            tile(
                "attendance",
                t("Davamiyyət"),
                fmt_dec(offerings["attendance_pct"], 1),
                unit="%",
                note=t("%(n)s davamiyyət qeydi") % {"n": fmt_int(offerings["attendance_marks"])},
                tone=attendance_tone(offerings["attendance_pct"]),
            )
        )
    queue = outcome["grading_queue"] + courses["ungraded_submissions"]
    if exams["total"] or courses["total"]:
        tiles.append(
            tile(
                "grading",
                t("Yoxlama növbəsi"),
                fmt_int(queue),
                note=t("imtahan %(exams)s · tapşırıq %(tasks)s")
                % {"exams": fmt_int(outcome["grading_queue"]), "tasks": fmt_int(courses["ungraded_submissions"])},
                tone="accent-warning" if queue else "accent-success",
            )
        )
    if outcome["finished"]:
        tiles.append(
            tile(
                "pass_rate",
                t("Keçid faizi"),
                fmt_dec(outcome["pass_rate"], 1),
                unit="%",
                note=t("%(n)s cəhd · orta bal %(avg)s")
                % {"n": fmt_int(outcome["finished"]), "avg": fmt_pct(outcome["avg_score"])},
            )
        )
    if exams["total"]:
        note = t("aktiv %(running)s · planlaşdırılıb %(scheduled)s") % {
            "running": fmt_int(exams["running"]),
            "scheduled": fmt_int(exams["scheduled"]),
        }
        if exams["next_start"]:
            note += " · " + t("növbəti: %(date)s") % {"date": fmt_date(exams["next_start"])}
        tiles.append(tile("exams", t("İmtahanlarım"), fmt_int(exams["total"]), note=note))
    if courses["total"]:
        tiles.append(
            tile(
                "courses",
                t("Kurslarım"),
                fmt_int(courses["total"]),
                note=t("dərc olunub %(published)s · tələbə %(students)s")
                % {"published": fmt_int(courses["published"]), "students": fmt_int(courses["students"])},
            )
        )

    offering_rows = [
        {
            "row_head": (row["subject"] + (f" · {row['code']}" if row["code"] else "")),
            "cells": [
                cell(row["group"]),
                cell(fmt_int(row["students"]), num=True),
                cell(fmt_pct(row["attendance_pct"]), num=True, muted=row["attendance_pct"] is None),
                chip(t("Bağlı"), "success") if row["journal_published"] else chip(t("Açıq"), "warning"),
            ],
        }
        for row in offerings["rows"]
    ]
    exam_rows = [
        {
            "row_head": row["title"],
            "cells": [
                cell(row["course"] or "—", muted=not row["course"]),
                cell(fmt_date(row["start"]), muted=True),
                cell(fmt_int(row["attempts"]), num=True),
                exam_status_chip(is_active=row["is_active"], start=row["start"], end=row["end"], now=now),
            ],
        }
        for row in exams["rows"]
    ]
    blocks = [
        table_block(
            "offerings",
            t("Fənlərim (cari dövr)"),
            [
                col("subject", t("Fənn")),
                col("group", t("Qrup")),
                col("students", t("Tələbə"), num=True),
                col("attendance", t("Davamiyyət"), num=True),
                col("journal", t("Jurnal")),
            ],
            offering_rows,
            empty=t("Cari dövrdə sizə təyin olunmuş fənn açılışı yoxdur."),
        ),
        bars_block("lifecycle", t("İmtahan həyat dövrü"), lifecycle_bars(exams) if exams["total"] else []),
        table_block(
            "exams",
            t("Son imtahanlar"),
            [
                col("exam", t("İmtahan")),
                col("course", t("Kurs")),
                col("start", t("Başlanğıc")),
                col("attempts", t("Cəhd"), num=True),
                col("status", t("Status")),
            ],
            exam_rows,
            empty=t("Müəllif olduğunuz imtahan yoxdur."),
        ),
    ]
    blocks[1]["empty"] = t("Müəllif olduğunuz imtahan yoxdur.")
    return {"profile": "teacher", "scope_label": "", "kpis": cap_tiles(tiles), "blocks": blocks, "extra": []}
