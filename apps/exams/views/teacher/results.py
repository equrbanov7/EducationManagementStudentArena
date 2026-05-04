import json
from datetime import datetime
from urllib.parse import urlencode, urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_http_methods

from apps.exams.models import ExamAnswer, ExamAttempt
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.ai_grading import has_ai_gradeable_answer_content, has_written_answer_content
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.exams.services.review_visibility import attempt_review_window_locked as _attempt_review_window_locked
from apps.exams.services.review_visibility import (
    resolve_exam_attempt_name_visibility as _resolve_attempt_name_visibility,
)
from apps.exams.services.review_visibility import (
    resolve_exam_attempt_review_window_seconds as _resolve_attempt_review_window_seconds,
)
from apps.exams.views.shared.tenant import get_teacher_exam_or_404, tenant_scoped_exams
from core.permissions import request_has_permission

ANONYMOUS_NAME_TOKEN_SALT = "exams.teacher_results.anonymous_name"  # nosec B105
ANONYMOUS_NAME_CODE_LENGTH = 6


def _build_answer_review_item(answer):
    answer_files = list(answer.files.all())
    has_text_answer = bool((getattr(answer, "text_answer", "") or "").strip())
    has_paint_answer = bool(getattr(answer, "paint_image", None)) or bool(getattr(answer, "has_paint", False))
    has_file_answer = bool(answer_files)
    has_answer_content = has_written_answer_content(
        student_answer=answer.text_answer,
        answer_files=answer_files,
        paint_image=getattr(answer, "paint_image", None),
    )

    return {
        "question": answer.question,
        "answer": answer,
        "answer_files": answer_files,
        "has_text_answer": has_text_answer,
        "has_paint_answer": has_paint_answer,
        "has_file_answer": has_file_answer,
        "has_answer_content": has_answer_content,
        "has_ai_gradeable_content": has_ai_gradeable_answer_content(
            student_answer=answer.text_answer,
            answer_files=answer_files,
            paint_image=getattr(answer, "paint_image", None),
        ),
    }


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
        request.GET.get("return_to") or request.GET.get("next") or request.META.get("HTTP_REFERER"),
    )
    profile_return_url = explicit_return_url or fallback_profile_return_url

    navigation_params = {
        "from_section": requested_profile_section,
        "return_to": profile_return_url,
    }
    return profile_return_url, navigation_params


def _parse_filter_date(raw_value):
    raw_date = (raw_value or "").strip()
    if not raw_date:
        return "", None
    try:
        return raw_date, datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return "", None


def _resolve_attempt_action_state(attempt, *, can_view_name, review_window_seconds, identity_window_seconds):
    if attempt.exam.exam_type == "test":
        return {
            "label": "Bax",
            "url_name": "exams:teacher_view_attempt",
            "countdown_seconds": 0,
            "countdown_mode": "",
        }

    if attempt.checked_by_teacher:
        if review_window_seconds:
            return {
                "label": "Yenidən yoxla",
                "url_name": "exams:teacher_check_attempt",
                "countdown_seconds": review_window_seconds,
                "countdown_mode": "recheck",
            }
        return {
            "label": "Bax",
            "url_name": "exams:teacher_view_attempt",
            "countdown_seconds": 0,
            "countdown_mode": "",
        }

    return {
        "label": "Yoxla",
        "url_name": "exams:teacher_check_attempt",
        "countdown_seconds": identity_window_seconds if not can_view_name else 0,
        "countdown_mode": "identity" if not can_view_name and identity_window_seconds else "",
    }


def _build_anonymous_name(*, attempt_id: int, user_id: int, exam_id: int) -> str:
    token = salted_hmac(
        ANONYMOUS_NAME_TOKEN_SALT,
        f"{attempt_id}:{user_id}:{exam_id}",
    ).hexdigest()
    return pgettext("exams.view.results.label", "anonymous_student").format(
        code=token[:ANONYMOUS_NAME_CODE_LENGTH].upper()
    )


