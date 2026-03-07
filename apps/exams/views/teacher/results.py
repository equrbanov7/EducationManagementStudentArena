import hashlib
from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_POST

from apps.courses.models import CourseMembership
from apps.exams.models import Exam, ExamAnswer, ExamAttempt
from apps.exams.services.attempts import _ensure_teacher
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.exams.views.shared.tenant import get_teacher_exam_or_404, tenant_scoped_exams
from core.permissions import request_has_permission


def _append_query_params(url, **params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    if not clean_params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(clean_params)}"


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

    parsed = urlsplit(raw_url)
    if parsed.netloc and parsed.netloc != request.get_host():
        return ""

    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def _resolve_profile_navigation(request, *, default_section="my-exams"):
    requested_profile_section = (request.GET.get("from_section") or "").strip()
    valid_profile_sections = {
        "my-exams",
        "assigned-exams",
        "profile-info",
        "my-courses",
        "assigned-courses",
        "courses",
        "pending-review",
        "review-results",
    }
    if requested_profile_section not in valid_profile_sections:
        requested_profile_section = default_section

    fallback_profile_return_url = f"{reverse('accounts:profile')}?section={requested_profile_section}"
    explicit_return_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    profile_return_url = explicit_return_url or fallback_profile_return_url

    navigation_params = {
        "from_section": requested_profile_section,
        "return_to": profile_return_url,
    }
    return profile_return_url, navigation_params


def _get_exam_for_results(request, slug):
    """
    Exam-i tapır: ya author, ya da kurs manager ola bilər.
    """
    qs = tenant_scoped_exams(request, Exam.objects.filter(slug=slug))
    exam = qs.first()
    if not exam:
        raise PermissionDenied

    if exam.author == request.user:
        return exam

    if exam.course:
        is_course_manager = exam.course.owner == request.user or CourseMembership.objects.filter(
            course=exam.course,
            user=request.user,
            role__in=["teacher", "assistant"],
        ).exists()
        if is_course_manager:
            return exam

    raise PermissionDenied


