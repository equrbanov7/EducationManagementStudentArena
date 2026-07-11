"""results paketi — daxili köməkçilər və sabitlər (view-suz məntiq)."""

from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit

from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext

from apps.exams.models import ExamAnswer
from apps.exams.services.ai_grading import has_ai_gradeable_answer_content, has_written_answer_content
from apps.exams.services.manual_grading import answer_max_points as _answer_max_points

ANONYMOUS_NAME_TOKEN_SALT = "exams.teacher_results.anonymous_name"  # nosec B105


ANONYMOUS_NAME_CODE_LENGTH = 6


def _user_display_name(user):
    return user.get_full_name() or user.username


def _coding_submission_file_items(submission):
    if not submission:
        return []
    code_files = list(submission.code_files.all())
    if code_files:
        return [
            {
                "name": code_file.name,
                "content": code_file.content or "",
                "language": code_file.language or "",
                "is_main": bool(code_file.is_main),
            }
            for code_file in code_files
        ]
    return [
        {
            "name": item.get("name") or "file.txt",
            "content": item.get("content") or "",
            "language": item.get("language") or "",
            "is_main": bool(item.get("is_main")),
        }
        for item in (submission.files or [])
        if isinstance(item, dict)
    ]


def _sync_coding_answers_from_final_submissions(attempt):
    if getattr(attempt.exam, "exam_type", "") != "coding":
        return

    seen_question_ids = set()
    submissions = (
        attempt.coding_submissions.filter(is_final=True)
        .select_related("question", "question__question")
        .order_by("question__question__order", "question__question_id", "-submitted_at", "-id")
    )
    for submission in submissions:
        base_question = getattr(submission.question, "question", None)
        if not base_question or base_question.id in seen_question_ids:
            continue
        seen_question_ids.add(base_question.id)

        answer, created = ExamAnswer.objects.get_or_create(
            attempt=attempt,
            question=base_question,
            defaults={"text_answer": submission.submitted_code or ""},
        )
        if not created and not (answer.text_answer or "").strip() and submission.submitted_code:
            answer.text_answer = submission.submitted_code
            answer.save(update_fields=["text_answer", "updated_at"])


