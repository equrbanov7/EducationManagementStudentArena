import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.exams.models import Exam, ExamAnswer, ExamAttempt
from apps.exams.services.attempts import _ensure_teacher
from apps.exams.services.randomizer import generate_random_questions_for_attempt


@login_required
def teacher_exam_results(request, slug):
    """
    Müəllim üçün imtahan nəticələri:
    - solda bütün cəhdlər cədvəli
    - aşağıda/sağda seçilmiş cəhdin cavabları + qiymətləndirmə formu
    """
    _ensure_teacher(request.user)
    exam = get_object_or_404(Exam, slug=slug, author=request.user)

    attempts = exam.attempts.select_related("user").order_by("-started_at")

    selected_attempt = None
    selected_answers = None

    # ---------- POST: müəllim bal + feedback saxlayır ----------
    if request.method == "POST":
        attempt_id = request.POST.get("attempt_id")
        score_raw = request.POST.get("teacher_score", "").strip()
        feedback = request.POST.get("teacher_feedback", "").strip()

        selected_attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)

        if score_raw:
            try:
                score_val = int(score_raw)
            except ValueError:
                messages.error(request, "Bal tam ədəd olmalıdır.")
            else:
                if 0 <= score_val <= 100:
                    selected_attempt.teacher_score = score_val
                    selected_attempt.teacher_feedback = feedback
                    selected_attempt.mark_checked()
                    messages.success(request, "Bal və rəy yadda saxlanıldı.")
                    # yenidən eyni attempt seçilmiş halda geri dön
                    return redirect(f"{request.path}?attempt={selected_attempt.id}")
                else:
                    messages.error(request, "Bal 0–100 aralığında olmalıdır.")
        else:
            # yalnız feedback saxlanılır
            selected_attempt.teacher_score = None
            selected_attempt.teacher_feedback = feedback
            selected_attempt.checked_by_teacher = False
            selected_attempt.save(
                update_fields=[
                    "teacher_score",
                    "teacher_feedback",
                    "checked_by_teacher",
                ]
            )
            messages.success(request, "Rəy yadda saxlanıldı.")
            return redirect(f"{request.path}?attempt={selected_attempt.id}")

    # ---------- GET: hansı attempt seçilib? ----------
    if selected_attempt is None:
        attempt_param = request.GET.get("attempt")
        if attempt_param:
            selected_attempt = (
                exam.attempts.filter(id=attempt_param).select_related("user").first()
            )

    if selected_attempt:
        selected_answers = (
            ExamAnswer.objects.filter(attempt=selected_attempt)
            .select_related("question")
            .order_by("question__order", "question__id")
        )

    now = timezone.now()
    attempts_data = []

    for att in attempts:
        # Anonim ad (deterministic)
        hash_input = f"{att.id}-{att.user.id}-{exam.id}"
        hash_digest = hashlib.md5(hash_input.encode()).hexdigest()
        anonymous_name = f"Tələbə #{hash_digest[:6].upper()}"

        # Vaxt hesablamaları
        seconds_remaining = None
        can_view_name = False

        if att.checked_by_teacher and att.teacher_checked_at:
            diff = now - att.teacher_checked_at
            total_seconds_passed = int(diff.total_seconds())

            if total_seconds_passed < 300:  # 5 dəqiqə = 300 saniyə
                seconds_remaining = 300 - total_seconds_passed
                can_view_name = False  # Ad gizli
            else:
                can_view_name = True  # 5+ dəqiqə - ad görünür

        attempts_data.append(
            {
                "attempt": att,
                "anonymous_name": anonymous_name,
                "real_name": att.user.username,
                "can_view_name": can_view_name,
                "seconds_remaining": seconds_remaining,
            }
        )

    # ═══════════════════════════════════════════════════════════════════
    # Statistikalar (əvvəlki kimi)
    # ═══════════════════════════════════════════════════════════════════
    fastest_attempts = sorted(
        [a for a in attempts if a.duration_seconds], key=lambda a: a.duration_seconds
    )[:5]

    questions = exam.questions.all()
    hardest_questions = sorted(questions, key=lambda q: q.correct_ratio)[:5]

    return render(
        request,
        "exams/teacher/teacher_exam_results.html",
        {
            "exam": exam,
            "attempts": attempts,
            "attempts_data": attempts_data,  # ✅ YENİ
            "fastest_attempts": fastest_attempts,
            "hardest_questions": hardest_questions,
            "selected_attempt": selected_attempt,
            "selected_answers": selected_answers,
        },
    )


