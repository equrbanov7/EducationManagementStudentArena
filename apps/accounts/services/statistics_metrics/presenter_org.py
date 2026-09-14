"""«Statistika» presenter — imtahan mərkəzi, təşkilat/struktur vahidi, superadmin.

`presenter.py` ilə eyni müqavilə; fayl modul ölçüsü qaydasına (SOFT_CAP 600)
görə ayrılıb.
"""

from __future__ import annotations

from .presenter import (
    bars_block,
    cap_tiles,
    cell,
    col,
    distribution_bars,
    fmt_dec,
    fmt_int,
    fmt_pct,
    lifecycle_bars,
    ratio_tile,
    t,
    table_block,
    tile,
)

#: `Organization.org_type` → oxunaqlı etiket (superadmin paylanması).
_ORG_TYPE_LABELS = {
    "university": "Universitet",
    "school": "Məktəb",
    "course_center": "Kurs mərkəzi",
    "individual": "Fərdi",
}


# ── İmtahan mərkəzi ───────────────────────────────────────────────────────────


def exam_center_tiles(m: dict) -> list[dict]:
    exams = m["exams"]
    outcome = m["outcome"]
    appeals = m["appeals"]
    rooms = m["rooms"]
    sessions = m["sessions"]
    incidents = m["incidents"]
    entry = m["score_entry"]

    tiles = []
    if exams["total"]:
        tiles.append(
            tile(
                "exams",
                t("İmtahanlar"),
                fmt_int(exams["total"]),
                note=t("planlaşdırılıb %(scheduled)s · aktiv %(running)s · bitib %(finished)s")
                % {
                    "scheduled": fmt_int(exams["scheduled"]),
                    "running": fmt_int(exams["running"]),
                    "finished": fmt_int(exams["finished"]),
                },
                tone="primary",
            )
        )
    if outcome["finished"]:
        checked_pct = outcome["checked"] * 100.0 / outcome["finished"]
        tiles.append(
            tile(
                "attempts",
                t("Cəhdlər"),
                fmt_int(outcome["finished"]),
                note=t("yoxlanılıb %(checked)s · növbədə %(queue)s")
                % {"checked": fmt_pct(checked_pct), "queue": fmt_int(outcome["grading_queue"])},
                tone="accent-warning" if outcome["grading_queue"] else None,
            )
        )
        tiles.append(
            tile(
                "pass_rate",
                t("Keçid faizi"),
                fmt_dec(outcome["pass_rate"], 1),
                unit="%",
                note=t("orta bal %(avg)s") % {"avg": fmt_pct(outcome["avg_score"])},
            )
        )
    if appeals["total"]:
        tiles.append(
            tile(
                "appeals",
                t("Açıq apellyasiya"),
                fmt_int(appeals["open"]),
                unit=f"/ {fmt_int(appeals['total'])}",
                note=t("qəbul %(accepted)s · rədd %(rejected)s")
                % {"accepted": fmt_int(appeals["accepted"]), "rejected": fmt_int(appeals["rejected"])},
                tone="accent-warning" if appeals["open"] else None,
            )
        )
    if entry["total"]:
        tiles.append(
            ratio_tile(
                "score_entry",
                t("Yekun bal daxil edilib"),
                entry["entered"],
                entry["total"],
                note=t("dərc olunub %(published)s") % {"published": fmt_int(entry["published"])},
            )
        )
    if rooms["rooms"]:
        tiles.append(
            tile(
                "rooms",
                t("İmtahan zalları"),
                fmt_int(rooms["rooms"]),
                note=t("%(computers)s kompüter · %(capacity)s yer · %(live)s canlı oturum")
                % {
                    "computers": fmt_int(rooms["computers"]),
                    "capacity": fmt_int(rooms["capacity"]),
                    "live": fmt_int(sessions["live"]),
                },
            )
        )
    if incidents["total"]:
        tiles.append(
            tile(
                "incidents",
                t("Nəzarət insidentləri"),
                fmt_int(incidents["total"]),
                note=t("yüksək/kritik %(severe)s") % {"severe": fmt_int(incidents["severe"])},
                tone="accent-danger" if incidents["severe"] else None,
            )
        )
    return cap_tiles(tiles)


