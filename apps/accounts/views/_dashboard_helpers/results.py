"""
"My results" collector for the profile dashboard.
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Submission
from apps.exams.models import ExamAttempt
from apps.exams.public import attach_attempt_interventions, calculate_test_attempt_result
from apps.labs.models import LabSubmission
from apps.projects.models import ProjectSubmission

from .._helpers import (
    REVIEW_EDIT_WINDOW,
    _append_query_params,
    _is_result_visible_to_student,
    _normalize_results_filter,
    _result_status_badge,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)
from .academic_results import collect_academic_items, count_academic_items
from .formatters import _standard_item_type_meta

User = get_user_model()


def _collect_my_results(request, filter_type=None, search=None, year=None, season=None):
    """
    Build a unified result list for current user across exams, assignments, labs,
    projects **and** the registrar's academic (journal) subject results.

    ``year`` / ``season`` yalnız AKADEMİK sətirlərə aiddir — yeni sistemin
    cəhd/təhvil sətirlərində semestr mənsubiyyəti yoxdur. Ona görə bu süzgəclərdən
    biri seçiləndə siyahı akademik sətirlərlə məhdudlaşır (bax aşağıdakı şərh).
    """
    user = request.user
    selected_filter = filter_type if filter_type is not None else request.GET.get("type")
    filter_type = _normalize_results_filter(selected_filter)
    year = (year or "").strip()
    season = (season or "").strip()
    # Semestr süzgəci aktivdirsə yalnız akademik sətirlər mənalıdır: imtahan
    # cəhdi / sərbəst iş təhvili heç bir semestrə bağlı deyil, ona görə onları
    # "2024/2025 Payız" kimi bir seçimin altında göstərmək yalan olardı.
    #
    # Süzgəc UI-da yalnız "Hamısı"/"Akademik" tablarında göstərilir; başqa tabda
    # URL-də ilişib qalmış ?results_year= siyahını SƏSSİZCƏ boşaltmasın deyə
    # orada nəzərə alınmır (əl ilə qurulmuş linklərə qarşı müdafiə).
    academic_only = bool(year or season) and filter_type in {"all", "academic"}
    now = timezone.now()
    review_cutoff = now - REVIEW_EDIT_WINDOW
    profile_results_url = _append_query_params(
        reverse("accounts:profile"),
        section="my-results",
        results_type=filter_type,
    )

    scoped_exams = _tenant_scoped_exams(request)
    scoped_courses = _tenant_scoped_courses(request)
    scoped_exam_ids = scoped_exams.values_list("id", flat=True)
    scoped_course_ids = scoped_courses.values_list("id", flat=True)

    items = []
    counts = {"exams": 0, "courses": 0, "labs": 0, "independent": 0, "academic": 0}

    if filter_type in {"all", "exams"} and not academic_only:
        attempts = (
            ExamAttempt.objects.filter(
                user=user,
                exam_id__in=scoped_exam_ids,
                exam__results_hidden_from_students=False,
                status__in=["submitted", "expired"],
            )
            .select_related("exam")
            # Perf: test ballarının hesablanması üçün cavablar lazımdır —
            # prefetch olmadan hər attempt 3-4 əlavə sorğu (N+1) yaradır.
            .prefetch_related("answers__question__options", "answers__selected_options")
            .order_by("-started_at")
        )
        attempts = list(attempts)
        attach_attempt_interventions(attempts)
        # Apellyasiya bonusları (tək sorğu) — tələbənin görəcəyi balda yalnız
        # 5 dəqiqəlik reviewer redaktə pəncərəsi bağlanandan sonra əks olunsun.
        try:
            from apps.appeals.public import apply_bonus_to_test_result, student_visible_appeal_bonus_map

            _appeal_bonus_by_attempt = student_visible_appeal_bonus_map([a.id for a in attempts])
        except Exception:
            _appeal_bonus_by_attempt, apply_bonus_to_test_result = {}, None
        for attempt in attempts:
            is_auto_test = attempt.exam.exam_type == "test"
            if (
                not is_auto_test
                and attempt.checked_by_teacher
                and attempt.teacher_checked_at
                and not _is_result_visible_to_student(attempt.teacher_checked_at)
            ):
                continue

            # "Bal" qutusunda əsas dəyər BAL-dır (bal / maks bal); faiz ayrıca
            # göstərilir (əvvəl test imtahanında faiz "Bal" kimi çıxırdı).
            score_value = attempt.teacher_score
            score_percent_value = ""
            if score_value is None and is_auto_test:
                test_result = calculate_test_attempt_result(attempt, answers=attempt.answers.all())
                _bonus = _appeal_bonus_by_attempt.get(attempt.id)
                if _bonus and apply_bonus_to_test_result is not None:
                    test_result = apply_bonus_to_test_result(test_result, _bonus)
                if test_result.delivered_count > 0:
                    score_value = f"{test_result.score_display} / {test_result.max_score_display}"
                    score_percent_value = f"{test_result.percentage_display}%"

            is_graded_visible = attempt.checked_by_teacher or score_value is not None
            items.append(
                {
                    "category": "exams",
                    "title": attempt.exam.title,
                    "kind": attempt.exam.get_exam_type_display() or pgettext_lazy("accounts.my_results.kind", "exam"),
                    "icon": _standard_item_type_meta("exams")[1],
                    "type_label": _standard_item_type_meta("exams")[0],
                    "submitted_at": attempt.finished_at or attempt.started_at,
                    "status": _result_status_badge(
                        attempt.status,
                        is_graded=is_graded_visible,
                    ),
                    "status_raw": attempt.get_status_display(),
                    "score": score_value if is_graded_visible else None,
                    "score_percent": score_percent_value if is_graded_visible else "",
                    "feedback": attempt.teacher_feedback if is_graded_visible else "",
                    "removed_from_exam": attempt.exam_intervention["is_terminal"],
                    "removal_reason": attempt.exam_intervention["reason"],
                    "detail_url": _append_query_params(
                        reverse(
                            "exams:exam_result",
                            kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id},
                        ),
                        from_section="my-results",
                        return_to=profile_results_url,
                        results_type=filter_type,
                    ),
                }
            )
            counts["exams"] += 1

    if filter_type in {"all", "courses"} and not academic_only:
        assignment_submissions = (
            Submission.objects.filter(
                user=user,
                assignment__course_id__in=scoped_course_ids,
            )
            .select_related("assignment", "assignment__course")
            .order_by("-submitted_at")
        )
        for submission in assignment_submissions:
            if (
                submission.status == "graded"
                and submission.graded_at
                and not _is_result_visible_to_student(submission.graded_at)
            ):
                continue

            is_graded_visible = submission.status == "graded" and (
                not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
            )
            items.append(
                {
                    "category": "courses",
                    "title": submission.assignment.title,
                    "kind": submission.assignment.course.title,
                    "icon": _standard_item_type_meta("assignments")[1],
                    "type_label": _standard_item_type_meta("assignments")[0],
                    "submitted_at": submission.submitted_at,
                    "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
                    "status_raw": submission.get_status_display(),
                    "score": submission.grade if is_graded_visible else None,
                    "feedback": submission.feedback if is_graded_visible else "",
                    "detail_url": _append_query_params(
                        reverse(
                            "accounts:my_result_detail",
                            kwargs={"item_type": "courses", "item_id": submission.id},
                        ),
                        results_type=filter_type,
                    ),
                }
            )
            counts["courses"] += 1

    if filter_type in {"all", "labs"} and not academic_only:
        lab_submissions = (
            LabSubmission.objects.filter(
                assignment__student=user,
                assignment__lab__course_id__in=scoped_course_ids,
            )
            .select_related("assignment", "assignment__lab", "assignment__lab__course")
            .order_by("-submitted_at")
        )
        for submission in lab_submissions:
            if (
                submission.status == "graded"
                and submission.graded_at
                and not _is_result_visible_to_student(submission.graded_at)
            ):
                continue

            is_graded_visible = submission.status == "graded" and (
                not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
            )
            items.append(
                {
                    "category": "labs",
                    "title": submission.assignment.lab.title,
                    "kind": submission.assignment.lab.course.title,
                    "icon": _standard_item_type_meta("labs")[1],
                    "type_label": _standard_item_type_meta("labs")[0],
                    "submitted_at": submission.submitted_at,
                    "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
                    "status_raw": submission.get_status_display(),
                    "score": submission.score if is_graded_visible else None,
                    "feedback": submission.feedback if is_graded_visible else "",
                    "detail_url": _append_query_params(
                        reverse(
                            "accounts:my_result_detail",
                            kwargs={"item_type": "labs", "item_id": submission.id},
                        ),
                        results_type=filter_type,
                    ),
                }
            )
            counts["labs"] += 1

    if filter_type in {"all", "independent"} and not academic_only:
        project_submissions = (
            ProjectSubmission.objects.filter(
                student=user,
                project__course_id__in=scoped_course_ids,
            )
            .select_related("project", "project__course")
            .order_by("-submitted_at")
        )
        for submission in project_submissions:
            if (
                submission.status == "graded"
                and submission.graded_at
                and not _is_result_visible_to_student(submission.graded_at)
            ):
                continue

            is_graded_visible = submission.status == "graded" and (
                not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
            )
            items.append(
                {
                    "category": "independent",
                    "title": submission.project.title,
                    "kind": submission.project.course.title,
                    "icon": _standard_item_type_meta("independent")[1],
                    "type_label": _standard_item_type_meta("independent")[0],
                    "submitted_at": submission.submitted_at,
                    "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
                    "status_raw": submission.get_status_display(),
                    "score": submission.grade if is_graded_visible else None,
                    "feedback": submission.feedback if is_graded_visible else "",
                    "detail_url": _append_query_params(
                        reverse(
                            "accounts:my_result_detail",
                            kwargs={"item_type": "independent", "item_id": submission.id},
                        ),
                        results_type=filter_type,
                    ),
                }
            )
            counts["independent"] += 1

    if filter_type in {"all", "academic"}:
        # Akademik (jurnal) fənn nəticələri — köçürülmüş tələbənin BÜTÜN tarixçəsi
        # buradan gəlir. Hesablama registrar fasadındadır; burada yalnız sayılır.
        academic_items = collect_academic_items(request, year=year, season=season)
        items.extend(academic_items)
        counts["academic"] = len(academic_items)

    # Akademik sətirdə `submitted_at` yoxdur (semestr etiketi göstərilir), ona görə
    # sıralama açarı `sort_at`-dır — semestrin bitmə tarixi. `timezone.now()` ilə
    # eyni awareness-də qurulur, əks halda naive/aware müqayisəsi TypeError verər.
    items.sort(key=lambda item: item.get("sort_at") or item["submitted_at"] or now, reverse=True)

    search_query = (search or "").strip()
    if search_query:
        search_lower = search_query.lower()
        items = [
            item
            for item in items
            if search_lower in (item.get("title") or "").lower()
            or search_lower in (item.get("kind") or "").lower()
            or search_lower in (item.get("type_label") or "").lower()
        ]

    # Tab sayğacları HƏMİŞƏ tam (süzgəcsiz) rəqəmi göstərməlidir ki, istifadəçi
    # digər tabın boş olub-olmadığını görsün. İl/semestr süzgəci yalnız SİYAHINI
    # daraldır, sayğacları yox — ona görə `academic_only` halında da yenidən yığılır.
    if filter_type != "all" or academic_only:
        counts = {
            "academic": count_academic_items(request),
            "exams": ExamAttempt.objects.filter(
                user=user,
                exam_id__in=scoped_exam_ids,
                exam__results_hidden_from_students=False,
                status__in=["submitted", "expired"],
            )
            .filter(
                Q(exam__exam_type="test")
                | Q(checked_by_teacher=False)
                | Q(checked_by_teacher=True, teacher_checked_at__isnull=True)
                | Q(checked_by_teacher=True, teacher_checked_at__lte=review_cutoff)
            )
            .count(),
            "courses": Submission.objects.filter(
                user=user,
                assignment__course_id__in=scoped_course_ids,
            )
            .exclude(status="graded", graded_at__gt=review_cutoff)
            .count(),
            "labs": LabSubmission.objects.filter(
                assignment__student=user,
                assignment__lab__course_id__in=scoped_course_ids,
            )
            .exclude(status="graded", graded_at__gt=review_cutoff)
            .count(),
            "independent": ProjectSubmission.objects.filter(
                student=user,
                project__course_id__in=scoped_course_ids,
            )
            .exclude(status="graded", graded_at__gt=review_cutoff)
            .count(),
        }
    counts["all"] = counts["exams"] + counts["courses"] + counts["labs"] + counts["independent"] + counts["academic"]

    return items, counts, filter_type
