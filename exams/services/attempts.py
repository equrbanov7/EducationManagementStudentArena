from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from exams.models import Exam, ExamAttempt
from exams.services.randomizer import (build_shuffled_options,
                                       generate_random_questions_for_attempt)
from exams.services.utils import (_attempt_has_any_answer,
                                  _clear_paint_from_answer,
                                  _effective_needed_count,
                                  _save_paint_png_to_answer)


# / Bu funksiya yalnız müəllimlərin imtahan cəhdlərini idarə etməsi üçün istifadə olunur.
def _ensure_teacher(user):
    if not getattr(user, "is_teacher", False):
        raise PermissionDenied("Bu səhifə yalnız müəllimlər üçündür.")


# / Bu funksiya yalnız tələbələrin imtahan cəhdlərini idarə etməsi üçün istifadə olunur.
def _start_or_resume_attempt(request, exam: Exam):
    """
    İstifadəçi üçün attempt yaradır və ya mövcud attempt-ə yönləndirir.
    """
    user = request.user

    # ✅ DƏYİŞİKLİK: Bitməmiş attempt-i yoxla
    current = (
        exam.attempts.filter(user=user, status__in=["draft", "in_progress"])
        .order_by("-started_at")
        .first()
    )

    if current:
        # Suallar düzgün generate edilib?
        desired = _effective_needed_count(exam)
        current_count = current.answers.count()

        # Əgər sual sayı düzgün deyilsə və heç cavab yazılmayıbsa, yenidən generate et
        if current_count != desired and not _attempt_has_any_answer(current):
            generate_random_questions_for_attempt(current, force_rebuild=True)

        return redirect("exams:take_exam", slug=exam.slug, attempt_id=current.id)

    # ✅ Bitmiş cəhdləri yoxla
    finished_qs = exam.attempts.filter(
        user=user, status__in=["submitted", "expired"]
    ).order_by("-started_at")

    finished_count = finished_qs.count()

    # ✅ DƏYİŞİKLİK: Boş olduqda limitsiz cəhd
    max_attempts = exam.max_attempts_per_user

    # Əgər max_attempts təyin edilib VƏ limite çatılıbsa
    if max_attempts and finished_count >= max_attempts:
        last = finished_qs.first()
        if last:
            messages.info(
                request,
                f"Siz bu imtahana maksimum {max_attempts} dəfə cəhd edə bilərsiniz.",
            )
            return redirect("exams:exam_result", slug=exam.slug, attempt_id=last.id)
        return redirect("exams:student_exam_list")

    # ✅ DƏYİŞİKLİK: Attempt number-i düzgün hesabla
    # Bütün attemptlərdən (bitmiş və bitməmiş) ən böyük nömrəni tap
    last_attempt = exam.attempts.filter(user=user).order_by("-attempt_number").first()

    if last_attempt:
        next_attempt_number = last_attempt.attempt_number + 1
    else:
        next_attempt_number = 1

    # ✅ Yeni attempt yarat
    attempt = ExamAttempt.objects.create(
        user=user,
        exam=exam,
        attempt_number=next_attempt_number,
        status="in_progress",
    )

    # Sualları generate et
    generate_random_questions_for_attempt(attempt)

    messages.success(request, f"İmtahan başladı! (Cəhd #{next_attempt_number})")
    return redirect("exams:take_exam", slug=exam.slug, attempt_id=attempt.id)
