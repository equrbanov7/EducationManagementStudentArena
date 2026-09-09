"""«Fənn təhvili» cədvəl SƏTİRLƏRİ — təhvil siyahısı və tarixçə.

`ems_ui/_data_table.html` müqaviləsi: hər sətir ``{row_head, head_include,
cells, actions_include, data}``. Bütün dinamik dəyərlər ``row.data``-dadır və
şablon onları `data-*` atributlarına yazır — xarici JS oradan oxuyur (CSP).

⚠️ Sətir başına SORĞU YOXDUR. Blokerlər və təsir sayğacları səhifə üçün TOPLU
hesablanır (`apps.registrar.handover_query`), sonra sətirlərə paylanır.
"""

from __future__ import annotations

import json

from django.utils.translation import pgettext

from apps.accounts.views.handover.labels import REVERT, blocker_labels
from apps.accounts.views.handover.policy import period_label, person_name
from apps.registrar import handover_query

_CTX = "accounts.handover"

#: Sətir xanalarının şablon qovluğu.
CELL_DIR = "accounts/profile/sections/handover/"


def _badge(tone: str, label) -> dict:
    """`ems_ui/_status_badge.html`-in gözlədiyi minimal status obyekti.

    Kataloqa (`core/ui/status_catalog.py`) YENİ ailə əlavə edilmir: təhvilin iki
    vəziyyəti var və onlar bu ekrandan kənarda işlənmir — paylaşılan kataloqu
    bir ekran üçün şişirtmək mənasızdır. Komponent yalnız ``css_class`` +
    ``label`` oxuyur, ona görə sadə sözlük kifayətdir.
    """
    return {"css_class": f"ems-badge ems-badge--{tone}", "label": label}


def columns() -> list:
    return [
        {"key": "subject", "label": pgettext(_CTX, "Fənn")},
        {"key": "group", "label": pgettext(_CTX, "Qrup")},
        {"key": "period", "label": pgettext(_CTX, "Semestr")},
        {"key": "instructor", "label": pgettext(_CTX, "Cari müəllim")},
        {"key": "impact", "label": pgettext(_CTX, "Təsir")},
        {"key": "state", "label": pgettext(_CTX, "Vəziyyət")},
        {"key": "actions", "label": pgettext(_CTX, "Əməliyyat")},
    ]


def offering_rows(offerings, *, actor, organization) -> list:
    """Səhifənin sətirləri — TOPLU bloker + təsir hesablaması ilə."""
    offerings = list(offerings)
    if not offerings:
        return []
    labels = blocker_labels()
    codes_by_id = handover_query.bulk_blockers(offerings, actor=actor, organization=organization)
    counts = handover_query.impact_counts([offering.pk for offering in offerings])

    rows = []
    for offering in offerings:
        codes = codes_by_id.get(offering.pk, [])
        stats = counts.get(offering.pk, {})
        subject = offering.subject
        data = {
            "id": str(offering.pk),
            "subject_code": getattr(subject, "code", "") or "",
            "subject_name": getattr(subject, "name", "") or getattr(subject, "code", "") or "",
            "group": getattr(offering.group, "name", "") or "",
            "period": period_label(offering.period),
            "instructor": person_name(offering.instructor),
            "students": stats.get("students", 0),
            "lessons": stats.get("lessons", 0),
            "marks": stats.get("marks", 0),
            "finals": stats.get("finals", 0),
            "can_transfer": not codes,
            "blockers": [{"code": code, "label": str(labels.get(code, code))} for code in codes],
        }
        data["blocker_text"] = " · ".join(item["label"] for item in data["blockers"])
        data["payload"] = json.dumps(data, ensure_ascii=False)
        data["status"] = (
            _badge("success", pgettext(_CTX, "Təhvil verilə bilər"))
            if not codes
            else _badge("danger", pgettext(_CTX, "Təhvil verilə bilməz"))
        )
        rows.append(
            {
                "row_head": data["subject_name"],
                "head_include": f"{CELL_DIR}_cell_subject.html",
                "cells": [
                    {"text": data["group"] or "—", "muted": not data["group"], "nowrap": True},
                    {"text": data["period"] or "—", "muted": not data["period"]},
                    {"include": f"{CELL_DIR}_cell_instructor.html"},
                    {"include": f"{CELL_DIR}_cell_impact.html"},
                    {"include": f"{CELL_DIR}_cell_state.html"},
                ],
                "actions_include": f"{CELL_DIR}_row_actions.html",
                "data": data,
            }
        )
    return rows