@login_required
def teacher_view_attempt(request, slug, attempt_id):
    """
    ✅ Müəllim cavabları YALNIZ GÖRMƏK üçün (bal verə bilməz)
    Test və Yazılı hər ikisi üçün işləyir
    """
    _ensure_teacher(request.user)

    exam = get_object_or_404(Exam, slug=slug, author=request.user)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)

    # Cavabları al
    answers_qs = (
        attempt.answers.select_related("question")
        .prefetch_related("files", "selected_options", "question__options")
        .order_by("id")
    )

    if not answers_qs.exists():
        generate_random_questions_for_attempt(attempt)
        answers_qs = (
            attempt.answers.select_related("question")
            .prefetch_related("files", "selected_options", "question__options")
            .order_by("id")
        )

    qa_list = [{"question": a.question, "answer": a} for a in answers_qs]

    context = {
        "exam": exam,
        "attempt": attempt,
        "qa_list": qa_list,
        "read_only": True,  # ✅ Yalnız oxumaq rejimi
    }

    return render(request, "exams/teacher/teacher_view_attempt.html", context)


@login_required
def teacher_check_attempt(request, slug, attempt_id):
    """
    Müəllim yazılı/praktiki imtahandakı BİR cəhdi sual-sual yoxlayır.

    ✅ MÜDAFİƏ: 5 dəqiqə keçibsə, yalnız oxumaq üçün yönləndir
    """
    _ensure_teacher(request.user)

    exam = get_object_or_404(Exam, slug=slug, author=request.user)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)

    # ✅ 5 dəqiqə keçibsə, yalnız "bax" səhifəsinə yönləndir
    if attempt.checked_by_teacher and attempt.teacher_checked_at:

        minutes_passed = int(
            (timezone.now() - attempt.teacher_checked_at).total_seconds() / 60
        )

        if minutes_passed >= 5:
            messages.warning(
                request, "5 dəqiqə keçdiyindən bu cavabı artıq dəyişə bilməzsiniz."
            )
            return redirect(
                "exams:teacher_view_attempt", slug=exam.slug, attempt_id=attempt.id
            )

    # YALNIZ bu attempt-ə düşən suallar
    answers_qs = (
        attempt.answers.select_related("question")
        .prefetch_related("files", "selected_options", "question__options")
        .order_by("id")
    )

    if not answers_qs.exists():
        generate_random_questions_for_attempt(attempt)
        answers_qs = (
            attempt.answers.select_related("question")
            .prefetch_related("files", "selected_options", "question__options")
            .order_by("id")
        )

    qa_list = [{"question": a.question, "answer": a} for a in answers_qs]

    if request.method == "POST":
        # ✅ DOUBLE-CHECK: POST zamanı da yoxla
        if attempt.checked_by_teacher and attempt.teacher_checked_at:
            minutes_passed = int(
                (timezone.now() - attempt.teacher_checked_at).total_seconds() / 60
            )

            if minutes_passed >= 5:
                messages.error(
                    request, "5 dəqiqə keçdiyindən bu cavabı artıq dəyişə bilməzsiniz."
                )
                return redirect(
                    "exams:teacher_view_attempt", slug=exam.slug, attempt_id=attempt.id
                )

        total_score = 0
        any_score = False

        for a in answers_qs:
            q = a.question

            score_raw = (request.POST.get(f"score_{q.id}") or "").strip()
            feedback = (request.POST.get(f"feedback_{q.id}") or "").strip()

            if score_raw == "":
                a.teacher_score = None
            else:
                try:
                    score_val = int(score_raw)
                except ValueError:
                    score_val = 0
                a.teacher_score = score_val
                total_score += score_val
                any_score = True

            a.teacher_feedback = feedback
            a.save(update_fields=["teacher_score", "teacher_feedback", "updated_at"])

        # ✅ Tarix yenilənir (hər dəyişiklikdə)
        attempt.teacher_score = total_score if any_score else None
        attempt.checked_by_teacher = True
        attempt.teacher_checked_at = timezone.now()  # ✅ Hər dəyişiklikdə yenilənir
        attempt.save(
            update_fields=["teacher_score", "checked_by_teacher", "teacher_checked_at"]
        )

        messages.success(request, "İmtahan cəhdi uğurla yoxlanıldı.")
        return redirect("exams:teacher_exam_results", slug=exam.slug)

    context = {
        "exam": exam,
        "attempt": attempt,
        "qa_list": qa_list,
    }
    return render(request, "exams/teacher/teacher_check_attempt.html", context)


