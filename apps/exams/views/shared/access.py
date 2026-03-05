from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.exams.models import Exam
from apps.exams.services.attempts import _start_or_resume_attempt
from apps.exams.views.shared.tenant import tenant_scoped_exams


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


def _resolve_exam_failure_redirect(request):
    explicit_next = _safe_same_origin_redirect_path(request, request.POST.get("next") or request.GET.get("next"))
    if explicit_next:
        return explicit_next

    source_section = (request.POST.get("from_section") or request.GET.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        assigned_type = (request.POST.get("assigned_type") or request.GET.get("assigned_type") or "all").strip().lower()
        allowed_types = {"all", "exams", "courses", "assignments", "labs", "independent"}
        if assigned_type not in allowed_types:
            assigned_type = "all"
        return f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type={assigned_type}"

    return reverse("exams:student_exam_list")


@login_required
@require_POST
def exam_code_check(request):
    slug = request.POST.get("exam_slug")
    code = (request.POST.get("access_code") or "").strip()

    exam = get_object_or_404(tenant_scoped_exams(request, Exam.objects.filter(is_active=True)), slug=slug)

    can_start, reason = exam.can_user_start(request.user, code=code)
    if not can_start:
        messages.error(request, reason or pgettext("exams.view.access.message", "exam_start_failed"))
        return redirect(_resolve_exam_failure_redirect(request))

    if not exam.questions.exists():
        messages.error(request, pgettext("exams.view.access.message", "exam_has_no_questions"))
        return redirect(_resolve_exam_failure_redirect(request))

    return _start_or_resume_attempt(request, exam)
