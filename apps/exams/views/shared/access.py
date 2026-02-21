from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.exams.models import Exam
from apps.exams.services.attempts import _start_or_resume_attempt
from apps.exams.views.shared.tenant import exam_in_active_tenant


@csrf_exempt  # DEV üçün CSRF-dən azad edirik (sonra istəsən götürərsən)
@login_required
@require_POST
def exam_code_check(request):
    slug = request.POST.get("exam_slug")
    code = (request.POST.get("access_code") or "").strip()

    exam = get_object_or_404(Exam, slug=slug, is_active=True)
    if not exam_in_active_tenant(request, exam):
        messages.error(request, "Bu imtahana giriş icazəniz yoxdur.")
        return redirect("exams:student_exam_list")

    can_start, reason = exam.can_user_start(request.user, code=code)
    if not can_start:
        messages.error(request, reason or "İmtahana başlamaq mümkün olmadı.")
        return redirect("exams:student_exam_list")

    return _start_or_resume_attempt(request, exam)
