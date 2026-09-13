from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import Exam
from apps.exams.services.attempts import (
    _start_or_resume_attempt,
    get_attempt_limit_result_redirect_url,
    get_effective_max_attempts,
)
from apps.exams.views.shared.tenant import tenant_scoped_exams
from apps.exams.views.student._helpers import ensure_student_exam_tenant_context


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


def _is_ajax_request(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _json_redirect_response(response):
    redirect_url = response.get("Location") if hasattr(response, "get") else ""
    return JsonResponse({"success": True, "redirect_url": redirect_url})


def _code_check_failure(request, message, *, status=400):
    if _is_ajax_request(request):
        return JsonResponse({"success": False, "error": message}, status=status)
    messages.error(request, message)
    return redirect(_resolve_exam_failure_redirect(request))


@login_required
@require_POST
def exam_code_check(request):
    ensure_student_exam_tenant_context(request)
    slug = request.POST.get("exam_slug")
    code = (request.POST.get("access_code") or "").strip()

    exam = get_object_or_404(tenant_scoped_exams(request, Exam.objects.filter(is_active=True)), slug=slug)

    # Audit 2026-09-13 EX-03 (P1): PIN/kod brute-force — `/exams/final/`-dəki
    # istifadəçi-adı əsaslı sürüşən pəncərə limiti (EXAM-SEC-002) bu yolda
    # tətbiq olunmurdu (30 səhv PIN → 30×400, hər biri PBKDF2). Eyni açar
    # işlədilir ki, iki yol bir-birinin limitini yan keçə bilməsin.
    if code:
        from apps.exams.services.student_pins import student_pin_login_rate_limited

        if student_pin_login_rate_limited(request.user.get_username()):
            return _code_check_failure(
                request,
                pgettext("exams.final_center.entry", "Çox sayda cəhd — bir dəqiqə sonra yenidən yoxlayın."),
                status=429,
            )

    # Audit 2026-09-13 EX-02 (P1): final imtahanı YALNIZ imtahan mərkəzi axını
    # ilə (`/exams/final/` — zal kompüteri qapısı, bilet/gözləmə otağı,
    # nəzarətçi start-ı) başlaya bilər; kabinet modalı final üçün kod xanası
    # göstərmir (`assigned_tasks.py`). Bu endpoint isə kabinetdə görünən PIN
    # ilə həmin qapıların hamısını keçib istənilən IP-dən cəhd yaradırdı.
    # Müəllif «Sınaq keç» yolu (is_trial) `start_exam`-dan gedir — burada
    # istisna lazım deyil.
    if getattr(exam, "exam_type_extended", None) == "final" and request.user != exam.author:
        return _code_check_failure(
            request,
            pgettext("exams.view.access.message", "final_exam_requires_center_entry"),
        )

    can_start, reason = exam.can_user_start(request.user, code=code)
    if not can_start:
        attempt_limit_result_url = get_attempt_limit_result_redirect_url(request, exam, request.user)
        if attempt_limit_result_url:
            # Effektiv limit = qlobal + tələbəyə verilmiş qrant(lar).
            effective_max = get_effective_max_attempts(exam, request.user) or exam.max_attempts_per_user
            if _is_ajax_request(request):
                return JsonResponse(
                    {
                        "success": False,
                        "error": pgettext("exams.service.attempt.message", "max_attempts_reached").format(
                            max_attempts=effective_max
                        ),
                        "redirect_url": attempt_limit_result_url,
                    },
                    status=400,
                )
            messages.info(
                request,
                pgettext("exams.service.attempt.message", "max_attempts_reached").format(max_attempts=effective_max),
            )
            return redirect(attempt_limit_result_url)
        if _is_ajax_request(request):
            return JsonResponse(
                {"success": False, "error": reason or pgettext("exams.view.access.message", "exam_start_failed")},
                status=400,
            )
        messages.error(request, reason or pgettext("exams.view.access.message", "exam_start_failed"))
        return redirect(_resolve_exam_failure_redirect(request))

    if not exam.questions.filter(is_active=True).exists():
        if _is_ajax_request(request):
            return JsonResponse(
                {"success": False, "error": pgettext("exams.view.access.message", "exam_has_no_questions")},
                status=400,
            )
        messages.error(request, pgettext("exams.view.access.message", "exam_has_no_questions"))
        return redirect(_resolve_exam_failure_redirect(request))

    response = _start_or_resume_attempt(request, exam)
    if _is_ajax_request(request):
        return _json_redirect_response(response)
    return response
