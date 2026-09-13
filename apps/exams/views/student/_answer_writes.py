"""Tələbə cavab yazıları — test (variant seçimi) və yazılı (mətn/fayl/rəsm).

Audit 2026-09-13: `attempts.py` 600-sətir qapısını keçdiyi üçün buraya
köçürüldü (davranış dəyişməyib; EX-07 düzəlişi `_save_written_answer_if_changed`-dədir).
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from apps.exams.models import ExamAnswerFile
from apps.exams.services.utils import _clear_paint_from_answer, _save_paint_png_to_answer
from apps.exams.validators import ALLOWED_EXTENSIONS as EXAM_ALLOWED_EXTENSIONS
from core.upload_security import randomize_uploaded_filename, validate_uploaded_file


def _valid_question_option_ids(question):
    return {option.id for option in question.options.all()}


def _correct_question_option_ids(question):
    return {option.id for option in question.options.all() if option.is_correct}


def _save_test_answer_if_changed(answer, question, selected_option_ids, current_selected_option_ids):
    valid_option_ids = _valid_question_option_ids(question)
    selected_option_ids = selected_option_ids & valid_option_ids

    if current_selected_option_ids != selected_option_ids:
        answer.selected_options.set(selected_option_ids)

    correct_option_ids = _correct_question_option_ids(question)
    next_is_correct = bool(correct_option_ids and selected_option_ids == correct_option_ids)
    update_fields = []

    # EXAM-P0-03: seçim ID-ləri cavabın özündə dondurulur ki, variant
    # redaktəsi (delete/recreate) M2M through sətirlərini silsə belə keçmiş
    # seçim və bal bərpa oluna bilsin.
    frozen_selection = sorted(selected_option_ids)
    if answer.selected_option_ids_snapshot != frozen_selection:
        answer.selected_option_ids_snapshot = frozen_selection
        update_fields.append("selected_option_ids_snapshot")

    if answer.text_answer:
        answer.text_answer = ""
        update_fields.append("text_answer")

    if answer.is_correct != next_is_correct:
        answer.is_correct = next_is_correct
        update_fields.append("is_correct")

    if (
        getattr(answer, "has_paint", False)
        or getattr(answer, "paint_image", None)
        or getattr(answer, "paint_data_url", None)
    ):
        _clear_paint_from_answer(answer)
        update_fields.extend(["has_paint", "paint_image", "paint_data_url", "paint_updated_at"])

    if update_fields:
        answer.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))


def _save_written_answer_if_changed(request, answer, question, *, allow_binary_uploads=True):
    update_fields = []
    text = request.POST.get(f"q_{question.id}", "").strip()
    if answer.text_answer != text:
        answer.text_answer = text
        update_fields.append("text_answer")
    if answer.is_correct:
        answer.is_correct = False
        update_fields.append("is_correct")

    if allow_binary_uploads:
        files = request.FILES.getlist(f"file_{question.id}[]")
        if len(files) > settings.EXAM_ANSWER_MAX_FILES_PER_QUESTION:
            raise ValidationError(
                pgettext("exams.view.validation", "Bir sual üçün maksimum {count} fayl yükləyə bilərsiniz.").format(
                    count=settings.EXAM_ANSWER_MAX_FILES_PER_QUESTION
                )
            )
        if files:
            # Audit 2026-09-13 EX-07 (P2): əvvəl köhnə fayllar silinir, sonra
            # validasiya gedirdi — rədd edilən `.exe` yükləməsi (400) tələbənin
            # əvvəlki düzgün fayllarını da aparırdı. İndi əvvəl HAMISI yoxlanır,
            # yalnız sonra əvəzləmə olur.
            for uploaded_file in files:
                validate_uploaded_file(
                    uploaded_file,
                    allowed_extensions=EXAM_ALLOWED_EXTENSIONS,
                    max_size_mb=settings.EXAM_ANSWER_FILE_MAX_SIZE_MB,
                )
            answer.files.all().delete()
            for uploaded_file in files:
                randomize_uploaded_filename(uploaded_file)
                ExamAnswerFile.objects.create(answer=answer, file=uploaded_file)

    if not allow_binary_uploads:
        if update_fields:
            answer.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))
        return

    paint_enabled = request.POST.get(f"paint_enabled_{question.id}") == "1"
    paint_clear = request.POST.get(f"paint_clear_{question.id}") == "1"
    paint_data_url = (request.POST.get(f"paint_data_{question.id}") or "").strip()

    if not question.paint_enabled_effective:
        if (
            getattr(answer, "has_paint", False)
            or getattr(answer, "paint_image", None)
            or getattr(answer, "paint_data_url", None)
        ):
            _clear_paint_from_answer(answer)
            update_fields.extend(["has_paint", "paint_image", "paint_data_url", "paint_updated_at"])
    elif paint_clear:
        _clear_paint_from_answer(answer)
        update_fields.extend(["has_paint", "paint_image", "paint_data_url", "paint_updated_at"])
    elif paint_enabled and paint_data_url.startswith("data:image/png;base64,"):
        if _save_paint_png_to_answer(answer, paint_data_url):
            update_fields.extend(["paint_image", "paint_updated_at", "has_paint", "paint_data_url"])
    elif not paint_enabled and (getattr(answer, "has_paint", False) or getattr(answer, "paint_image", None)):
        _clear_paint_from_answer(answer)
        update_fields.extend(["has_paint", "paint_image", "paint_data_url", "paint_updated_at"])

    if update_fields:
        answer.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))
