"""Profil "my-exams" bölməsinin «Zibil qutusu» alt-görünüşü (2026-09-14, W3 `w3myexams`).

Sahib: «Oradakı zibil qutusu yerini də düzəlt, daha yaxşı formada.» Əvvəl
«Zibil qutusu» başlıqdakı mətn linki idi və ayrıca tam səhifəyə
(`exams:deleted_exams_list`) aparırdı. İndi bölmənin İÇİNDƏ alt-görünüşdür:
``?section=my-exams&exam_view=trash`` — tab «İmtahanlarım / Zibil qutusu»,
başlıqda sayğaclı ikon düyməsi. Bərpa / birdəfəlik silmə endpoint-ləri və
icazə qaydaları DƏYİŞMİR (``exams:restore_exam`` / ``exams:permanent_delete_exam``).

Cədvəl `ems_ui/_data_table.html` müqaviləsi ilə qurulur (view-model burada,
şablon yalnız render edir).
"""

from __future__ import annotations

from django.db.models import Count
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import pgettext

from apps.accounts.views._helpers.tenant import _tenant_scoped_exams

#: Alt-görünüş sorğu parametri (`?section=my-exams&exam_view=trash`).
TRASH_VIEW_PARAM = "exam_view"
TRASH_VIEW_VALUE = "trash"

_ROW_HEAD_TEMPLATE = "accounts/profile/sections/partials/_my_exams_trash_row_head.html"
_ROW_ACTIONS_TEMPLATE = "accounts/profile/sections/partials/_my_exams_trash_row_actions.html"


def is_trash_view(request) -> bool:
    """Sorğu «Zibil qutusu» alt-görünüşünü istəyirmi."""
    return (request.GET.get(TRASH_VIEW_PARAM, "") or "").strip() == TRASH_VIEW_VALUE


def trash_view_url() -> str:
    return f"{reverse('accounts:profile')}?section=my-exams&{TRASH_VIEW_PARAM}={TRASH_VIEW_VALUE}"


def _deleted_exams_queryset(request):
    from apps.exams.models import Exam

    # `include_deleted=True` MƏCBURİDİR: tenant keçidi default olaraq yumşaq
    # silinmişləri çıxarır — məhz onlar lazımdır (yalnız müəllifin özününkülər).
    return _tenant_scoped_exams(
        request,
        Exam.objects.filter(author=request.user, is_deleted=True),
        include_deleted=True,
    )


def _table_columns() -> list[dict]:
    ctx = "exams.template.deleted_exams"
    return [
        {"key": "exam", "label": pgettext(ctx, "col_exam")},
        {"key": "results", "label": pgettext(ctx, "col_results")},
        {"key": "deleted_at", "label": pgettext(ctx, "col_deleted_at")},
        # Əməllər sütununun vizual başlığı yoxdur; boş `<th>` a11y pozuntusudur (P2-8).
        {"key": "actions", "label": pgettext(ctx, "col_actions"), "sr_only": True},
    ]


def _table_row(exam) -> dict:
    deleted_at = ""
    if exam.deleted_at:
        deleted_at = formats.date_format(timezone.localtime(exam.deleted_at), "d.m.Y H:i")
    return {
        "exam": exam,
        "head_include": _ROW_HEAD_TEMPLATE,
        "cells": [
            {"text": exam.attempts_total, "num": True},
            {"text": deleted_at or "—", "muted": True, "nowrap": True},
        ],
        "actions_include": _ROW_ACTIONS_TEMPLATE,
    }


def build_my_exams_trash_context(request, *, is_open: bool) -> dict:
    """«Zibil qutusu» üçün context (`my_exams_dashboard.trash` altında).

    Sayğac HƏMİŞƏ hesablanır (başlıqdakı ikon düyməsi + tab üçün, 1 COUNT);
    siyahı yalnız alt-görünüş açıq olanda yüklənir. Sorğu sayı sətir sayından
    asılı deyil: COUNT + (açıqdırsa) annotate-li tək SELECT.
    """
    deleted_qs = _deleted_exams_queryset(request)
    context = {
        "is_open": is_open,
        "count": deleted_qs.count(),
        "url": trash_view_url(),
        "table_columns": _table_columns(),
        "table_rows": [],
        "table_state": "empty",
    }
    if not is_open:
        return context

    exams = list(
        deleted_qs.annotate(attempts_total=Count("attempts", distinct=True)).order_by("-deleted_at", "-created_at")
    )
    context["table_rows"] = [_table_row(exam) for exam in exams]
    context["table_state"] = "ready" if exams else "empty"
    return context
