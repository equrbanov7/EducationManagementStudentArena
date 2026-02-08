
from pyexpat.errors import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt

from exams.models import Exam
from exams.services.attempts import _start_or_resume_attempt

@csrf_exempt   # DEV üçün CSRF-dən azad edirik (sonra istəsən götürərsən)
@login_required
@require_POST
def exam_code_check(request):
    slug = request.POST.get("exam_slug")
    code = (request.POST.get("access_code") or "").strip()

    exam = get_object_or_404(Exam, slug=slug, is_active=True)

    can_start, reason = exam.can_user_start(request.user, code=code)
    if not can_start:
        messages.error(request, reason or "İmtahana başlamaq mümkün olmadı.")
        return redirect("student_exam_list")

    return _start_or_resume_attempt(request, exam)