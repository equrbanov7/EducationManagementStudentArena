"""
Dashboard role dispatcher.
"""

from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course
from apps.exams.models import Exam, ExamAttempt
from apps.labs.models import LabAnswer, LabSubmission
from apps.projects.models import ProjectSubmission
from apps.task_submission_core.review import resolve_identity_window as resolve_submission_identity_window
from core.tenancy import restore_request_organization_from_profile

from .._dashboard_helpers import _collect_my_results
from .._helpers import (
    REVIEW_EDIT_WINDOW,
    REVIEW_EDIT_WINDOW_MINUTES,
    _append_query_params,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _extract_assignment_attachments,
    _is_result_visible_to_student,
    _is_review_window_closed,
    _normalize_pending_answers_filter,
    _normalize_results_filter,
    _normalize_review_result_item_type,
    _parse_decimal_score,
    _pending_review_type_label,
    _query_string,
    _render_profile_section,
    _result_status_badge,
    _review_window_seconds_left,
    _role_capabilities,
    _safe_same_origin_redirect_path,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)

User = get_user_model()


@login_required
def dashboard(request):
    """Redirect users to the dashboard variant that matches their role."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if capabilities["can_review_submissions"]:
        return redirect("accounts:teacher_dashboard")
    return redirect("accounts:student_dashboard")
