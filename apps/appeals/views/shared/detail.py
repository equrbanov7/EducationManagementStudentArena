"""Appeals — apellyasiya detalı: sahib tələbə VƏ YA reviewer (F4, 2026-07-02)."""

from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from ...constants import APPEAL_ITEM_STATUS_ACCEPTED, APPEAL_ITEM_STATUS_REJECTED
from ...models import Appeal
from ...services import can_review_appeal, effective_test_score, is_within_appeal_window
from ._helpers import _marked_question_map


def _appeal_item_stats(items):
    """Detal səhifəsi üçün item statuslarının xülasəsi."""
    stats = {"total": len(items), "accepted": 0, "rejected": 0, "pending": 0}
    for item in items:
        if item.status == APPEAL_ITEM_STATUS_ACCEPTED:
            stats["accepted"] += 1
        elif item.status == APPEAL_ITEM_STATUS_REJECTED:
            stats["rejected"] += 1
        else:
            stats["pending"] += 1
    return stats


def _format_decimal(value):
    try:
        decimal_value = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, TypeError, ValueError):
        decimal_value = Decimal("0")
    if decimal_value == decimal_value.to_integral_value():
        return str(int(decimal_value))
    return format(decimal_value.normalize(), "f")


def _appeal_positive_bonus(items):
    bonus = Decimal("0")
    for item in items:
        adjustment = getattr(item, "score_adjustment", None)
        if not adjustment or adjustment.reverted or not adjustment.delta_points:
            continue
        if adjustment.delta_points > 0:
            bonus += adjustment.delta_points
    return bonus


@login_required
def appeal_detail(request, appeal_id):
    appeal = get_object_or_404(
        Appeal.objects.select_related("exam", "attempt", "reviewed_by", "student").prefetch_related(
            "items__question", "items__score_adjustment"
        ),
        id=appeal_id,
    )

    is_owner = appeal.student_id == request.user.id
    if not is_owner and not can_review_appeal(request, appeal):
        raise PermissionDenied

    items = list(appeal.items.all())
    score_info = effective_test_score(appeal.attempt) if appeal.exam.exam_type == "test" else None
    appeal_positive_bonus = _appeal_positive_bonus(items)

    context = {
        "appeal": appeal,
        "items": items,
        "is_owner": is_owner,
        "score_info": score_info,
        "item_stats": _appeal_item_stats(items),
        "is_within_window": is_within_appeal_window(appeal.attempt),
        "appeal_positive_bonus": appeal_positive_bonus,
        "appeal_positive_bonus_display": _format_decimal(appeal_positive_bonus),
        "marked_question_by_qid": _marked_question_map(appeal.attempt),
        "back_url": reverse("accounts:profile") + "?section=my-appeals",
    }

    # Dashboard daxili AJAX swap üçün yalnız gövdə fraqmenti qaytarılır.
    is_fragment = request.GET.get("fragment") == "1" or request.headers.get("x-requested-with") == "XMLHttpRequest"
    if is_fragment:
        return render(request, "appeals/partials/_appeal_detail_body.html", context)
    return render(request, "appeals/student/appeal_detail.html", context)