def _build_answer_review_item(answer):
    answer_files = list(answer.files.all())
    has_text_answer = bool((getattr(answer, "text_answer", "") or "").strip())
    has_paint_answer = bool(getattr(answer, "paint_image", None)) or bool(getattr(answer, "has_paint", False))
    has_file_answer = bool(answer_files)
    selected_options_count = len(list(answer.selected_options.all()))
    has_answer_content = has_written_answer_content(
        student_answer=answer.text_answer,
        answer_files=answer_files,
        paint_image=getattr(answer, "paint_image", None),
    )

    coding_submission = None
    if getattr(answer.question.exam, "exam_type", "") == "coding":
        coding_submission = (
            answer.attempt.coding_submissions.filter(question__question=answer.question, is_final=True)
            .prefetch_related("code_files")
            .order_by("-submitted_at")
            .first()
        )
    coding_files = _coding_submission_file_items(coding_submission)
    has_answer_content = has_answer_content or bool(coding_files)

    return {
        "question": answer.question,
        "answer": answer,
        "max_points": _answer_max_points(answer),
        "coding_submission": coding_submission,
        "coding_files": coding_files,
        "coding_file_count": len(coding_files),
        "answer_files": answer_files,
        "has_text_answer": has_text_answer,
        "has_paint_answer": has_paint_answer,
        "has_file_answer": has_file_answer,
        "selected_options_count": selected_options_count,
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


def _build_attempt_timing_context(attempt):
    started_at = getattr(attempt, "started_at", None)
    finished_at = getattr(attempt, "finished_at", None)
    duration_seconds = getattr(attempt, "duration_seconds", None)

    if duration_seconds is None and started_at and finished_at:
        duration_seconds = max(int((finished_at - started_at).total_seconds()), 0)

    if finished_at is None and started_at and duration_seconds is not None:
        finished_at = started_at + timedelta(seconds=duration_seconds)

    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "has_duration": duration_seconds is not None,
    }


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
            "code": "view",
            "label": pgettext("exams.teacher.results.action", "Bax"),
            "url_name": "exams:teacher_view_attempt",
            "countdown_seconds": 0,
            "countdown_mode": "",
        }

    if attempt.checked_by_teacher:
        if review_window_seconds:
            return {
                "code": "recheck",
                "label": pgettext("exams.teacher.results.action", "Yenidən yoxla"),
                "url_name": "exams:teacher_check_attempt",
                "countdown_seconds": review_window_seconds,
                "countdown_mode": "recheck",
            }
        return {
            "code": "view",
            "label": pgettext("exams.teacher.results.action", "Bax"),
            "url_name": "exams:teacher_view_attempt",
            "countdown_seconds": 0,
            "countdown_mode": "",
        }

    return {
        "code": "review",
        "label": pgettext("exams.teacher.results.action", "Yoxla"),
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


def _available_groups_for_exam(exam):
    """İmtahanın iştirakçılarının üzv olduğu qruplar + allowed_groups (tenant-scoped).

    - allowed_groups-i daxil et (təyin olunmuş qruplar).
    - Plus: imtahanın cəhdləri olan tələbələrin üzv olduqları qruplar.
    - Tenant: yalnız bu imtahanın organization-na aid qrupları göstər (əgər varsa).
    """
    from apps.exams.models import StudentGroup

    attempt_user_ids = exam.attempts.values_list("user_id", flat=True)
    qs = StudentGroup.objects.filter(Q(exams=exam) | Q(students__id__in=attempt_user_ids))
    org_id = getattr(exam, "organization_id", None)
    if org_id:
        qs = qs.filter(organization_id=org_id)
    return qs.distinct().order_by("name")


def _attempt_time_limit_seconds(attempt):
    """İmtahanın vaxt limiti (saniyə) — limit yoxdursa None."""
    duration_minutes = getattr(attempt.exam, "total_duration_minutes", None)
    if not duration_minutes:
        return None
    return int(duration_minutes) * 60


def _attempt_effective_finish(attempt, *, now=None):
    """İmtahanı bitirməyən tələbə üçün effektiv bitmə vaxtı.

    - Əgər finished_at varsa və limiti aşmırsa, onu qaytarır.
    - finished_at limitdən SONRADIRSA (gecikmiş lazy expire ilə yazılmış köhnə
      sətirlər) → deadline göstərilir ("avto" tag ilə): tələbə real olaraq
      yalnız limit qədər imtahanda ola bilərdi.
    - finished_at yoxdursa: started_at + limit (əgər müddət bitibsə).
    - Müddət hələ bitməyibsə None.
    """
    started_at = getattr(attempt, "started_at", None)
    duration_minutes = getattr(attempt.exam, "total_duration_minutes", None)
    deadline = None
    if started_at and duration_minutes:
        deadline = started_at + timedelta(minutes=int(duration_minutes))

    finished_at = getattr(attempt, "finished_at", None)
    if finished_at:
        if deadline and finished_at > deadline:
            return deadline, True
        return finished_at, False
    if deadline and (now or timezone.now()) >= deadline:
        return deadline, True
    return None, False


def _attempt_effective_duration(attempt, effective_finish):
    """Cədvəldə göstərilən müddət — imtahan limitini heç vaxt aşmır."""
    effective_duration = attempt.duration_seconds
    if effective_duration is None and effective_finish and attempt.started_at:
        effective_duration = max(int((effective_finish - attempt.started_at).total_seconds()), 0)
    if effective_duration is not None:
        limit_seconds = _attempt_time_limit_seconds(attempt)
        if limit_seconds and effective_duration > limit_seconds:
            effective_duration = limit_seconds
    return effective_duration


def _appeal_bonus_map_for(attempts):
    """Cəhdlər üçün bal-düzəliş bonus xəritəsi (M2: score_adjustments hook-u)."""
    from apps.exams import score_adjustments

    return score_adjustments.bonus_map([att.id for att in attempts])


def _apply_appeal_bonus(test_result, bonus):
    """Bonusun test nəticəsinə tətbiqi (M2: score_adjustments hook-u)."""
    from apps.exams import score_adjustments

    return score_adjustments.apply_bonus(test_result, bonus)


def _expire_overdue_attempts(exam, *, now=None):
    """Vaxt limiti keçmiş, amma hələ də 'davam edir'/'qaralama' görünən
    cəhdləri toplu şəkildə expire edir (lazy maintenance).

    Tələbə səhifəyə qayıtmayanda expire_if_time_limit_reached heç vaxt
    işləmir və cəhd siyahıda əbədi "davam edir" qalırdı. Tək bulk UPDATE —
    per-row save yoxdur.
    """
    duration_minutes = getattr(exam, "total_duration_minutes", None)
    if not duration_minutes:
        return 0
    duration_minutes = int(duration_minutes)
    cutoff = (now or timezone.now()) - timedelta(minutes=duration_minutes)
    return exam.attempts.filter(
        status__in=("in_progress", "draft"),
        started_at__lt=cutoff,
    ).update(
        status="expired",
        finished_at=F("started_at") + timedelta(minutes=duration_minutes),
        duration_seconds=duration_minutes * 60,
    )


def _apply_results_filters(exam, request):
    """Şərt: teacher_exam_results və export_exam_results_xlsx ortaq filter logic-i.

    Qaytarır: (attempts_qs, filter_state_dict)
    """
    return _apply_results_filters_from_params(exam, request.GET)


def _apply_results_filters_from_params(exam, params):
    """Filter məntiqi düz mapping üzərində — export job worker-i də çağıra bilir."""
    # Lazy expire: vaxtı keçmiş "davam edir" cəhdləri filter/siyahıdan ƏVVƏL
    # expired-ə çevir ki, status həm cədvəldə, həm filterlərdə düzgün görünsün.
    _expire_overdue_attempts(exam)

    attempts = (
        exam.attempts.exclude(is_trial=True)
        .select_related("user", "exam")
        .prefetch_related(
            "answers__question__options",
            "answers__selected_options",
        )
    )

    search_query = (params.get("q") or "").strip()
    if search_query:
        attempts = attempts.filter(
            Q(user__username__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
        )

    status_filter = (params.get("status") or "all").strip().lower()
    allowed_status_filters = {"all", "draft", "in_progress", "submitted", "expired"}
    if status_filter not in allowed_status_filters:
        status_filter = "all"
    if status_filter != "all":
        attempts = attempts.filter(status=status_filter)

    checked_filter = (params.get("checked") or "all").strip().lower()
    if checked_filter == "checked":
        attempts = attempts.filter(checked_by_teacher=True)
    elif checked_filter == "unchecked":
        attempts = attempts.filter(checked_by_teacher=False)
    else:
        checked_filter = "all"

    date_from_raw, date_from = _parse_filter_date(params.get("date_from"))
    date_to_raw, date_to = _parse_filter_date(params.get("date_to"))
    if date_from:
        attempts = attempts.filter(started_at__date__gte=date_from)
    if date_to:
        attempts = attempts.filter(started_at__date__lte=date_to)

    # Group filter — imtahanın iştirakçılarının üzvü olduğu istənilən qrupdan
    group_filter_raw = (params.get("group") or "").strip().lower()
    group_id = None
    if group_filter_raw and group_filter_raw != "all":
        try:
            group_id = int(group_filter_raw)
        except ValueError:
            group_id = None
    if group_id is not None and _available_groups_for_exam(exam).filter(id=group_id).exists():
        attempts = attempts.filter(user__student_groups_as_student__id=group_id).distinct()
    else:
        group_id = None

    sort_by = (params.get("sort_by") or "").strip()
    sort_dir = (params.get("sort_dir") or "").strip()
    ALLOWED_SORT_FIELDS = {
        "user": "user__first_name",
        "username": "user__username",
        "email": "user__email",
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

    return attempts, {
        "search_query": search_query,
        "status_filter": status_filter,
        "checked_filter": checked_filter,
        "date_from_raw": date_from_raw,
        "date_to_raw": date_to_raw,
        "group_id": group_id,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
    }
