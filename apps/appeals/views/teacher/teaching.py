"""«Fənnimə aid apellyasiyalar» — müəllimin YALNIZ-OXU görünüşü (sahib 2026-10-21).

Sahib: «… həmin müəllimin də səhifəsində görünsün bu». Müəllim öz tədris etdiyi açılışların (jurnal sahibi və ya
cədvəl slotunun müəllimi) tələbələrinin həmin fənn üzrə apellyasiyalarını görür: status, etiraz olunan suallar,
qərar, qərarı verən müəllim. QƏRAR HÜQUQU VERİLMİR — qərar əvvəlki kimi imtahan mərkəzinin
``appeal.respond`` + ``appeal.decide`` açarı ilədir (``services.permissions``).

Əhatə: ``services.teachers.teaching_appeals_queryset`` (aktiv təşkilat daxilində, RLS altında). Kabinet bölməsi
kimi bağlamaq üçün kontekst qurucusu (:func:`build_teaching_appeals_context`) ``apps.appeals.public``-dədir.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.tenancy import get_request_organization

from ...constants import APPEAL_STATUS_CHOICES, APPEAL_STATUS_VALUES
from ...services.teachers import attach_subject_teachers, teaching_appeals_queryset
from ._review_decision import decided_teacher_names

_PAGE_SIZE = 20


def build_teaching_appeals_context(request):
    organization = get_request_organization(request)
    appeals = (
        teaching_appeals_queryset(request.user, organization)
        .select_related("exam", "attempt", "student")
        .prefetch_related("items__question", "items__decided_by_teacher", "items__score_adjustment")
        .order_by("-created_at", "-id")
    )
    status_filter = (request.GET.get("status") or "").strip()
    if status_filter in APPEAL_STATUS_VALUES:
        appeals = appeals.filter(status=status_filter)
    page_obj = Paginator(appeals, _PAGE_SIZE).get_page(request.GET.get("page", 1))
    rows = list(page_obj.object_list)
    attach_subject_teachers(rows)
    for appeal in rows:
        appeal.decided_teacher_names = decided_teacher_names(appeal)
        appeal.item_rows = list(appeal.items.all())
        appeal.accepted_count = sum(1 for item in appeal.item_rows if item.status == "accepted")
        appeal.rejected_count = sum(1 for item in appeal.item_rows if item.status == "rejected")
    try:
        open_id = int(request.GET.get("open") or 0)
    except (TypeError, ValueError):
        open_id = 0
    return {
        "teaching_appeals": rows,
        "teaching_page_obj": page_obj,
        "teaching_status_choices": APPEAL_STATUS_CHOICES,
        "teaching_status_filter": status_filter if status_filter in APPEAL_STATUS_VALUES else "",
        "teaching_open_id": open_id,
    }


@login_required
@require_GET
def teaching_appeals(request):
    return render(request, "appeals/teacher/teaching_appeals.html", build_teaching_appeals_context(request))


__all__ = ["build_teaching_appeals_context", "teaching_appeals"]