def exam_center_blocks(m: dict) -> list[dict]:
    exams = m["exams"]
    appeals = m["appeals"]
    rooms = m["rooms"]
    sessions = m["sessions"]

    appeal_items = (
        ("open", t("Baxılır"), "warning"),
        ("accepted", t("Qəbul edilib"), "success"),
        ("rejected", t("Rədd edilib"), "danger"),
    )
    top = max((appeals.get(key, 0) for key, _l, _t in appeal_items), default=0)
    appeal_bars = [
        {
            "label": label,
            "value_label": fmt_int(appeals.get(key, 0)),
            "sub": "",
            "pct": int(round(appeals.get(key, 0) * 100.0 / top)) if top else 0,
            "tone": tone,
        }
        for key, label, tone in appeal_items
    ]
    room_rows = [
        {
            "row_head": row["name"] + (f" · {row['code']}" if row["code"] else ""),
            "cells": [
                cell(fmt_int(row["capacity"]), num=True),
                cell(fmt_int(row["computers"]), num=True),
                cell(fmt_int(row["sessions"]), num=True),
            ],
        }
        for row in rooms["rows"]
    ]
    session_sub = t("Dövrdə %(total)s oturum · bitib %(ended)s · ləğv %(cancelled)s") % {
        "total": fmt_int(sessions["total"]),
        "ended": fmt_int(sessions["ended"]),
        "cancelled": fmt_int(sessions["cancelled"]),
    }
    return [
        bars_block(
            "lifecycle",
            t("İmtahan həyat dövrü"),
            lifecycle_bars(exams) if exams["total"] else [],
            empty=t("Dövrdə imtahan yoxdur."),
        ),
        bars_block(
            "appeals",
            t("Apellyasiya nəticələri"),
            appeal_bars if appeals["total"] else [],
            empty=t("Dövrdə apellyasiya yoxdur."),
        ),
        table_block(
            "rooms",
            t("İmtahan zalları"),
            [
                col("room", t("Zal")),
                col("capacity", t("Yer"), num=True),
                col("computers", t("Kompüter"), num=True),
                col("sessions", t("Oturum"), num=True),
            ],
            room_rows,
            sub=session_sub if rooms["rooms"] else None,
            empty=t("Aktiv imtahan zalı yoxdur."),
        ),
    ]


def present_exam_center(m: dict) -> dict:
    return {
        "profile": "exam_center",
        "scope_label": "",
        "kpis": exam_center_tiles(m),
        "blocks": exam_center_blocks(m),
        "extra": [],
    }


# ── Təşkilat / struktur vahidi ────────────────────────────────────────────────


