from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from django.db.models import Q
from django.utils import timezone

from core.helpers import REVIEW_EDIT_LOCK_WINDOW


@dataclass(frozen=True)
class SubmissionFilterState:
    search_query: str
    status_filter: str
    date_from_raw: str
    date_to_raw: str


def annotate_student_review_state(submissions, *, current_time=None):
    now = current_time or timezone.now()
    prepared_submissions = []

    for submission in submissions:
        submission.has_grade = submission.grade is not None
        submission.show_review_data = submission.status == "graded" and (
            not submission.graded_at or now >= submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
        )
        submission.review_available_in_seconds = 0
        if submission.status == "graded" and submission.graded_at and not submission.show_review_data:
            reveal_at = submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
            submission.review_available_in_seconds = max(0, int((reveal_at - now).total_seconds()))
        prepared_submissions.append(submission)

    return prepared_submissions


def parse_filter_date(raw_value):
    raw_date = (raw_value or "").strip()
    if not raw_date:
        return "", None
    try:
        return raw_date, datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return "", None


def resolve_recheck_window(submission, *, current_time=None):
    if submission.status != "graded" or not submission.graded_at:
        return False, 0

    now = current_time or timezone.now()
    reveal_at = submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
    if now >= reveal_at:
        return False, 0

    return True, max(0, int((reveal_at - now).total_seconds()))


def resolve_identity_window(submission, *, current_time=None):
    now = current_time or timezone.now()

    # Identity is always hidden while the submission has not been graded yet.
    # There is no time-based reveal for pending submissions — the teacher must
    # never see the student's name before the re-check window has closed.
    if submission.status != "graded" or not submission.graded_at:
        return True, 0

    # Once graded, hide identity until the re-check window closes.
    reveal_at = submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
    if now >= reveal_at:
        return False, 0

    return True, max(0, int((reveal_at - now).total_seconds()))


def format_input_number(value):
    if value in (None, ""):
        return ""
    normalized = str(value).replace(",", ".")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def apply_submission_filters(submissions, params, *, student_lookup_prefix, allowed_status_filters):
    search_query = (params.get("q") or "").strip()
    if search_query:
        submissions = submissions.filter(
            Q(**{f"{student_lookup_prefix}__username__icontains": search_query})
            | Q(**{f"{student_lookup_prefix}__first_name__icontains": search_query})
            | Q(**{f"{student_lookup_prefix}__last_name__icontains": search_query})
            | Q(content__icontains=search_query)
        )

    status_filter = (params.get("status") or "all").strip().lower()
    if status_filter not in allowed_status_filters:
        status_filter = "all"
    if status_filter != "all":
        submissions = submissions.filter(status=status_filter)

    date_from_raw, date_from = parse_filter_date(params.get("date_from"))
    date_to_raw, date_to = parse_filter_date(params.get("date_to"))
    if date_from:
        submissions = submissions.filter(submitted_at__date__gte=date_from)
    if date_to:
        submissions = submissions.filter(submitted_at__date__lte=date_to)

    return submissions, SubmissionFilterState(
        search_query=search_query,
        status_filter=status_filter,
        date_from_raw=date_from_raw,
        date_to_raw=date_to_raw,
    )


def build_pagination_query(*, filters, selected_submission_id, from_section="", return_to=""):
    return urlencode(
        {
            key: value
            for key, value in {
                "q": filters.search_query,
                "status": filters.status_filter,
                "date_from": filters.date_from_raw,
                "date_to": filters.date_to_raw,
                "submission": selected_submission_id,
                "from_section": (from_section or "").strip(),
                "return_to": (return_to or "").strip(),
            }.items()
            if value not in ("", None)
        }
    )


def annotate_teacher_review_state(submissions, *, student_attr, current_time=None):
    now = current_time or timezone.now()

    for submission in submissions:
        student = getattr(submission, student_attr)
        in_recheck_window, review_window_seconds_left = resolve_recheck_window(submission, current_time=now)
        is_identity_hidden, identity_window_seconds_left = resolve_identity_window(submission, current_time=now)

        submission.in_recheck_window = in_recheck_window
        submission.review_window_seconds_left = review_window_seconds_left
        submission.identity_window_seconds_left = identity_window_seconds_left
        submission.can_view_student_identity = not is_identity_hidden
        submission.student_display_name = (
            student.get_full_name() or student.username if submission.can_view_student_identity else "Anonim tələbə"
        )
        submission.student_display_meta = (
            f"@{student.username}" if submission.can_view_student_identity else "Anonim görünüş"
        )
        submission.grade_input_value = format_input_number(submission.grade)
        submission.review_action_label = (
            "Yenidən yoxla" if in_recheck_window else ("Bax" if submission.status == "graded" else "Yoxla")
        )
        submission.review_action_variant = (
            "warning" if in_recheck_window else ("secondary" if submission.status == "graded" else "primary")
        )
        submission.can_edit_review = submission.status != "graded" or in_recheck_window
        submission.review_countdown_seconds = (
            review_window_seconds_left if in_recheck_window else identity_window_seconds_left
        )
        submission.review_countdown_mode = "recheck" if in_recheck_window else (
            "identity" if identity_window_seconds_left > 0 else ""
        )

    return submissions

