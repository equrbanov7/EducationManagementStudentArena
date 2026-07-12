"""Strict timed-question content üçün təhlükəsiz render proyeksiyası."""

import random
from types import SimpleNamespace

from django.core.files.storage import default_storage

from apps.exams.constants import LABELS
from apps.exams.services.question_snapshot import delivered_question_view


def _storage_url(name):
    if not name:
        return ""
    try:
        return default_storage.url(name)
    except (ValueError, NotImplementedError):
        return ""


def delivered_selected_option_ids(answer) -> set[int]:
    """Dondurulmuş seçim varsa onu, legacy cavabda canlı M2M-i qaytar."""
    frozen = getattr(answer, "selected_option_ids_snapshot", None)
    if isinstance(frozen, list):
        selected = set()
        for raw_id in frozen:
            try:
                selected.add(int(raw_id))
            except (TypeError, ValueError):
                continue
        return selected
    return {option.id for option in answer.selected_options.all()}


def safe_delivered_question(answer):
    """Template-ə düzgün cavab metadatası daxil etməyən snapshot proyeksiyası.

    ``delivered_question_view`` daxildə ``correct_answer``/``is_correct`` də
    saxlayır (nəticə hesablanması üçün). Bu funksiya həmin sahələri qəsdən
    çıxarır; question-delivery JSON-u yalnız tələbəyə göstərilə bilən məzmunu
    alır.
    """
    delivered = delivered_question_view(answer)
    selected_ids = delivered_selected_option_ids(answer)
    options = list(delivered.get("options") or [])
    random.Random(f"{answer.attempt_id}:{answer.question_id}").shuffle(options)  # nosec B311

    safe_options = []
    for index, option in enumerate(options):
        try:
            option_id = int(option.get("id"))
        except (TypeError, ValueError):
            continue
        safe_options.append(
            SimpleNamespace(
                id=option_id,
                label=LABELS[index] if index < len(LABELS) else "",
                text=option.get("text", "") or "",
                image_url=_storage_url(option.get("image", "")),
                is_selected=option_id in selected_ids,
            )
        )

    return SimpleNamespace(
        text=delivered.get("text", "") or "",
        image_url=_storage_url(delivered.get("image", "")),
        video_url=_storage_url(delivered.get("video", "")),
        answer_mode=delivered.get("answer_mode", "") or "",
        options=safe_options,
    )


__all__ = ["delivered_selected_option_ids", "safe_delivered_question"]