# ── Tarixçə ──────────────────────────────────────────────────────────────────


def history_columns() -> list:
    return [
        {"key": "subject", "label": pgettext(_CTX, "Fənn")},
        {"key": "when", "label": pgettext(_CTX, "Tarix")},
        {"key": "move", "label": pgettext(_CTX, "Kimdən → kimə")},
        {"key": "who", "label": pgettext(_CTX, "Əməliyyatı aparan")},
        {"key": "reason", "label": pgettext(_CTX, "Səbəb")},
        {"key": "state", "label": pgettext(_CTX, "Vəziyyət")},
        {"key": "actions", "label": pgettext(_CTX, "Əməliyyat")},
    ]


def history_rows(records, *, organization) -> list:
    """Tarixçə sətirləri — geri qaytarma blokerləri TOPLU hesablanır.

    Aktor QƏSDƏN ötürülMÜR: əhatə `scoped_history` ilə onsuz da daraldılıb və
    `blockers` aktor verildikdə geri qaytarmanın QƏBUL etdiyi kodları da
    qaytarardı (bax `handover_actions.REVERT_BLOCKER_CODES`).
    """
    from django.utils import timezone

    from apps.registrar import handover as handover_read
    from apps.registrar.handover_actions import REVERT_BLOCKER_CODES

    records = list(records)
    if not records:
        return []
    today = timezone.localdate()
    labels = blocker_labels(action=REVERT)
    live = [record for record in records if not record.is_reverted]
    closed_ids = handover_read.closed_offering_ids([record.offering_id for record in live])

    rows = []
    for record in records:
        offering = record.offering
        codes = []
        if not record.is_reverted:
            codes = [
                code
                for code in handover_read.blockers(
                    offering, organization=organization, closed_ids=closed_ids, today=today
                )
                if code in REVERT_BLOCKER_CODES
            ]
            if offering.instructor_id != record.to_instructor_id:
                codes.append("chain_moved")
        data = {
            "id": str(record.pk),
            "offering_id": str(record.offering_id),
            "subject": getattr(offering.subject, "name", "") or getattr(offering.subject, "code", ""),
            "group": getattr(offering.group, "name", "") or "",
            "period": period_label(offering.period),
            "from_name": record.from_instructor_name or "—",
            "to_name": record.to_instructor_name or "—",
            "performed_by": person_name(record.performed_by),
            "created_at": record.created_at,
            "reason": record.reason,
            "is_reverted": record.is_reverted,
            "revert_reason": record.revert_reason,
            "blockers": [{"code": code, "label": str(labels.get(code, code))} for code in codes],
            # MÜQAVİLƏ: düymə YALNIZ serverin həqiqətən qəbul edəcəyi sətirdə.
            "can_revert": (not record.is_reverted) and not codes,
        }
        data["blocker_text"] = " · ".join(item["label"] for item in data["blockers"])
        data["status"] = (
            _badge("muted", pgettext(_CTX, "Geri qaytarılıb"))
            if record.is_reverted
            else _badge("success" if data["can_revert"] else "warning", pgettext(_CTX, "Qüvvədədir"))
        )
        rows.append(
            {
                "row_head": data["subject"],
                "head_include": f"{CELL_DIR}_cell_history_subject.html",
                "cells": [
                    {"include": f"{CELL_DIR}_cell_history_when.html"},
                    {"include": f"{CELL_DIR}_cell_history_move.html"},
                    {"text": data["performed_by"] or "—", "muted": not data["performed_by"]},
                    {"text": data["reason"] or "—", "muted": not data["reason"]},
                    {"include": f"{CELL_DIR}_cell_history_state.html"},
                ],
                "actions_include": f"{CELL_DIR}_history_actions.html",
                "data": data,
            }
        )
    return rows


__all__ = ["CELL_DIR", "columns", "history_columns", "history_rows", "offering_rows"]