def present_org(m: dict, *, exam_center: dict | None = None) -> dict:
    members = m["members"]
    records = m["records"]
    offerings = m["offerings"]
    syllabi = m["syllabi"]
    workload = m["workload"]
    courses = m["courses"]
    outcome = m["outcome"]
    appeals = m["appeals"]
    period_label = m["period"]["label"]
    scoped = m["profile"] == "unit_manager"

    tiles = []
    if members["total"]:
        tiles.append(
            tile(
                "members",
                t("Üzvlər"),
                fmt_int(members["total"]),
                note=t("tələbə %(students)s · müəllim %(teachers)s · heyət %(staff)s")
                % {
                    "students": fmt_int(members["students"]),
                    "teachers": fmt_int(members["teachers"]),
                    "staff": fmt_int(members["staff"]),
                },
                tone="primary",
            )
        )
    if records["total"]:
        tiles.append(
            tile(
                "records",
                t("Aktiv tələbə qeydi"),
                fmt_int(records["enrolled"]),
                note=(
                    t("%(programs)s ixtisas · akademik məzuniyyət %(leave)s")
                    % {"programs": fmt_int(records["programs"]), "leave": fmt_int(records["on_leave"])}
                ),
            )
        )
    if offerings["total"]:
        tiles.append(
            tile(
                "offerings",
                t("Fənn açılışı"),
                fmt_int(offerings["total"]),
                note=t("%(groups)s qrup · %(instructors)s müəllim · %(period)s")
                % {
                    "groups": fmt_int(offerings["groups"]),
                    "instructors": fmt_int(offerings["instructors"]),
                    "period": period_label or t("cari dövr"),
                },
            )
        )
        tiles.append(ratio_tile("journals", t("Bağlı jurnal"), offerings["journals_published"], offerings["total"]))
    if syllabi["total"]:
        tiles.append(
            ratio_tile(
                "syllabi",
                t("Təsdiqli sillabus"),
                syllabi["approved"],
                syllabi["total"],
                note=t("təsdiq gözləyir %(pending)s") % {"pending": fmt_int(syllabi["pending"])},
            )
        )
    if workload["total"]:
        tiles.append(
            ratio_tile(
                "workload",
                t("Yük bölgüsü tamamlanıb"),
                workload["distributed"],
                workload["total"],
                note=t("bölgü davam edir %(n)s") % {"n": fmt_int(workload["in_progress"])},
            )
        )
    if outcome["finished"]:
        tiles.append(
            tile(
                "attempts",
                t("İmtahan cəhdləri"),
                fmt_int(outcome["finished"]),
                note=t("keçid %(rate)s · orta bal %(avg)s")
                % {"rate": fmt_pct(outcome["pass_rate"]), "avg": fmt_pct(outcome["avg_score"])},
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
    if courses["total"]:
        tiles.append(
            tile(
                "courses",
                t("LMS kursları"),
                fmt_int(courses["published"]),
                unit=f"/ {fmt_int(courses['total'])}",
                note=t("dərc olunmuş / cəmi"),
            )
        )

    process_rows = []
    for _key, label, done, total, pending in (
        ("journals", t("Jurnal bağlama"), offerings["journals_published"], offerings["total"], None),
        ("syllabi", t("Sillabus təsdiqi"), syllabi["approved"], syllabi["total"], syllabi["pending"]),
        ("workload", t("Dərs yükü bölgüsü"), workload["distributed"], workload["total"], workload["in_progress"]),
    ):
        if not total:
            continue
        process_rows.append(
            {
                "row_head": label,
                "cells": [
                    cell(fmt_int(done), num=True),
                    cell(fmt_int(total), num=True),
                    cell(fmt_pct(done * 100.0 / total), num=True),
                    cell(fmt_int(pending) if pending is not None else "—", num=True, muted=pending is None),
                ],
            }
        )

    students_title = t("Qruplar üzrə tələbə") if scoped else t("İxtisaslar üzrə tələbə")
    blocks = [
        bars_block(
            "students",
            students_title,
            distribution_bars(records["distribution"], unit_label=t("tələbə")),
            sub=t("Aktiv akademik qeydlər (qeydiyyatlı status)."),
            empty=t("Aktiv akademik qeyd yoxdur."),
        ),
        bars_block(
            "roles",
            t("Üzvlər rol üzrə"),
            distribution_bars(members["by_role"], unit_label=t("üzv")),
            empty=t("Aktiv üzvlük yoxdur."),
        ),
        table_block(
            "process",
            t("Proseslərin gedişi"),
            [
                col("process", t("Proses")),
                col("done", t("Tamamlanıb"), num=True),
                col("total", t("Cəmi"), num=True),
                col("pct", t("Faiz"), num=True),
                col("pending", t("Gözləyir"), num=True),
            ],
            process_rows,
            sub=period_label or None,
            empty=t("Cari dövr üçün proses məlumatı yoxdur."),
        ),
    ]
    extra = []
    if exam_center is not None:
        extra.append(
            {
                "key": "exam_center",
                "title": t("İmtahan mərkəzi"),
                "kpis": exam_center_tiles(exam_center),
                "blocks": exam_center_blocks(exam_center),
            }
        )
    return {
        "profile": m["profile"],
        "scope_label": period_label,
        "kpis": cap_tiles(tiles),
        "blocks": blocks,
        "extra": extra,
    }


# ── Superadmin ────────────────────────────────────────────────────────────────


def present_superadmin(m: dict) -> dict:
    orgs = m["organizations"]
    users = m["users"]
    exams = m["exams"]
    outcome = m["outcome"]
    courses = m["courses"]

    tiles = [
        tile(
            "organizations",
            t("Aktiv təşkilat"),
            fmt_int(orgs["total"]),
            note=t("universitet %(n)s") % {"n": fmt_int(orgs["universities"])},
            tone="primary",
        ),
        tile(
            "users",
            t("Aktiv istifadəçi"),
            fmt_int(users["active"]),
            note=t("üzvlük %(n)s") % {"n": fmt_int(users["memberships"])},
        ),
        tile(
            "students",
            t("Tələbələr"),
            fmt_int(users["students"]),
            note=t("müəllim %(n)s") % {"n": fmt_int(users["teachers"])},
        ),
    ]
    if exams["total"]:
        tiles.append(
            tile(
                "exams",
                t("İmtahanlar"),
                fmt_int(exams["total"]),
                note=t("aktiv %(running)s · planlaşdırılıb %(scheduled)s")
                % {"running": fmt_int(exams["running"]), "scheduled": fmt_int(exams["scheduled"])},
            )
        )
    if outcome["finished"]:
        tiles.append(
            tile(
                "attempts",
                t("Cəhdlər"),
                fmt_int(outcome["finished"]),
                note=t("keçid %(rate)s · orta bal %(avg)s")
                % {"rate": fmt_pct(outcome["pass_rate"]), "avg": fmt_pct(outcome["avg_score"])},
            )
        )
    if courses["total"]:
        tiles.append(
            tile(
                "courses",
                t("Kurslar"),
                fmt_int(courses["published"]),
                unit=f"/ {fmt_int(courses['total'])}",
                note=t("dərc olunmuş / cəmi"),
            )
        )
    type_bars = distribution_bars(
        [{**item, "label": t(_ORG_TYPE_LABELS.get(item["label"], item["label"]))} for item in orgs["by_type"]],
        unit_label=t("təşkilat"),
    )
    blocks = [
        bars_block(
            "org_types",
            t("Təşkilat növləri"),
            type_bars,
            empty=t("Aktiv təşkilat yoxdur."),
        ),
    ]
    return {"profile": "superadmin", "scope_label": "", "kpis": cap_tiles(tiles), "blocks": blocks, "extra": []}
