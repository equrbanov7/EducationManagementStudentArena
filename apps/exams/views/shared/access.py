from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import Exam
from apps.exams.services.attempts import _start_or_resume_attempt
from apps.exams.views.shared.tenant import tenant_scoped_exams


@login_required
@require_POST
def exam_code_check(request):
    slug = request.POST.get("exam_slug")
    code = (request.POST.get("access_code") or "").strip()

    exam = get_object_or_404(tenant_scoped_exams(request, Exam.objects.filter(is_active=True)), slug=slug)

    can_start, reason = exam.can_user_start(request.user, code=code)
    if not can_start:
        messages.error(request, reason or pgettext("exams.view.access.message", "exam_start_failed"))
        return redirect("exams:student_exam_list")

    return _start_or_resume_attempt(request, exam)
