"""
Evaluated-review collector for the teacher review-results section.
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Submission
from apps.courses.models import Course
from apps.exams.models import Exam, ExamAnswer, ExamAttempt
from apps.labs.models import LabSubmission
from apps.projects.models import ProjectSubmission
from core.search_text import tolerant_q

from .._helpers import (
    REVIEW_EDIT_WINDOW,
    _append_query_params,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)
from .._helpers.task_kind_visibility import hidden_task_filters, visible_task_filter
from .evaluated_review_filters import (
    EXAM_CATEGORY_FILTERS,
    EXAM_KIND_FILTERS,
    PERIOD_FILTERS,
    attempt_window_q,
    graded_window_q,
    item_in_window,
    resolve_date_window,
    subject_options,
)
from .formatters import (
    _attach_registry_groups,
    _build_student_group_map_and_available,
    _format_score_display,
    _normalize_pending_review_type,
    _normalize_submission_date_order,
    _user_display_name,
)
from .review_scope import review_exams_q

User = get_user_model()


def _percent_tone(percent):
    """Faiz nişanının tonu — baxış səhifəsi ilə eyni hədd (≥ 50 → yaşıl, əks halda qırmızı)."""
    return "success" if percent >= 50 else "danger"


def fill_evaluated_test_scores(items):
    """«Nəticə» sütunu — YALNIZ verilən (səhifənin) sətirləri üçün.

    * test: cavablar bir prefetch dəstində, apellyasiya bonusları tək sorğuda oxunur;
      hesablama əvvəlki kimidir (bal / maks bal + faiz);
    * yazılı/praktiki (2026-10-17): müəllim balı ÇATDIRILAN sualların snapshot tavanına
      bölünür (jurnal sinxronu ilə eyni qayda) — «bal / maks» + faiz; cavab + sual
      sətirləri yenə bir prefetch dəstində."""
    from django.db.models import Prefetch, prefetch_related_objects

    from apps.appeals.public import appeal_bonus_map, apply_bonus_to_test_result
    from apps.exams.public import answer_max_points, calculate_test_attempt_result

    pending = [item for item in items if item.get("pending_score_attempt") is not None]
    if pending:
        attempts = [item["pending_score_attempt"] for item in pending]
        prefetch_related_objects(attempts, "answers__question__options", "answers__selected_options")
        appeal_bonus_by_attempt = appeal_bonus_map([attempt.id for attempt in attempts])
        for item, attempt in zip(pending, attempts):
            result = calculate_test_attempt_result(attempt, answers=attempt.answers.all())
            bonus = appeal_bonus_by_attempt.get(attempt.id)
            if bonus:
                result = apply_bonus_to_test_result(result, bonus)
            item["score_display"] = f"{result.score_display} / {result.max_score_display}"
            item["score_percent_display"] = f"{result.percentage_display}%"
            item["score_tone"] = _percent_tone(float(result.percentage))
            item["pending_score_attempt"] = None

    written = [item for item in items if item.get("pending_written_attempt") is not None]
    if written:
        attempts = [item["pending_written_attempt"] for item in written]
        # Bir sorğu: cavab + sual (JOIN) — tavan snapshot-dan, yoxdursa canlı sualdan.
        prefetch_related_objects(attempts, Prefetch("answers", queryset=ExamAnswer.objects.select_related("question")))
        for item, attempt in zip(written, attempts):
            max_score = sum(answer_max_points(answer) for answer in attempt.answers.all())
            item["pending_written_attempt"] = None
            if not max_score:
                continue
            percent = round(float(attempt.teacher_score) * 100.0 / float(max_score), 1)
            item["score_display"] = f"{_format_score_display(attempt.teacher_score)} / {max_score}"
            item["score_percent_display"] = f"{_format_score_display(percent)}%"
            item["score_tone"] = _percent_tone(percent)
    return items


def fill_evaluated_checkers(items):
    """«Yoxlayan» — imtahan sətirləri üçün YALNIZ verilən (səhifənin) sətirlərində (2 sorğu, 2026-10-27).

    Bal qoyan / dəyişən insan varsa onun adı; yoxdursa test / kodlaşdırma cəhdində «Avtomatik (sistem)».
    Əvvəl imtahanın MÜƏLLİFİ yazılırdı — avtomatik yoxlanan testdə yanlış təəssürat yaradırdı."""
    from apps.exams.public import attempt_checked_by_map

    exam_items = [item for item in items if item.get("attempt") is not None]
    if exam_items:
        labels = attempt_checked_by_map([item["attempt"] for item in exam_items])
        for item in exam_items:
            item["evaluator_display"] = labels.get(item["attempt_id"], "")
    return items


__all__ = [
    "EXAM_CATEGORY_FILTERS",
    "EXAM_KIND_FILTERS",
    "PERIOD_FILTERS",
    "_collect_evaluated_review_items",
    "fill_evaluated_checkers",
    "fill_evaluated_test_scores",
]


def _param(request, name, override=None):
    return (override if override is not None else request.GET.get(name, "")).strip()


def _collect_evaluated_review_items(
    request, search=None, filter_type=None, filter_group=None, submitted_order=None, period=None
):
    """Süzülmüş sətirlər + seçici vəziyyəti.

    Qaytarır: ``(items, search, type, group, groups, order, period, extras)`` — ``extras``:
    ``subject`` / ``subjects`` (fənn süzgəci), ``date_from`` / ``date_to`` (aralığın kanonik mətni).
    İmtahan sətirlərində ``attempt`` obyekti saxlanılır (ixrac + «Yoxlayan» görünən səhifə üçün);
    «Yoxlayan» imtahan sətirlərində səhifələmədən SONRA doldurulur (``fill_evaluated_checkers``).
    """
    search_query = (search if search is not None else request.GET.get("evaluated_search", "")).strip()
    # 2026-10-13 (rol auditi B12): söndürülmüş «Sərbəst iş» / «Kurs işi» tabı seçilə bilməz, sətirləri yığılmır.
    hidden_types = hidden_task_filters("review-results")
    raw_type = (filter_type if filter_type is not None else request.GET.get("evaluated_type", "all")) or "all"
    exam_kind = EXAM_KIND_FILTERS.get(raw_type.lower(), "")
    exam_category = EXAM_CATEGORY_FILTERS.get(raw_type.lower(), "")
    normalized_type = (
        "exams"
        if exam_kind or exam_category
        else visible_task_filter("review-results", _normalize_pending_review_type(raw_type))
    )
    selected_type = raw_type.lower() if exam_kind or exam_category else normalized_type
    window = resolve_date_window(
        _param(request, "evaluated_period", period),
        _param(request, "evaluated_from"),
        _param(request, "evaluated_to"),
    )
    selected_period = window.period
    selected_subject = _param(request, "evaluated_subject")[:255]
    selected_group = (filter_group if filter_group is not None else request.GET.get("evaluated_group", "")).strip()
    normalized_submitted_order = _normalize_submission_date_order(
        submitted_order if submitted_order is not None else request.GET.get("evaluated_submitted_order", "newest"),
        default="newest",
    )

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    # Sahib 2026-10-26: imtahan mərkəzi (işçi + rəhbər) org-un BÜTÜN midterm/final nəticələrini görür
    # (yaradandan asılı deyil); quiz/kateqoriyasız yalnız müəllifindir — ``manageable_exams_q``.
    teacher_exams = _tenant_scoped_exams(request, Exam.objects.filter(review_exams_q(request.user)))
    review_cutoff = timezone.now() - REVIEW_EDIT_WINDOW
    # Review 2026-10-18: «Dövr» süzgəci BAZADA da (Python süzgəci aşağıda eyni qaydanı saxlayır — nəticə dəyişmir).
    # 2026-10-27: hazır dövrə əlavə olaraq istənilən tarix-saat aralığı (``evaluated_from`` / ``evaluated_to``).

    def _graded_since(qs):
        return qs.filter(graded_window_q(window)) if window.active else qs

    # Qrup seçimi sətirlər yığılandan SONRA yoxlanılır — qrup reyestrdən gəlir (``_attach_registry_groups``).
    student_group_map, legacy_groups = _build_student_group_map_and_available(request.user)

    profile_return_url = _append_query_params(
        reverse("accounts:profile"),
        section="review-results",
        evaluated_search=search_query,
        evaluated_type=selected_type,
        evaluated_group=selected_group,
        evaluated_period=selected_period,
        evaluated_from=window.from_text,
        evaluated_to=window.to_text,
        evaluated_subject=selected_subject,
        evaluated_submitted_order=normalized_submitted_order,
        er_page=(request.GET.get("er_page") or "").strip(),
    )

    items = []

    if normalized_type in {"all", "exams"}:
        attempts = (
            ExamAttempt.objects.filter(
                exam__in=teacher_exams,
                status__in=["submitted", "expired"],
            )
            .filter(
                Q(exam__exam_type="test")
                | Q(checked_by_teacher=True, teacher_checked_at__isnull=True)
                | Q(checked_by_teacher=True, teacher_checked_at__lte=review_cutoff)
            )
            .select_related("exam", "user", "exam__author", "exam__course", "exam__subject")
            # Cavablar burada prefetch OLUNMUR: test balı yalnız görünən səhifənin
            # sətirləri üçün hesablanır (``fill_evaluated_test_scores``). Əvvəl
            # müəllimin BÜTÜN test tarixçəsinin cavab + variant sətirləri hər
            # açılışda yüklənirdi, səhifə isə 15 sətir göstərir (2026-10-07).
        )
        if exam_kind:
            attempts = attempts.filter(exam__exam_type=exam_kind)
        if exam_category:
            attempts = attempts.filter(exam__exam_type_extended=exam_category)
        if window.active:
            attempts = attempts.filter(attempt_window_q(window))
        search_q = tolerant_q(
            search_query,
            ("user__username", "user__first_name", "user__last_name", "exam__title", "exam__course__title"),
        )
        if search_q is not None:
            attempts = attempts.filter(search_q)
        for attempt in attempts:
            course = attempt.exam.course
            submitted_at = attempt.finished_at or attempt.started_at
            pending_score_attempt = None
            pending_written_attempt = None
            if attempt.exam.exam_type == "test":
                # "Nəticə" sütununda əsas dəyər BAL-dır (bal / maks bal);
                # faiz ayrıca badge kimi göstərilir (əvvəl yalnız faiz çıxırdı).
                if attempt.teacher_score is not None:
                    score_display = _format_score_display(attempt.teacher_score)
                else:
                    # Səhifələmədən SONRA doldurulur (bax ``fill_evaluated_test_scores``).
                    score_display = ""
                    pending_score_attempt = attempt
                score_percent_display = ""
            else:
                if attempt.teacher_score is not None:
                    score_display = _format_score_display(attempt.teacher_score)
                    # «bal / maks» + faiz səhifələmədən SONRA (``fill_evaluated_test_scores``).
                    pending_written_attempt = attempt
                else:
                    score_display = _format_score_display(attempt.score_percent)
                score_percent_display = ""
            items.append(
                {
                    "type": "exam",
                    "exam_kind": attempt.exam.exam_type,
                    "exam_kind_label": attempt.exam.get_exam_type_display(),
                    "exam_category": attempt.exam.exam_type_extended or "",
                    "exam_category_label": (
                        attempt.exam.get_exam_type_extended_display() if attempt.exam.exam_type_extended else ""
                    ),
                    "attempt_id": attempt.id,
                    "attempt": attempt,
                    "student": attempt.user,
                    "title": attempt.exam.title,
                    "course_title": course.title if course else "-",
                    "subject_title": (
                        attempt.exam.subject.name if attempt.exam.subject_id else (course.title if course else "")
                    ),
                    "group_name": student_group_map.get(attempt.user_id, ""),
                    "score_display": score_display,
                    "score_percent_display": score_percent_display,
                    # 2026-10-27: «Yoxlayan» = bal qoyan İNSAN, yoxdursa «Avtomatik (sistem)» — müəllif DEYİL
                    # (``fill_evaluated_checkers``, yalnız görünən səhifə; ixrac eyni qaydanı işlədir).
                    "evaluator_display": "",
                    # Başqasının imtahanı (mərkəz görünüşü) — «Yaradan» sətirdə ayrıca göstərilir.
                    "creator_display": (
                        _user_display_name(attempt.exam.author) if attempt.exam.author_id != request.user.id else ""
                    ),
                    "submitted_at": submitted_at,
                    "reviewed_at": attempt.teacher_checked_at,
                    "action_url": _append_query_params(
                        reverse(
                            "exams:teacher_view_attempt",
                            kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id},
                        ),
                        from_section="review-results",
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "review"),
                    "pending_score_attempt": pending_score_attempt,
                    "pending_written_attempt": pending_written_attempt,
                }
            )

    if normalized_type in {"all", "assignments"} and "assignments" not in hidden_types:
        submissions = (
            Submission.objects.filter(
                assignment__course__in=teacher_courses,
                status="graded",
            )
            .filter(Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff))
            .select_related("assignment", "assignment__course", "user", "graded_by")
        )
        search_q = tolerant_q(
            search_query,
            ("user__username", "user__first_name", "user__last_name", "assignment__title", "assignment__course__title"),
        )
        if search_q is not None:
            submissions = submissions.filter(search_q)
        submissions = _graded_since(submissions)
        for submission in submissions:
            course = submission.assignment.course
            items.append(
                {
                    "type": "assignment",
                    "student": submission.user,
                    "title": submission.assignment.title,
                    "course_title": course.title if course else "-",
                    "subject_title": course.title if course else "",
                    "status_display": submission.get_status_display(),
                    "group_name": student_group_map.get(submission.user_id, ""),
                    "score_display": _format_score_display(submission.grade),
                    "evaluator_display": _user_display_name(submission.graded_by) if submission.graded_by_id else "-",
                    "submitted_at": submission.submitted_at,
                    "reviewed_at": submission.graded_at,
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:review_result_detail",
                            kwargs={"item_type": "assignment", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "open_assignment"),
                }
            )

    if normalized_type in {"all", "projects"} and "projects" not in hidden_types:
        project_submissions = (
            ProjectSubmission.objects.filter(
                project__course__in=teacher_courses,
                status="graded",
            )
            .filter(Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff))
            .select_related("project", "project__course", "student", "graded_by")
        )
        search_q = tolerant_q(
            search_query,
            (
                "student__username",
                "student__first_name",
                "student__last_name",
                "project__title",
                "project__course__title",
            ),
        )
        if search_q is not None:
            project_submissions = project_submissions.filter(search_q)
        project_submissions = _graded_since(project_submissions)
        for submission in project_submissions:
            course = submission.project.course
            items.append(
                {
                    "type": "project",
                    "student": submission.student,
                    "title": submission.project.title,
                    "course_title": course.title if course else "-",
                    "subject_title": course.title if course else "",
                    "status_display": submission.get_status_display(),
                    "group_name": student_group_map.get(submission.student_id, ""),
                    "score_display": _format_score_display(submission.grade),
                    "evaluator_display": _user_display_name(submission.graded_by) if submission.graded_by_id else "-",
                    "submitted_at": submission.submitted_at,
                    "reviewed_at": submission.graded_at,
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:review_result_detail",
                            kwargs={"item_type": "project", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "open_project"),
                }
            )

    if normalized_type in {"all", "labs"}:
        lab_submissions = (
            LabSubmission.objects.filter(
                assignment__lab__course__in=teacher_courses,
                status="graded",
            )
            .filter(Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff))
            .select_related(
                "assignment",
                "assignment__lab",
                "assignment__lab__course",
                "assignment__student",
                "graded_by",
            )
        )
        search_q = tolerant_q(
            search_query,
            (
                "assignment__student__username",
                "assignment__student__first_name",
                "assignment__student__last_name",
                "assignment__lab__title",
                "assignment__lab__course__title",
            ),
        )
        if search_q is not None:
            lab_submissions = lab_submissions.filter(search_q)
        lab_submissions = _graded_since(lab_submissions)
        for submission in lab_submissions:
            student = submission.assignment.student
            course = submission.assignment.lab.course
            items.append(
                {
                    "type": "lab",
                    "student": student,
                    "title": submission.assignment.lab.title,
                    "course_title": course.title if course else "-",
                    "subject_title": course.title if course else "",
                    "status_display": submission.get_status_display(),
                    "group_name": student_group_map.get(student.id, ""),
                    "score_display": _format_score_display(submission.score),
                    "evaluator_display": _user_display_name(submission.graded_by) if submission.graded_by_id else "-",
                    "submitted_at": submission.submitted_at,
                    "reviewed_at": submission.graded_at,
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:review_result_detail",
                            kwargs={"item_type": "lab", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "grade"),
                }
            )

    available_groups = _attach_registry_groups(items, legacy_groups)
    available_subjects = subject_options(items)
    if selected_group and selected_group not in available_groups:
        selected_group = ""
    if selected_subject and selected_subject not in available_subjects:
        selected_subject = ""
    if selected_group:
        items = [item for item in items if item.get("group_name") == selected_group]
    if selected_subject:
        items = [item for item in items if item.get("subject_title") == selected_subject]
    if window.active:
        items = [item for item in items if item_in_window(item, window)]

    items.sort(
        key=lambda item: (
            item["submitted_at"] is None,
            item["submitted_at"] or timezone.now(),
        ),
        reverse=normalized_submitted_order == "newest",
    )
    return (
        items,
        search_query,
        selected_type,
        selected_group,
        available_groups,
        normalized_submitted_order,
        selected_period,
        {
            "subject": selected_subject,
            "subjects": available_subjects,
            "date_from": window.from_text,
            "date_to": window.to_text,
        },
    )
