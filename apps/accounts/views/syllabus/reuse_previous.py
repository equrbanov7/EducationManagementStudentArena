"""«Keçən ildən köçür» — AÇILIŞDAN (sillabussuz qrup) və ya boş qaralamadan (2026-10-08).

Əvvəl «Sillabus yoxdur» sətrindəki düymə AÇILIŞIN id-sini ``syllabus_action`` →
``copy``-yə SİLLABUS id-si kimi göndərirdi və 404 alırdı.  İndi düymə təkrar istifadə
dialoqunu ``mode=previous`` ilə açır: eyni fənnin BAŞQA semestrlərdəki (və ya
semestrsiz baza) dosyeləri siyahılanır, müəllim birini seçir və hədəf açılış üçün
QARALAMA yaranır (``services.reuse.copy_adjust(previous=True)``).

Əhatə ``copy_from_previous`` ilə EYNİDİR: mənbənin müəllifi və ya mənbənin kafedrasını
``syllabus.edit`` ilə əhatə edən aktor (``reuse_rules.previous_queryset`` yalnız belə
dosyeləri qaytarır — TƏK sorğu).  Bağlama burada YOXDUR: başqa semestrin təsdiqi bu
semestrə köçürülmür, nəticə adi təsdiq axınına düşür.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from apps.syllabus.public import SyllabusStatus, services

from .labels import HOUR_KIND_LABELS, STATUS_TONES, transition_text
from .reuse_context import _person, group_label, hours_text, target_block

_CTX = "accounts.syllabus"

_YOU = pgettext_lazy(_CTX, "Müəllif: siz")
_BASE = pgettext_lazy(_CTX, "Semestrsiz baza sillabus")


def _period_title(row) -> str:
    period = row.period if row.period_id else None
    if period is None:
        return str(_BASE)
    return f"{period.year_display} · {period.name}"


def _previous_row(row, *, actor, target, target_code) -> dict:
    from .rows import approver_text

    rules = services.reuse_rules
    approved = row.approved_version if row.approved_version_id else None
    base = approved or row.current_version
    base_hours = getattr(base, "plan_hours", None) or {}
    copy_code = rules.copy_code(row, actor=actor, target_code=target_code, copyable=True)
    version = row.current_version
    status = version.status if version is not None else SyllabusStatus.DRAFT.value
    author = str(_YOU) if row._own else _person(row.author)
    return {
        "id": str(row.pk),
        "group": _period_title(row),
        "author": " · ".join(part for part in (author, group_label(row) if row.offering_id else "") if part),
        "own": bool(row._own),
        "status_key": status,
        "status_label": str(SyllabusStatus(status).label),
        "status_tone": STATUS_TONES.get(status, "neutral"),
        "version_label": base.label if base is not None else "—",
        "approver": approver_text(row, approved) if approved is not None else "",
        "hours_text": hours_text(base_hours),
        "hours_same": services.hours_match(base_hours, target.plan_hours),
        "hours_rows": [
            {**item, "label": str(HOUR_KIND_LABELS[item["kind"]])}
            for item in rules.hours_rows(base_hours, target.plan_hours)
        ],
        "linked_count": 0,
        "can_link": False,
        "link_reason": "",
        "can_copy": not copy_code,
        "copy_reason": transition_text(copy_code) if copy_code else "",
        "modes": {},
    }


def build_previous_options(organization, actor, target) -> dict:
    """Dialoqun «Keçən ildən köçür» rejimi — ``reuse_api.syllabus_reuse_options`` (``mode=previous``)."""
    holder = target.syllabus if target.syllabus is not None else target.offering
    rows = list(
        services.reuse_rules.previous_queryset(
            organization=organization,
            actor=actor,
            subject_id=holder.subject_id,
            period_id=holder.period_id,
        )
    )
    target_code = services.reuse_rules.target_state_code(target.syllabus)
    return {
        "mode": "previous",
        "target": target_block(target, target_code),
        "siblings": [_previous_row(row, actor=actor, target=target, target_code=target_code) for row in rows],
        "candidates": [],
        "can_create_blank": target.syllabus is None,
    }


__all__ = ["build_previous_options"]
