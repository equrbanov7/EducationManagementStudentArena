"""teacher questions paketi — crud."""

import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.exams.forms import ExamQuestionCreateForm
from apps.exams.models import ExamQuestion
from apps.exams.services.access_policy import _ensure_teacher, ensure_can_manage_exam_questions
from apps.exams.services.coding_definition import ensure_coding_question_for_exam_question
from apps.exams.services.language_variants import ensure_default_variant
from apps.exams.views.shared.tenant import get_teacher_exam_or_404

from ._shared import (
    _append_navigation_query,
    _is_question_modal_request,
    _question_form_blocks,
    _question_post_data_with_default_block,
    _render_question_form_html,
    _resequence_exam_questions,
    _resolve_question_bank_navigation,
)

logger = logging.getLogger(__name__)


@login_required
def add_exam_question(request, slug):
    """
    Müəllim imtahana sual əlavə edir.
    Test imtahanı üçün variantlar da eyni formda daxil olunur.
    Yazılı imtahan üçün yalnız sual mətni + ideal cavab hissəsi istifadə edilir.
    """
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    ensure_can_manage_exam_questions(request.user, exam)
    blocks, created_default_block = _question_form_blocks(exam)
    is_modal_request = _is_question_modal_request(request)
    _, _, navigation_query = _resolve_question_bank_navigation(request)

    if request.method == "POST":
        form = ExamQuestionCreateForm(
            _question_post_data_with_default_block(request, created_default_block),
            request.FILES,
            exam_type=exam.exam_type,
            subject_blocks=blocks,
            exam=exam,
        )
        if form.is_valid():
            # Sualı yaradıq
            last_q = exam.questions.order_by("-order").first()
            next_order = (last_q.order + 1) if last_q else 1

            question = form.save(commit=False)
            question.exam = exam
            question.order = next_order

            # Seçilmiş dilin variantını təmin et (çoxdilli imtahan + student dil axını).
            question.language_variant = ensure_default_variant(exam, question.language)

            # Yazılı/praktiki imtahan üçün answer_mode-u zorla "single" edə bilərik
            if exam.exam_type in {"written", "coding"}:
                question.answer_mode = "single"
                if exam.exam_type == "written":
                    question.set_paint_enabled(form.cleaned_data.get("enable_paint"))

            question.save()
            if exam.exam_type == "coding":
                ensure_coding_question_for_exam_question(question, sync_existing=True)

            # Invalidate the cached question ID list so live sessions see the change.
            try:
                from core.cache import invalidate_exam_question_ids_cache

                invalidate_exam_question_ids_cache(exam.pk)
            except Exception:
                # Best-effort: the cached ID list self-heals on its next TTL, so
                # a cache failure must not break question creation — but log it.
                logger.warning(
                    "Exam question-ids cache invalidation failed for exam %s",
                    exam.pk,
                    exc_info=True,
                )

            # Əgər exam tipi testdirsə → variantları yarat
            if exam.exam_type == "test":
                form.create_options(question)

            from apps.exams.services.difficulty import schedule_ai_question_difficulty_warmup

            schedule_ai_question_difficulty_warmup(exam, force=True)

            if is_modal_request:
                return JsonResponse({"success": True, "question_id": question.id})

            # hansı düyməyə basıldığını yoxlayaq
            if "save_and_continue" in request.POST:
                # eyni imtahan üçün yenidən boş formada aç
                return redirect(
                    _append_navigation_query(
                        reverse("exams:add_exam_question", kwargs={"slug": exam.slug}), navigation_query
                    )
                )
            else:
                # Sadəcə imtahan detalına qayıt
                return redirect(
                    _append_navigation_query(
                        reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
                        navigation_query,
                    )
                )
        if is_modal_request:
            return JsonResponse(
                {
                    "success": False,
                    "html": _render_question_form_html(
                        request,
                        exam=exam,
                        form=form,
                        editing=False,
                        navigation_query=navigation_query,
                    ),
                },
                status=400,
            )
    else:
        form = ExamQuestionCreateForm(exam_type=exam.exam_type, subject_blocks=blocks, exam=exam)

    if is_modal_request:
        return render(
            request,
            "exams/teacher/partials/_question_form.html",
            {
                "exam": exam,
                "form": form,
                "editing": False,
                "is_modal": True,
                "question_navigation_query": navigation_query,
            },
        )

    return render(
        request,
        "exams/teacher/add_exam_question.html",
        {
            "exam": exam,
            "form": form,
            "editing": False,
            "is_modal": False,
            "question_navigation_query": navigation_query,
        },
    )


