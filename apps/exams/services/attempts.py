from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.exams.services.utils import _attempt_has_any_answer, _effective_needed_count


# / Bu funksiya yalnız müəllimlərin imtahan cəhdlərini idarə etməsi üçün istifadə olunur.
def _ensure_teacher(user):
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return

    has_teacher_role = False
    if hasattr(user, "has_role"):
        has_teacher_role = user.has_role(ProfileRole.TEACHER) or user.has_role(ProfileRole.ASSISTANT_TEACHER)
    if not has_teacher_role:
        profile = getattr(user, "profile", None)
        role = getattr(profile, "role", None)
        has_teacher_role = role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}

    if not has_teacher_role:
        raise PermissionDenied(pgettext("exams.service.attempt.permission", "teachers_only_page"))


def _safe_same_origin_redirect_path(request, candidate_url):
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""
    return raw_url


def _append_return_to(url, return_to):
    if not return_to:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'return_to': return_to})}"


def _build_exam_result_url(exam, attempt, return_to):
    return _append_return_to(
        reverse("exams:exam_result", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
        return_to,
    )


# / Bu funksiya yalnız tələbələrin imtahan cəhdlərini idarə etməsi üçün istifadə olunur.
def _start_or_resume_attempt(request, exam: Exam):
    """
    İstifadəçi üçün attempt yaradır və ya mövcud attempt-ə yönləndirir.
    """
    user = request.user
    return_to = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next") or request.POST.get("return_to") or request.POST.get("next"),
    )

    # ✅ DƏYİŞİKLİK: Bitməmiş attempt-i yoxla
    current = exam.attempts.filter(user=user, status__in=["draft", "in_progress"]).order_by("-started_at").first()

    if current:
        # Suallar düzgün generate edilib?
        desired = _effective_needed_count(exam)
        current_count = current.answers.count()

        # Əgər sual sayı düzgün deyilsə və heç cavab yazılmayıbsa, yenidən generate et
        if current_count != desired and not _attempt_has_any_answer(current):
            generate_random_questions_for_attempt(current, force_rebuild=True)

        return redirect(_append_return_to(reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": current.id}), return_to))

    # ✅ Bitmiş cəhdləri yoxla
    finished_qs = exam.attempts.filter(user=user, status__in=["submitted", "expired"]).order_by("-started_at")

    finished_count = finished_qs.count()

    # ✅ DƏYİŞİKLİK: Boş olduqda limitsiz cəhd
    max_attempts = exam.max_attempts_per_user

    # Əgər max_attempts təyin edilib VƏ limite çatılıbsa
    if max_attempts and finished_count >= max_attempts:
        last = finished_qs.first()
        if last:
            messages.info(
                request,
                pgettext("exams.service.attempt.message", "max_attempts_reached").format(max_attempts=max_attempts),
            )
            return redirect(_build_exam_result_url(exam, last, return_to))
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

    messages.success(
        request,
        pgettext("exams.service.attempt.message", "exam_started").format(attempt_number=next_attempt_number),
    )
    return redirect(_append_return_to(reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id}), return_to))