@login_required
def teacher_exam_results(request, slug):
    """
    Müəllim üçün imtahan nəticələri:
    - filter paneli (axtarış, status, yoxlanıb, tarix aralığı)
    - iştirakçı nəticələri cədvəli (checkbox ilə)
    - toplu silmə imkanı
    """
    _ensure_teacher(request.user)
    exam = _get_exam_for_results(request, slug)
    profile_return_url, navigation_params = _resolve_profile_navigation(request, default_section="my-exams")
    exam_navigation_query = urlencode(navigation_params)
    exam_detail_url = _append_query_params(
        reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
        **navigation_params,
    )

    # ---------- Filter parametrləri ----------
    search_query = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    checked_filter = (request.GET.get("checked") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    attempts = exam.attempts.select_related("user").order_by("-started_at")

    if search_query:
        attempts = attempts.filter(user__username__icontains=search_query)
    if status_filter in {"submitted", "expired"}:
        attempts = attempts.filter(status=status_filter)
    if checked_filter == "checked":
        attempts = attempts.filter(checked_by_teacher=True)
    elif checked_filter == "unchecked":
        attempts = attempts.filter(checked_by_teacher=False)
    if date_from:
        dt_from = parse_date(date_from)
        if dt_from:
            attempts = attempts.filter(started_at__date__gte=dt_from)
    if date_to:
        dt_to = parse_date(date_to)
        if dt_to:
            attempts = attempts.filter(started_at__date__lte=dt_to)

    selected_attempt = None
    selected_answers = None

    # ---------- POST: müəllim bal + feedback saxlayır ----------
    if request.method == "POST":
        if not request_has_permission(request, "grade.input"):
            messages.error(
                request,
                pgettext_lazy("exams.view.results.message", "grading_permission_required"),
            )
            return redirect(request.path)

        attempt_id = request.POST.get("attempt_id")
        score_raw = request.POST.get("teacher_score", "").strip()
        feedback = request.POST.get("teacher_feedback", "").strip()

        selected_attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)

        if score_raw:
            try:
                score_val = int(score_raw)
            except ValueError:
                messages.error(request, pgettext_lazy("exams.view.results.message", "score_must_be_integer"))
            else:
                if 0 <= score_val <= 100:
                    selected_attempt.teacher_score = score_val
                    selected_attempt.teacher_feedback = feedback
                    selected_attempt.mark_checked()
                    messages.success(request, pgettext_lazy("exams.view.results.message", "score_feedback_saved"))
                    return redirect(
                        _append_query_params(
                            request.path,
                            attempt=selected_attempt.id,
                            **navigation_params,
                        )
                    )
                else:
                    messages.error(request, pgettext_lazy("exams.view.results.message", "score_range_0_100"))
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
            messages.success(request, pgettext_lazy("exams.view.results.message", "feedback_saved"))
            return redirect(
                _append_query_params(
                    request.path,
                    attempt=selected_attempt.id,
                    **navigation_params,
                )
            )

    # ---------- GET: hansı attempt seçilib? ----------
    if selected_attempt is None:
        attempt_param = request.GET.get("attempt")
        if attempt_param:
            selected_attempt = exam.attempts.filter(id=attempt_param).select_related("user").first()

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
        anonymous_name = pgettext("exams.view.results.label", "anonymous_student").format(code=hash_digest[:6].upper())

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
    fastest_attempts = sorted([a for a in attempts if a.duration_seconds], key=lambda a: a.duration_seconds)[:5]

    questions = exam.questions.all()
    hardest_questions = sorted(questions, key=lambda q: q.correct_ratio)[:5]

    return render(
        request,
        "exams/teacher/teacher_exam_results.html",
        {
            "exam": exam,
            "attempts": attempts,
            "attempts_data": attempts_data,
            "fastest_attempts": fastest_attempts,
            "hardest_questions": hardest_questions,
            "selected_attempt": selected_attempt,
            "selected_answers": selected_answers,
            "profile_return_url": profile_return_url,
            "exam_detail_url": exam_detail_url,
            "exam_navigation_query": exam_navigation_query,
            # Filter values for form re-population
            "filter_q": search_query,
            "filter_status": status_filter,
            "filter_checked": checked_filter,
            "filter_date_from": date_from,
            "filter_date_to": date_to,
            "has_active_filters": any([search_query, status_filter, checked_filter, date_from, date_to]),
        },
    )


@login_required
@require_POST
def bulk_delete_attempts(request, slug):
    """
    Seçilmiş cəhdləri toplu silir.
    POST body: attempt_ids (vergüllə ayrılmış ID-lər)
    """
    _ensure_teacher(request.user)
    exam = _get_exam_for_results(request, slug)

    raw_ids = request.POST.get("attempt_ids", "")
    ids_to_delete = []
    for x in raw_ids.split(","):
        x = x.strip()
        if x.isdigit():
            try:
                ids_to_delete.append(int(x))
            except ValueError:
                pass

    if not ids_to_delete:
        messages.warning(request, pgettext_lazy("exams.view.results.message", "no_attempts_selected"))
        return redirect("exams:teacher_exam_results", slug=exam.slug)

    deleted_count, _ = ExamAttempt.objects.filter(exam=exam, id__in=ids_to_delete).delete()
    messages.success(
        request,
        pgettext("exams.view.results.message", "attempts_deleted").format(count=deleted_count),
    )
    return redirect("exams:teacher_exam_results", slug=exam.slug)


@login_required
def teacher_view_attempt(request, slug, attempt_id):
    """
    ✅ Müəllim cavabları YALNIZ GÖRMƏK üçün (bal verə bilməz)
    Test və Yazılı hər ikisi üçün işləyir
    """
    _ensure_teacher(request.user)

    exam = get_teacher_exam_or_404(request, slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)
    profile_return_url, navigation_params = _resolve_profile_navigation(request, default_section="my-exams")

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

    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        search_token = search_query.lower()
        filtered = []
        for item in qa_list:
            question = item["question"]
            answer = item["answer"]
            question_text = (question.text or "").lower()
            answer_text = (getattr(answer, "text_answer", "") or "").lower()
            options_text = " ".join(opt.text for opt in question.options.all()).lower()
            if (
                search_token in question_text
                or search_token in answer_text
                or search_token in options_text
            ):
                filtered.append(item)
        qa_list = filtered

    questions_page = Paginator(qa_list, 6).get_page(request.GET.get("questions_page"))
    pagination_query = urlencode(
        {
            **navigation_params,
            "q": search_query,
        }
    )
    clear_search_url = _append_query_params(request.path, **navigation_params)

    context = {
        "exam": exam,
        "attempt": attempt,
        "qa_list": questions_page.object_list,
        "qa_page": questions_page,
        "qa_search_query": search_query,
        "qa_pagination_query": pagination_query,
        "qa_clear_search_url": clear_search_url,
        "read_only": True,  # ✅ Yalnız oxumaq rejimi
        "profile_return_url": profile_return_url,
    }

    return render(request, "exams/teacher/teacher_view_attempt.html", context)


