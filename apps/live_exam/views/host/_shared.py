"""live_exam host paketi — _shared."""

from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.models import ExamQuestion
from apps.live_exam.domain.session import get_total_questions
from apps.live_exam.models import LiveSession
from apps.live_exam.session_settings import allowed_max_participants_for_user, get_session_settings
from apps.live_exam.transport import build_join_url
from core.permissions import request_has_permission


def _ensure_host_org_permission(request, exam_organization) -> None:
    """
    Enforce organization-level RBAC for all host endpoints.

    Checks (in order):
    1. An active organization context exists in the request.
    2. The exam's organization matches the request's active organization.
    3. The organization is not suspended or inactive.
    4. The requesting user holds the ``exam.host`` permission, or the broader
       ``exam.manage`` permission.

    Raises ``PermissionDenied`` on any violation.
    """
    org = getattr(request, "organization", None)
    if org is None:
        raise PermissionDenied(pgettext("live_exam.view.permission", "org_context_required"))

    if exam_organization is None or org.id != exam_organization.id:
        raise PermissionDenied(pgettext("live_exam.view.permission", "cross_org_access_denied"))

    if org.is_suspended:
        raise PermissionDenied(pgettext("live_exam.view.permission", "org_suspended_or_inactive"))

    if not (request_has_permission(request, "exam.host") or request_has_permission(request, "exam.manage")):
        raise PermissionDenied(pgettext("live_exam.view.permission", "exam_manage_required"))


def _host_session_context(request, session: LiveSession, *, auto_fullscreen: str = "0") -> dict[str, object]:
    exam_total = ExamQuestion.objects.filter(exam=session.exam).count()
    selected = get_total_questions(session)
    if exam_total > 0:
        selected = max(1, min(selected, exam_total))
    else:
        selected = 0

    session_settings = get_session_settings(session)

    return {
        "session": session,
        "entry_url": build_join_url(request, session),
        "qr_url": reverse("liveExam:qr_png", kwargs={"pin": session.pin}),
        "total_questions": selected,
        "exam_total_questions": exam_total,
        "selected_total_questions": selected,
        "session_settings": session_settings,
        "session_locked": bool(session.is_locked),
        "max_participants_cap": allowed_max_participants_for_user(request.user),
        "auto_fullscreen": auto_fullscreen,
    }