@login_required
def teacher_exam_results(request, slug):
    """
    Müəllim üçün imtahan nəticələri:
    - solda bütün cəhdlər cədvəli
    - aşağıda/sağda seçilmiş cəhdin cavabları + qiymətləndirmə formu
    """
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    profile_return_url, navigation_params = _resolve_profile_navigation(request, default_section="my-exams")
    exam_navigation_query = urlencode(navigation_params)
    exam_detail_url = _append_query_params(
        reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
        **navigation_params,
    )

    attempts = exam.attempts.select_related("user")

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
        from apps.notifications.services import notify_student_about_feedback

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
                    notify_student_about_feedback(
                        task=exam,
                        student=selected_attempt.user,
                        task_kind="exam",
                        extra_metadata={"attempt_id": selected_attempt.id},
                    )
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
            notify_student_about_feedback(
                task=exam,
                student=selected_attempt.user,
                task_kind="exam",
                extra_metadata={"attempt_id": selected_attempt.id},
            )
            messages.success(request, pgettext_lazy("exams.view.results.message", "feedback_saved"))
            return redirect(
                _append_query_params(
                    request.path,
                    attempt=selected_attempt.id,
                    **navigation_params,
                )
            )

    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        attempts = attempts.filter(
            Q(user__username__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
        )

    status_filter = (request.GET.get("status") or "all").strip().lower()
    allowed_status_filters = {"all", "draft", "in_progress", "submitted", "expired"}
    if status_filter not in allowed_status_filters:
        status_filter = "all"
    if status_filter != "all":
        attempts = attempts.filter(status=status_filter)

    checked_filter = (request.GET.get("checked") or "all").strip().lower()
    if checked_filter == "checked":
        attempts = attempts.filter(checked_by_teacher=True)
    elif checked_filter == "unchecked":
        attempts = attempts.filter(checked_by_teacher=False)
    else:
        checked_filter = "all"

    date_from_raw, date_from = _parse_filter_date(request.GET.get("date_from"))
    date_to_raw, date_to = _parse_filter_date(request.GET.get("date_to"))
    if date_from:
        attempts = attempts.filter(started_at__date__gte=date_from)
    if date_to:
        attempts = attempts.filter(started_at__date__lte=date_to)

    # ---------- Sorting ----------
    sort_by = (request.GET.get("sort_by") or "").strip()
    sort_dir = (request.GET.get("sort_dir") or "").strip()
    ALLOWED_SORT_FIELDS = {
        "user": "user__first_name",
        "status": "status",
        "correct": "correct_count",
        "wrong": "wrong_count",
        "score": "teacher_score",
        "start": "started_at",
        "end": "finished_at",
        "duration": "duration_seconds",
    }
    if sort_by in ALLOWED_SORT_FIELDS and sort_dir in ("asc", "desc"):
        order_field = ALLOWED_SORT_FIELDS[sort_by]
        if sort_dir == "desc":
            order_field = f"-{order_field}"
        attempts = attempts.order_by(order_field)
    else:
        sort_by = ""
        sort_dir = ""
        attempts = attempts.order_by("-started_at")

    max_score = 100 if exam.exam_type == "test" else exam.questions.aggregate(total=Sum("points")).get("total") or 0
    pending_count = 0 if exam.exam_type == "test" else attempts.filter(checked_by_teacher=False).count()
    graded_count = attempts.count() if exam.exam_type == "test" else attempts.filter(checked_by_teacher=True).count()
    review_stats = {
        "total": attempts.count(),
        "pending": pending_count,
        "graded": graded_count,
        "max_score": max_score,
    }
    paginator = Paginator(attempts, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    attempts_page = list(page_obj.object_list)

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

    for att in attempts_page:
        anonymous_name = _build_anonymous_name(attempt_id=att.id, user_id=att.user_id, exam_id=exam.id)

        can_view_name, identity_window_seconds = _resolve_attempt_name_visibility(att, current_time=now)
        review_window_seconds = _resolve_attempt_review_window_seconds(att, current_time=now)
        action_state = _resolve_attempt_action_state(
            att,
            can_view_name=can_view_name,
            review_window_seconds=review_window_seconds,
            identity_window_seconds=identity_window_seconds,
        )
        real_name = att.user.get_full_name() or att.user.username

        attempts_data.append(
            {
                "attempt": att,
                "anonymous_name": anonymous_name,
                "real_name": real_name,
                "can_view_name": can_view_name,
                "seconds_remaining": review_window_seconds or identity_window_seconds or 0,
                "action_label": action_state["label"],
                "action_url": _append_query_params(
                    reverse(action_state["url_name"], kwargs={"slug": exam.slug, "attempt_id": att.id}),
                    **navigation_params,
                ),
                "countdown_seconds": action_state["countdown_seconds"],
                "countdown_mode": action_state["countdown_mode"],
            }
        )

    # ═══════════════════════════════════════════════════════════════════
    # Statistikalar (əvvəlki kimi)
    # ═══════════════════════════════════════════════════════════════════
    filtered_attempts = list(attempts)
    fastest_attempts = sorted([a for a in filtered_attempts if a.duration_seconds], key=lambda a: a.duration_seconds)[
        :5
    ]

    questions = exam.questions.all()
    hardest_questions = sorted(questions, key=lambda q: q.correct_ratio)[:5]

    pagination_query = urlencode(
        {
            key: value
            for key, value in {
                "q": search_query,
                "status": status_filter,
                "checked": checked_filter,
                "date_from": date_from_raw,
                "date_to": date_to_raw,
                "sort_by": sort_by,
                "sort_dir": sort_dir,
                "attempt": (request.GET.get("attempt") or "").strip(),
                "from_section": (request.GET.get("from_section") or "").strip(),
                "return_to": (request.GET.get("return_to") or "").strip(),
            }.items()
            if value not in ("", None)
        }
    )

    sort_base_query = urlencode(
        {
            key: value
            for key, value in {
                "q": search_query,
                "status": status_filter,
                "checked": checked_filter,
                "date_from": date_from_raw,
                "date_to": date_to_raw,
                "attempt": (request.GET.get("attempt") or "").strip(),
                "from_section": (request.GET.get("from_section") or "").strip(),
                "return_to": (request.GET.get("return_to") or "").strip(),
            }.items()
            if value not in ("", None)
        }
    )

    return render(
        request,
        "exams/teacher/teacher_exam_results.html",
        {
            "exam": exam,
            "attempts": page_obj.object_list,
            "attempts_data": attempts_data,
            "page_obj": page_obj,
            "fastest_attempts": fastest_attempts,
            "hardest_questions": hardest_questions,
            "selected_attempt": selected_attempt,
            "selected_answers": selected_answers,
            "profile_return_url": profile_return_url,
            "exam_detail_url": exam_detail_url,
            "exam_navigation_query": exam_navigation_query,
            "source_back_label": pgettext("exams.template.teacher_exam_detail", "action_back"),
            "review_stats": review_stats,
            "search_query": search_query,
            "status_filter": status_filter,
            "checked_filter": checked_filter,
            "date_from": date_from_raw,
            "date_to": date_to_raw,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "sort_base_query": sort_base_query,
            "pagination_query": pagination_query,
            "can_delete_attempts": request_has_permission(request, "exam.delete"),
        },
    )


@login_required
@require_http_methods(["POST"])
def delete_exam_attempts(request, slug):
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    redirect_url = _safe_same_origin_redirect_path(request, request.POST.get("next"))
    if not redirect_url:
        nav_params = {}
        from_section = (request.POST.get("from_section") or "").strip()
        return_to = _safe_same_origin_redirect_path(request, request.POST.get("return_to"))
        if from_section:
            nav_params["from_section"] = from_section
        if return_to:
            nav_params["return_to"] = return_to
        redirect_url = _append_query_params(
            reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}),
            **nav_params,
        )

    if not request_has_permission(request, "exam.delete"):
        messages.error(request, pgettext_lazy("exams.view.results.message", "delete_permission_required"))
        return redirect(redirect_url)

    raw_ids = request.POST.getlist("attempt_ids")
    single_attempt_id = (request.POST.get("attempt_id") or "").strip()
    if single_attempt_id:
        raw_ids.append(single_attempt_id)

    attempt_ids = sorted({int(raw_id) for raw_id in raw_ids if str(raw_id).isdigit()})
    if not attempt_ids:
        messages.warning(request, pgettext_lazy("exams.view.results.message", "select_attempt_to_delete"))
        return redirect(redirect_url)

    attempts_qs = exam.attempts.filter(id__in=attempt_ids)
    attempt_count = attempts_qs.count()
    if attempt_count == 0:
        messages.warning(request, pgettext_lazy("exams.view.results.message", "attempt_not_found"))
        return redirect(redirect_url)

    attempts_qs.delete()
    messages.success(
        request,
        pgettext_lazy("exams.view.results.message", "attempts_deleted").format(count=attempt_count),
    )
    return redirect(redirect_url)


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

    qa_list = [_build_answer_review_item(a) for a in answers_qs]
    can_view_name, identity_window_seconds = _resolve_attempt_name_visibility(attempt, current_time=timezone.now())
    if attempt.exam.exam_type == "test":
        student_display = attempt.user.get_full_name() or attempt.user.username
    else:
        anonymous_name = _build_anonymous_name(
            attempt_id=attempt.id,
            user_id=attempt.user_id,
            exam_id=attempt.exam_id,
        )
        student_display = attempt.user.get_full_name() or attempt.user.username if can_view_name else anonymous_name

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
            if search_token in question_text or search_token in answer_text or search_token in options_text:
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
        "source_back_label": pgettext("exams.template.teacher_exam_detail", "action_back"),
        "student_display": student_display,
        "can_view_student_identity": can_view_name,
        "identity_window_seconds_left": identity_window_seconds,
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
    if navigation_params.get("from_section") == "pending-review":
        results_return_url = profile_return_url
    else:
        results_return_url = _append_query_params(
            reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}),
            **navigation_params,
        )
    view_attempt_url = _append_query_params(
        reverse("exams:teacher_view_attempt", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
        **navigation_params,
    )

    # ✅ 5 dəqiqə keçibsə, yalnız "bax" səhifəsinə yönləndir
    if _attempt_review_window_locked(attempt, current_time=timezone.now()):
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

    qa_list = [_build_answer_review_item(a) for a in answers_qs]
    can_view_name, identity_window_seconds = _resolve_attempt_name_visibility(attempt, current_time=timezone.now())
    if attempt.exam.exam_type == "test":
        student_display = attempt.user.get_full_name() or attempt.user.username
    else:
        anonymous_name = _build_anonymous_name(
            attempt_id=attempt.id,
            user_id=attempt.user_id,
            exam_id=attempt.exam_id,
        )
        student_display = attempt.user.get_full_name() or attempt.user.username if can_view_name else anonymous_name

    if request.method == "POST":
        if not request_has_permission(request, "grade.input"):
            messages.error(
                request,
                pgettext_lazy("exams.view.results.message", "grading_permission_required"),
            )
            return redirect(view_attempt_url)

        # ✅ DOUBLE-CHECK: POST zamanı da yoxla
        if _attempt_review_window_locked(attempt, current_time=timezone.now()):
            messages.error(
                request,
                pgettext_lazy("exams.view.results.message", "cannot_edit_after_five_minutes"),
            )
            return redirect(view_attempt_url)

        total_score = 0
        any_score = False
        from apps.notifications.services import notify_student_about_feedback

        for a in answers_qs:
            q = a.question

            score_raw = (request.POST.get(f"score_{q.id}") or "").strip()
            max_points_raw = (request.POST.get(f"max_points_{q.id}") or "").strip()
            feedback = (request.POST.get(f"feedback_{q.id}") or "").strip()

            if max_points_raw:
                try:
                    max_points_val = int(max_points_raw)
                except ValueError:
                    max_points_val = q.points
                max_points_val = max(1, max_points_val)
            else:
                max_points_val = q.points

            if q.points != max_points_val:
                q.points = max_points_val
                q.save(update_fields=["points"])

            if score_raw == "":
                a.teacher_score = None
            else:
                try:
                    score_val = int(score_raw)
                except ValueError:
                    score_val = 0
                score_val = max(0, min(score_val, max_points_val))
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
        notify_student_about_feedback(
            task=exam,
            student=attempt.user,
            task_kind="exam",
            extra_metadata={"attempt_id": attempt.id},
        )

        messages.success(request, pgettext_lazy("exams.view.results.message", "attempt_checked_success"))
        return redirect(results_return_url)

    context = {
        "exam": exam,
        "attempt": attempt,
        "qa_list": qa_list,
        "profile_return_url": profile_return_url,
        "results_return_url": results_return_url,
        "student_display": student_display,
        "can_view_student_identity": can_view_name,
        "identity_window_seconds_left": identity_window_seconds,
    }
    return render(request, "exams/teacher/teacher_check_attempt.html", context)


@login_required
@require_http_methods(["POST"])
def ai_grade_answer(request, slug, attempt_id):
    """AJAX endpoint — AI grades a single written answer."""
    from django.http import JsonResponse

    from apps.exams.services.ai_grading import grade_written_answer

    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    question_id = data.get("question_id")
    if not question_id:
        return JsonResponse({"ok": False, "error": "question_id required"}, status=400)

    answer = (
        attempt.answers.select_related("question").prefetch_related("files").filter(question_id=question_id).first()
    )
    if not answer:
        return JsonResponse({"ok": False, "error": "Answer not found"}, status=404)

    q = answer.question
    try:
        max_points = int(data.get("max_points", q.points) or q.points)
    except (TypeError, ValueError):
        max_points = q.points
    max_points = max(1, max_points)

    result = grade_written_answer(
        question_text=q.text,
        student_answer=answer.text_answer or "",
        max_points=int(max_points),
        correct_answer=getattr(q, "correct_answer", "") or "",
        language_code=request.LANGUAGE_CODE,
        user_id=request.user.pk,
        answer_files=answer.files.all(),
        paint_image=getattr(answer, "paint_image", None),
    )
    return JsonResponse(result)


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
        anonymous_name = _build_anonymous_name(attempt_id=att.id, user_id=att.user_id, exam_id=att.exam_id)

        can_view_name, seconds_remaining = _resolve_attempt_name_visibility(att, current_time=now)

        attempts_data.append(
            {
                "attempt": att,
                "anonymous_name": anonymous_name,
                "real_name": att.user.get_full_name() or att.user.username,
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
