"""Cəhd → son apellyasiyanın statusu — siyahı ekranları üçün yüngül toplu oxu (2026-10-17).

«Dəyərləndirilmiş nəticələr» cədvəli hər imtahan sətrində apellyasiya nişanını və
«Apellyasiya» KPI-ni göstərir. ``history.appeal_rows_by_attempt`` bal fərqi, baxan
şəxs və bənd sayları ilə 3+ sorğu atır — burada yalnız status lazımdır: TƏK sorğu,
cəhd sayından asılı deyil.
"""

from __future__ import annotations

from apps.appeals.constants import APPEAL_STATUS_CHOICES, APPEAL_STATUS_FINAL
from apps.appeals.models import Appeal

_STATUS_LABELS = dict(APPEAL_STATUS_CHOICES)
_CHUNK = 5000


def appeal_status_by_attempt(attempt_ids) -> dict:
    """``attempt_id`` → ``{"status", "label", "is_final"}`` (cəhdin ƏN SON apellyasiyası) — 1 sorğu."""
    ids = sorted({pk for pk in attempt_ids if pk})
    if not ids:
        return {}
    rows = []
    # Review 2026-10-18: çox uzun tarixçədə Postgres-in ~65k parametr həddinə çatmamaq üçün hissə-hissə
    # (adi halda yenə TƏK sorğu). Hər hissədə sıra eynidir → «ən son» qaydası dəyişmir.
    for start in range(0, len(ids), _CHUNK):
        rows.extend(
            Appeal.objects.filter(attempt_id__in=ids[start : start + _CHUNK])
            .order_by("created_at", "id")
            .values_list("attempt_id", "status")
        )
    out: dict = {}
    for attempt_id, status in rows:
        out[attempt_id] = {
            "status": status,
            "label": str(_STATUS_LABELS.get(status, status)),
            "is_final": status in APPEAL_STATUS_FINAL,
        }
    return out


def student_appeal_status_by_attempt(attempt_ids, *, at_time=None) -> dict:
    """Tələbə səthləri üçün ``appeal_status_by_attempt`` (Paket A, 2026-10-18).

    Qərar tələbəyə yalnız rəyçinin redaktə pəncərəsi bağlanandan sonra görünür
    (``appeal_item_result_visible_to_student`` — nəticə səhifəsi və «Apellyasiyalarım» ilə eyni
    qayda): bəndlərdən biri hələ gizlidirsə status ``under_review`` («Baxılır») qaytarılır.
    Sorğu sayı sabitdir: apellyasiyalar + bəndlər (prefetch) — cəhd sayından asılı deyil.
    """
    from django.db.models import Prefetch

    from apps.appeals.constants import APPEAL_STATUS_UNDER_REVIEW
    from apps.appeals.models import AppealItem
    from apps.appeals.services.scoring import appeal_item_result_visible_to_student

    ids = sorted({pk for pk in attempt_ids if pk})
    if not ids:
        return {}
    items_qs = AppealItem.objects.only("id", "appeal_id", "status", "resolved_at")
    appeals = []
    for start in range(0, len(ids), _CHUNK):
        appeals.extend(
            Appeal.objects.filter(attempt_id__in=ids[start : start + _CHUNK])
            .only("id", "attempt_id", "status", "created_at")
            .prefetch_related(Prefetch("items", queryset=items_qs))
            .order_by("created_at", "id")
        )
    out: dict = {}
    for appeal in appeals:
        hidden = any(not appeal_item_result_visible_to_student(item, at_time=at_time) for item in appeal.items.all())
        status = APPEAL_STATUS_UNDER_REVIEW if hidden else appeal.status
        out[appeal.attempt_id] = {
            "status": status,
            "label": str(_STATUS_LABELS.get(status, status)),
            "is_final": status in APPEAL_STATUS_FINAL,
        }
    return out
