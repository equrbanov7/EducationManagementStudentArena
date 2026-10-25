"""results paketi — müəllim nəticə view funksiyaları (qrup)."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

from apps.exams import score_adjustments
from apps.exams.models import ExamAnswer, ExamAttempt
from apps.exams.services.access_policy import _ensure_teacher, is_exam_center_user
from apps.exams.services.attempt_budget import attempts_left_map
from apps.exams.services.formal_retake import formal_retake_url, requires_formal_retake
from apps.exams.services.manual_grading import (
    ManualGradingAttemptNotFinished,
    ManualGradingWindowClosed,
    apply_attempt_grade,
)
from apps.exams.services.result_calculation import calculate_test_attempt_result
from apps.exams.services.review_visibility import (
    resolve_exam_attempt_name_visibility as _resolve_attempt_name_visibility,
)
from apps.exams.services.review_visibility import (
    resolve_exam_attempt_review_window_seconds as _resolve_attempt_review_window_seconds,
)
from apps.exams.services.supervision import attach_attempt_interventions
from apps.exams.views.shared.breadcrumbs import exam_breadcrumbs
from apps.exams.views.shared.tenant import get_teacher_exam_or_404
from core.permissions import request_has_permission

from ._filter_context import results_filter_context, results_per_page
from ._helpers import (
    _appeal_bonus_map_for,
    _append_query_params,
    _apply_appeal_bonus,
    _apply_results_filters,
    _attempt_effective_duration,
    _attempt_effective_finish,
    _build_anonymous_name,
    _resolve_attempt_action_state,
    _resolve_profile_navigation,
)
from ._test_scores import attach_legacy_selected_options


def _explicit_return_url(request):
    """Yalnız açıq verilmiş və imtahan səhifəsi OLMAYAN `return_to`/`next` (sahib 2026-09-21)."""
    from apps.exams.views.teacher.question_bank._helpers import _is_internal_exam_management_path

    from ._helpers import _safe_same_origin_redirect_path

    candidate = _safe_same_origin_redirect_path(request, request.GET.get("return_to") or request.GET.get("next"))
    if not candidate or _is_internal_exam_management_path(candidate):
        return ""
    # Kabinet URL-i axının BAŞLANĞICIDIR (detal səhifəsinin «Geri»si) — alt səhifədə
    # «Geri» onu yox, əvvəlki krambı (detalı) göstərməlidir.
    if candidate.startswith(reverse("accounts:profile")):
        return ""
    return candidate


@login_required
def teacher_exam_results(request, slug):
    """
    Müəllim üçün imtahan nəticələri:
    - solda bütün cəhdlər cədvəli
    - aşağıda/sağda seçilmiş cəhdin cavabları + qiymətləndirmə formu
    """
    _ensure_teacher(request.user)
    # Yumşaq silinmiş imtahanın nəticələri "Zibil qutusu"ndan yalnız-oxu kimi
    # görünür (include_deleted). Qiymətləndirmə/dəyişiklik bloklanır.
    exam = get_teacher_exam_or_404(request, slug=slug, include_deleted=True)
    profile_return_url, navigation_params = _resolve_profile_navigation(request, default_section="my-exams")
    exam_navigation_query = urlencode(navigation_params)
    exam_detail_url = _append_query_params(
        reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}),
        **navigation_params,
    )

    selected_attempt = None
    selected_answers = None

    # ---------- POST: müəllim bal + feedback saxlayır ----------
    if request.method == "POST":
        if exam.is_deleted:
            messages.error(
                request,
                pgettext_lazy("exams.view.results.message", "cannot_grade_deleted_exam"),
            )
            return redirect(request.path)
        if not request_has_permission(request, "grade.input"):
            messages.error(
                request,
                pgettext_lazy("exams.view.results.message", "grading_permission_required"),
            )
            return redirect(request.path)

        attempt_id = request.POST.get("attempt_id")
        score_raw = request.POST.get("teacher_score", "").strip()
        feedback = request.POST.get("teacher_feedback", "").strip()
        from apps.notifications.public import notify_student_about_feedback

        selected_attempt = get_object_or_404(ExamAttempt, id=attempt_id, exam=exam)

        score_value = None
        score_is_valid = not score_raw
        if score_raw:
            try:
                score_val = int(score_raw)
            except ValueError:
                messages.error(request, pgettext_lazy("exams.view.results.message", "score_must_be_integer"))
            else:
                if 0 <= score_val <= 100:
                    score_value = score_val
                    score_is_valid = True
                else:
                    messages.error(request, pgettext_lazy("exams.view.results.message", "score_range_0_100"))

        if score_is_valid:
            try:
                selected_attempt, grading_changed = apply_attempt_grade(
                    attempt_id=selected_attempt.id,
                    score=score_value,
                    feedback=feedback,
                    grader=request.user,
                )
            except ManualGradingAttemptNotFinished:
                # Audit 2026-09-28 EX28-02: bitməmiş cəhd qiymətləndirilmir.
                messages.error(
                    request,
                    pgettext_lazy("exams.view.results.message", "attempt_not_finished_cannot_grade"),
                )
                return redirect(request.path)
            except ManualGradingWindowClosed:
                messages.error(
                    request,
                    pgettext_lazy("exams.view.results.message", "cannot_edit_after_five_minutes"),
                )
                return redirect(request.path)

            if grading_changed:
                notify_student_about_feedback(
                    task=exam,
                    student=selected_attempt.user,
                    task_kind="exam",
                    extra_metadata={"attempt_id": selected_attempt.id},
                )
            success_message = (
                pgettext_lazy("exams.view.results.message", "score_feedback_saved")
                if score_value is not None
                else pgettext_lazy("exams.view.results.message", "feedback_saved")
            )
            messages.success(request, success_message)
            return redirect(
                _append_query_params(
                    request.path,
                    attempt=selected_attempt.id,
                    **navigation_params,
                )
            )

    attempts, filter_state = _apply_results_filters(exam, request)
    group_index = filter_state["group_index"]
    per_page = results_per_page(request.GET.get("per_page"))

    max_score = 100 if exam.exam_type == "test" else exam.questions.aggregate(total=Sum("points")).get("total") or 0
    # Eyni filtrlənmiş çoxluq üzərində əvvəllər 4 ayrı COUNT (+ Paginator-un
    # özününkü) gedirdi — indi tək şərti aqreqat; test imtahanında hamısı
    # «yoxlanılıb» sayılır, gözləyən yoxdur (audit P1-9, 2026-09-12).
    attempt_stats = attempts.aggregate(
        total=Count("id"),
        graded=Count("id", filter=Q(checked_by_teacher=True)),
    )
    total_count = attempt_stats["total"] or 0
    graded_count = total_count if exam.exam_type == "test" else (attempt_stats["graded"] or 0)
    review_stats = {
        "total": total_count,
        "pending": 0 if exam.exam_type == "test" else total_count - graded_count,
        "graded": graded_count,
        "max_score": max_score,
    }
    paginator = Paginator(attempts, per_page)
    # Paginator-un sayı elə həmin çoxluğun ölçüsüdür — ikinci dəfə saymırıq
    # (legacy_review._paginator ilə eyni üsul).
    paginator.count = total_count
    page_obj = paginator.get_page(request.GET.get("page"))
    attempts_page = list(page_obj.object_list)
    attach_legacy_selected_options(attempts_page)
    can_delete_attempts = bool(
        request_has_permission(request, "exam.delete")
        and not exam.is_deleted
        and any(attempt.is_trial for attempt in attempts_page)
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
            .prefetch_related("question__options", "selected_options")
            .order_by("question__order", "question__id")
        )
        if exam.exam_type == "test":
            selected_attempt.test_result = calculate_test_attempt_result(
                selected_attempt,
                answers=list(selected_answers),
            )

    now = timezone.now()
    attempts_data = []

    # Apellyasiya bonusları (səhifədəki cəhdlər üçün tək sorğu) — qəbul olunmuş
    # apellyasiyalar müəllimin gördüyü Bal/Faiz sütunlarında da əks olunsun.
    appeal_bonus_by_attempt = _appeal_bonus_map_for(attempts_page) if exam.exam_type == "test" else {}

    # İmtahandan uzaqlaşdırılmış tələbələr cədvəldə qırmızı görünsün + səbəb
    # (N+1-siz). `att.exam_intervention` = {action, reason, is_terminal}.
    attach_attempt_interventions(attempts_page)
    # Apellyasiya nişanı (cəhdin son apellyasiyası) — səhifə üçün tək sorğu (appeals hook-u).
    appeal_status_map = score_adjustments.status_by_attempt([att.id for att in attempts_page])

    # Qalan cəhd sayı: əvvəllər hər sətirdə ``exam.attempts_left_for(att.user)``
    # (cəhd başına 3 sorğu, 12-lik səhifədə ~36) — indi səhifənin bütün
    # tələbələri üçün 3 sabit sorğu, eyni məntiqlə (audit P1-9, 2026-09-12).
    attempts_left_by_user = attempts_left_map(exam, [att.user_id for att in attempts_page])
    # 2026-10-24 (sahib): midterm / final — «Yenidən şans ver» rəsmi «Yenidən imtahan cəhdi» səhifəsinə aparır.
    formal_retake = requires_formal_retake(exam)

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
        effective_finish, finish_inferred = _attempt_effective_finish(att, now=now)
        effective_duration = _attempt_effective_duration(att, effective_finish)

        test_result = (
            calculate_test_attempt_result(att, answers=att.answers.all()) if exam.exam_type == "test" else None
        )
        appeal_bonus = appeal_bonus_by_attempt.get(att.id) or 0
        if test_result is not None:
            delivered_count = test_result.delivered_count
            if appeal_bonus:
                test_result = _apply_appeal_bonus(test_result, appeal_bonus)
        else:
            delivered_count = att.correct_count + att.wrong_count
        attempts_data.append(
            {
                "attempt": att,
                # Academic attempts are retention-protected.  Physical delete
                # controls are exposed only for disposable teacher trial runs;
                # the service revalidates this under row locks.
                "can_delete_attempt": att.is_trial,
                "test_result": test_result,
                "appeal_bonus": appeal_bonus,
                "delivered_count": delivered_count,
                "anonymous_name": anonymous_name,
                "real_name": real_name,
                "student_id": att.user_id,
                "attempts_left": attempts_left_by_user.get(att.user_id),
                "formal_retake_url": formal_retake_url(exam, student=att.user_id) if formal_retake else "",
                "can_view_name": can_view_name,
                "seconds_remaining": review_window_seconds or identity_window_seconds or 0,
                "action_code": action_state["code"],
                "action_label": action_state["label"],
                "action_url": _append_query_params(
                    reverse(action_state["url_name"], kwargs={"slug": exam.slug, "attempt_id": att.id}),
                    **navigation_params,
                ),
                "countdown_seconds": action_state["countdown_seconds"],
                "countdown_mode": action_state["countdown_mode"],
                "effective_finish": effective_finish,
                "finish_inferred": finish_inferred,
                "effective_duration_seconds": effective_duration,
                "intervention": getattr(att, "exam_intervention", None),
                "group": group_index.user_group.get(att.user_id),
                "cohorts": group_index.user_cohorts.get(att.user_id, ()),
                "appeal": appeal_status_map.get(att.id),
            }
        )

    # Perf: səhifə yalnız cari səhifənin cəhdlərini yükləyir (bax audit P1-9).
    filter_context = results_filter_context(exam, filter_state, request=request, per_page=per_page)
    export_xlsx_url = reverse("exams:export_exam_results_xlsx", kwargs={"slug": exam.slug})
    if filter_context["export_query"]:
        export_xlsx_url = f"{export_xlsx_url}?{filter_context['export_query']}"
    teacher_display = exam.author.get_full_name() or exam.author.username
    teacher_username = exam.author.username

    return render(
        request,
        "exams/teacher/teacher_exam_results.html",
        {
            "exam": exam,
            "exam_crumbs": exam_breadcrumbs(
                request,
                exam,
                navigation_query=exam_navigation_query,
                current=pgettext("exams.template.teacher_exam_results", "page_title_suffix"),
            ),
            "attempts": page_obj.object_list,
            "attempts_data": attempts_data,
            "page_obj": page_obj,
            "selected_attempt": selected_attempt,
            "selected_answers": selected_answers,
            # «Geri» = açıq xarici `return_to` (kurs paneli və s.) və ya əvvəlki kramb
            # (imtahan detalı) — referer/imtahan-daxili return_to ilişməsi yoxdur.
            "profile_return_url": _explicit_return_url(request) or exam_detail_url,
            "exam_detail_url": exam_detail_url,
            "exam_navigation_query": exam_navigation_query,
            "source_back_label": pgettext("exams.template.teacher_exam_detail", "action_back"),
            "review_stats": review_stats,
            **filter_context,
            # Silinmiş imtahan yalnız-oxu göstərilir: qiymət/silmə/redaktə gizlədilir.
            "exam_is_deleted": exam.is_deleted,
            "can_delete_attempts": can_delete_attempts,
            "available_groups": group_index.options,
            "grant_groups": group_index.grant_options,
            # Midterm / final: birbaşa əlavə cəhd yoxdur — rəsmi səhifə (yalnız İmtahan Mərkəzi açır).
            "formal_retake": formal_retake,
            "formal_retake_open": formal_retake and is_exam_center_user(request.user),
            "formal_retake_action": reverse("accounts:profile"),
            "formal_retake_exam_url": formal_retake_url(exam) if formal_retake else "",
            "export_xlsx_url": export_xlsx_url,
            "teacher_display": teacher_display,
            "teacher_username": teacher_username,
        },
    )


@login_required
def export_exam_results_xlsx(request, slug):
    """İmtahan nəticələrini xlsx olaraq export et.

    - Eyni filtrlər tətbiq olunur (group, status, checked, date, q).
    - Pagination YOX — bütün uyğun cəhdlər.
    - Tenant isolation: get_teacher_exam_or_404 bunu təmin edir.
    - C2 (2026-07-03): böyük datasetlər worker-də hazırlanır (export job) —
      kiçik datasetlər üçün davranış köhnə sinxron attachment ilə eynidir.
    """
    from django.conf import settings

    from apps.exams.views.teacher.extract_jobs import start_export_job

    from ._export_builder import build_exam_results_xlsx_export
    from ._filters import FILTER_KEYS, param_list

    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)

    attempts_qs, state = _apply_results_filters(exam, request)
    threshold = getattr(settings, "EXPORT_SYNC_MAX_ROWS", 500)
    if attempts_qs.count() <= threshold:
        filename, content_type, data = build_exam_results_xlsx_export(
            exam, list(attempts_qs), group_index=state["group_index"]
        )
        response = HttpResponse(data, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    filter_params = {key: ",".join(param_list(request.GET, key)) for key in FILTER_KEYS if param_list(request.GET, key)}
    return start_export_job(
        request,
        export_name="exam_results_xlsx",
        params={"exam_id": exam.pk, "filters": filter_params},
    )