@login_required
def teacher_check_attempt(request, slug, attempt_id):
    """
    Müəllim yazılı/praktiki imtahandakı BİR cəhdi sual-sual yoxlayır.

    ✅ MÜDAFİƏ: 5 dəqiqə keçibsə, yalnız oxumaq üçün yönləndir
    """
    _ensure_teacher(request.user)

    exam = get_teacher_exam_or_404(request, slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)
    profile_return_url, navigation_params = _resolve_profile_navigation(request, default_section="my-exams")
    results_return_url = _append_query_params(
        reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}),
        **navigation_params,
    )
    view_attempt_url = _append_query_params(
        reverse("exams:teacher_view_attempt", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
        **navigation_params,
    )

    # ✅ 5 dəqiqə keçibsə, yalnız "bax" səhifəsinə yönləndir
    if attempt.checked_by_teacher and attempt.teacher_checked_at:

        minutes_passed = int((timezone.now() - attempt.teacher_checked_at).total_seconds() / 60)

        if minutes_passed >= 5:
            messages.warning(
                request,
                pgettext_lazy("exams.view.results.message", "cannot_edit_after_five_minutes"),
            )
            return redirect(view_attempt_url)

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
        if not request_has_permission(request, "grade.input"):
            messages.error(
                request,
                pgettext_lazy("exams.view.results.message", "grading_permission_required"),
            )
            return redirect(view_attempt_url)

        # ✅ DOUBLE-CHECK: POST zamanı da yoxla
        if attempt.checked_by_teacher and attempt.teacher_checked_at:
            minutes_passed = int((timezone.now() - attempt.teacher_checked_at).total_seconds() / 60)

            if minutes_passed >= 5:
                messages.error(
                    request,
                    pgettext_lazy("exams.view.results.message", "cannot_edit_after_five_minutes"),
                )
                return redirect(view_attempt_url)

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

        # İlk yoxlama vaxtını saxla; 5 dəqiqəlik redaktə pəncərəsi bu vaxtdan hesablanır.
        attempt.teacher_score = total_score if any_score else None
        attempt.checked_by_teacher = True
        if not attempt.teacher_checked_at:
            attempt.teacher_checked_at = timezone.now()
        attempt.save(update_fields=["teacher_score", "checked_by_teacher", "teacher_checked_at"])

        messages.success(request, pgettext_lazy("exams.view.results.message", "attempt_checked_success"))
        return redirect(results_return_url)

    context = {
        "exam": exam,
        "attempt": attempt,
        "qa_list": qa_list,
        "profile_return_url": profile_return_url,
        "results_return_url": results_return_url,
    }
    return render(request, "exams/teacher/teacher_check_attempt.html", context)


@login_required
def teacher_pending_attempts(request):
    """
    Müəllimin bütün imtahanlarından yığılmış,
    yoxlanılmağı gözləyən (Pending) işlərin siyahısı.
    """
    _ensure_teacher(request.user)

    teacher_exams = tenant_scoped_exams(request, request.user.exams.all())

    # Yoxlanılacaq işləri tapırıq
    pending_attempts = (
        ExamAttempt.objects.filter(
            exam__in=teacher_exams,  # Bu müəllimin aktiv tenant imtahanları
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
        anonymous_name = pgettext("exams.view.results.label", "anonymous_student").format(code=hash_digest[:6].upper())

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