@login_required
def edit_exam_question(request, slug, question_id):
    """
    Mövcud sualı redaktə etmək (text, blok, cavab rejimi, vaxt, variantlar və s.).
    """
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    ensure_can_manage_exam_questions(request.user, exam)
    question = get_object_or_404(ExamQuestion, id=question_id, exam=exam)
    is_modal_request = _is_question_modal_request(request)
    _, _, navigation_query = _resolve_question_bank_navigation(request)

    blocks, created_default_block = _question_form_blocks(exam)

    if request.method == "POST":
        form = ExamQuestionCreateForm(
            _question_post_data_with_default_block(request, created_default_block),
            request.FILES,
            instance=question,
            exam_type=exam.exam_type,
            exam=exam,
            subject_blocks=blocks,  # <--- Vacib: Blokları formaya ötürürük
        )
        if form.is_valid():
            q = form.save(commit=False)
            q.exam = exam

            # Seçilmiş dilin variantını təmin et (çoxdilli imtahan).
            q.language_variant = ensure_default_variant(exam, q.language)

            if exam.exam_type in {"written", "coding"}:
                q.answer_mode = "single"
                if exam.exam_type == "written":
                    q.set_paint_enabled(form.cleaned_data.get("enable_paint"))

            q.save()
            if exam.exam_type == "coding":
                ensure_coding_question_for_exam_question(q, sync_existing=True)

            if exam.exam_type == "test":
                form.save_options(q)

            from apps.exams.services.difficulty import schedule_ai_question_difficulty_warmup

            schedule_ai_question_difficulty_warmup(exam, force=True)

            if is_modal_request:
                return JsonResponse({"success": True, "question_id": q.id})

            if "save_and_continue" in request.POST:
                return redirect(
                    _append_navigation_query(
                        reverse("exams:add_exam_question", kwargs={"slug": exam.slug}), navigation_query
                    )
                )

            return redirect(
                _append_navigation_query(
                    reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
                    navigation_query,
                )
            )
        if is_modal_request:
            return JsonResponse(
                {
                    "success": False,
                    "html": _render_question_form_html(
                        request,
                        exam=exam,
                        form=form,
                        editing=True,
                        question=question,
                        navigation_query=navigation_query,
                    ),
                },
                status=400,
            )
    else:
        form = ExamQuestionCreateForm(
            instance=question,
            exam_type=exam.exam_type,
            exam=exam,
            subject_blocks=blocks,  # <--- Vacib: Blokları formaya ötürürük
        )

    if is_modal_request:
        return render(
            request,
            "exams/teacher/partials/_question_form.html",
            {
                "exam": exam,
                "form": form,
                "editing": True,
                "question": question,
                "is_modal": True,
                "question_navigation_query": navigation_query,
            },
        )

    return render(
        request,
        "exams/teacher/add_exam_question.html",
        {
            "exam": exam,
            "form": form,
            "editing": True,
            "question": question,
            "is_modal": False,
            "question_navigation_query": navigation_query,
        },
    )


@login_required
def delete_exam_question(request, slug, question_id):
    """
    Sualı silmək – əvvəlcə təsdiq istənilir.
    """
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    ensure_can_manage_exam_questions(request.user, exam)
    question = get_object_or_404(ExamQuestion, id=question_id, exam=exam)
    _, _, navigation_query = _resolve_question_bank_navigation(request)

    if request.method == "POST":
        with transaction.atomic():
            question.delete()
            _resequence_exam_questions(exam)
        # Invalidate the cached question ID list for this exam.
        try:
            from core.cache import invalidate_exam_question_ids_cache

            invalidate_exam_question_ids_cache(exam.pk)
        except Exception:
            # Best-effort: the cached ID list self-heals on its next TTL, so a
            # cache failure must not break question deletion — but log it.
            logger.warning(
                "Exam question-ids cache invalidation failed for exam %s",
                exam.pk,
                exc_info=True,
            )
        return redirect(
            _append_navigation_query(
                reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
                navigation_query,
            )
        )

    return render(
        request,
        "exams/teacher/confirm_delete_question.html",
        {
            "exam": exam,
            "question": question,
        },
    )
