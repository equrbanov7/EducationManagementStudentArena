"""Reviewer qərar modalı üçün sual-sual MÜQAYİSƏ + TARİXÇƏ konteksti (2026-10-13, gecə).

Əvvəl modal variantları CANLI sualdan (``question.options`` + ``opt.is_correct``) və canlı
seçimdən (``answer.selected_options``) göstərirdi: müəllif imtahandan sonra sualı redaktə
etsə, imtahan mərkəzi tələbənin GÖRDÜYÜ yox, dəyişmiş sualı və açarı görürdü — qərar səhv
sübut üzərində verilirdi. İndi müqayisə ÇATDIRILMA snapshot-undan qurulur (nəticə və
apellyasiya yaratma səhifəsi ilə eyni ``delivered_question_render``), dondurulmuş seçim
varsa ondan oxunur, aktiv açar düzəlişi isə ayrıca işarələnir.

Sorğu büdcəsi: bütün item-lər üçün açar düzəlişləri və bal düzəlişləri TOPLU oxunur
(item sayından asılı olmayan sabit sorğu sayı).
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import pgettext

from apps.exams.public import delivered_question_render

from ...constants import APPEAL_ITEM_STATUS_ACCEPTED, APPEAL_ITEM_STATUS_REJECTED
from ...models import AnswerKeyCorrection
from ...services.key_corrections import KEY_CORRECTION_MIN_REASON, key_option_choices


def _selected_ids(answer):
    if answer is None:
        return set()
    frozen = getattr(answer, "selected_option_ids_snapshot", None)
    if frozen is not None:
        return {int(option_id) for option_id in frozen}
    return {option.id for option in answer.selected_options.all()}


def _person(user):
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username()).strip()


def attach_item_comparison(items, *, is_test, can_decide):
    """Hər item-ə ``delivered`` (snapshot görünüşü), ``selected_option_ids``, açar düzəlişi məlumatı yaz."""
    question_ids = [item.question_id for item in items]
    corrections = list(
        AnswerKeyCorrection.objects.filter(question_id__in=question_ids)
        .select_related("created_by", "revoked_by")
        .order_by("created_at", "id")
    )
    by_question = {}
    for correction in corrections:
        by_question.setdefault(correction.question_id, []).append(correction)

    for item in items:
        answer = item.answer
        if answer is not None and answer.question_id == item.question_id:
            answer.question = item.question  # keşə qoy — snapshot görünüşü hər item üçün sual sorğusu etməsin (N+1)
        selected = _selected_ids(answer)
        item.selected_option_ids = selected if is_test else set()
        item.delivered = delivered_question_render(answer, selected) if answer is not None else None
        item.kc_history = by_question.get(item.question_id, [])
        active = next((c for c in item.kc_history if c.revoked_at is None), None)
        item.active_key_correction = active
        item.corrected_option_ids = set(active.corrected_option_ids or []) if active else set()
        for option in getattr(item.delivered, "options", None) or []:
            option.is_fixed_key = option.id in item.corrected_option_ids
        # Açar düzəlişi formu yalnız test sualında, qərar səlahiyyəti olanda və aktiv düzəliş yoxdursa.
        item.can_correct_key = bool(is_test and can_decide and active is None and answer is not None)
        item.key_choices = key_option_choices(answer, item.question) if item.can_correct_key else []
    return items


def appeal_timeline(appeal, items):
    """Apellyasiyanın xronoloji tarixçəsi — göndərilmə, sual-sual qərarlar, bal düzəlişləri, açar düzəlişləri."""
    events = [
        {
            "at": appeal.created_at,
            "icon": "fa-paper-plane",
            "text": pgettext("appeals.history", "Apellyasiya göndərildi ({count} sual)").format(count=len(items)),
            "actor": _person(appeal.student),
        }
    ]
    for index, item in enumerate(items, start=1):
        if item.resolved_at and item.status in (APPEAL_ITEM_STATUS_ACCEPTED, APPEAL_ITEM_STATUS_REJECTED):
            events.append(
                {
                    "at": item.resolved_at,
                    "icon": "fa-check" if item.status == APPEAL_ITEM_STATUS_ACCEPTED else "fa-xmark",
                    "text": pgettext("appeals.history", "{no}-ci sual: {status}").format(
                        no=index, status=item.get_status_display()
                    ),
                    "actor": _person(item.resolved_by),
                }
            )
        try:
            adjustment = item.score_adjustment
        except ObjectDoesNotExist:
            adjustment = None
        if adjustment is not None and adjustment.delta_points:
            events.append(
                {
                    "at": adjustment.applied_at,
                    "icon": "fa-rotate-left" if adjustment.reverted else "fa-plus",
                    "text": (
                        pgettext("appeals.history", "{no}-ci sual: bal düzəlişi geri alındı").format(no=index)
                        if adjustment.reverted
                        else pgettext("appeals.history", "{no}-ci sual: +{delta} bal").format(
                            no=index, delta=_points(adjustment.delta_points)
                        )
                    ),
                    "actor": _person(adjustment.applied_by),
                }
            )
        for correction in getattr(item, "kc_history", []):
            events.append(
                {
                    "at": correction.created_at,
                    "icon": "fa-key",
                    "text": pgettext(
                        "appeals.history",
                        "{no}-ci sual: cavab açarı düzəldildi — {credited}/{affected} tələbəyə kredit",
                    ).format(no=index, credited=correction.credited_count, affected=correction.affected_count),
                    "actor": _person(correction.created_by),
                }
            )
            if correction.revoked_at:
                events.append(
                    {
                        "at": correction.revoked_at,
                        "icon": "fa-rotate-left",
                        "text": pgettext("appeals.history", "{no}-ci sual: açar düzəlişi geri alındı").format(no=index),
                        "actor": _person(correction.revoked_by),
                    }
                )
    events.sort(key=lambda event: event["at"])
    return events


def _points(value):
    text = f"{value:.2f}"
    return text.rstrip("0").rstrip(".")


__all__ = ["KEY_CORRECTION_MIN_REASON", "appeal_timeline", "attach_item_comparison"]