@login_required
def teacher_pending_attempts(request):
    """
    Müəllimin bütün imtahanlarından yığılmış,
    yoxlanılmağı gözləyən (Pending) işlərin siyahısı.
    """
    # Yalnız müəllimlər görə bilsin
    if not getattr(request.user, "is_teacher", False):
        return render(request, "403_forbidden.html")

    # Yoxlanılacaq işləri tapırıq
    pending_attempts = (
        ExamAttempt.objects.filter(
            exam__author=request.user,  # Bu müəllimin imtahanları
            status__in=["submitted", "expired"],  # Bitmiş imtahanlar
            checked_by_teacher=False,  # Hələ yoxlanmayıb
        )
        .exclude(exam__exam_type="test")  # Testləri çıxarırıq
        .select_related("user", "exam")
        .order_by("finished_at")
    )

    now = timezone.now()
    attempts_data = []

    for att in pending_attempts:
        # Anonim ad (deterministic)
        hash_input = f"{att.id}-{att.user.id}-{att.exam.id}"
        hash_digest = hashlib.md5(hash_input.encode()).hexdigest()
        anonymous_name = f"Tələbə #{hash_digest[:6].upper()}"

        # Vaxt hesablamaları
        seconds_remaining = None
        can_view_name = False

        if att.checked_by_teacher and att.teacher_checked_at:
            diff = now - att.teacher_checked_at
            total_seconds_passed = int(diff.total_seconds())

            if total_seconds_passed < 300:  # 5 dəqiqə = 300 saniyə
                seconds_remaining = 300 - total_seconds_passed
                can_view_name = False  # Ad gizli
            else:
                can_view_name = True  # 5+ dəqiqə - ad görünür

        attempts_data.append(
            {
                "attempt": att,
                "anonymous_name": anonymous_name,
                "real_name": att.user.username,
                "can_view_name": can_view_name,
                "seconds_remaining": seconds_remaining,
            }
        )

    # ═══════════════════════════════════════════════════════════════════
    # ✅ YENİ: Tip üzrə saylar (Yazılı və Test)
    # ═══════════════════════════════════════════════════════════════════
    essay_count = sum(1 for att in pending_attempts if att.exam.exam_type == "written")
    test_count = sum(1 for att in pending_attempts if att.exam.exam_type == "test")

    context = {
        "pending_attempts": pending_attempts,
        "attempts_data": attempts_data,  # ✅ YENİ - anonim adlar
        "essay_count": essay_count,  # ✅ YENİ - yazılı say
        "test_count": test_count,  # ✅ YENİ - test say
    }
    return render(request, "exams/teacher/teacher_pending_attempts.html", context)
