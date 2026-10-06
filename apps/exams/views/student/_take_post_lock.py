"""Tələbə imtahan POST-u (autosave / save_draft / finish) — TƏK kilidli giriş yolu.

Perf 2026-10-06 (1000 eyni-anlı tələbə yük testi, autosave ~25 sorğu): əvvəl
``take_exam`` attempt-i kilidsiz yükləyib giriş yoxlamasını (exclusion EXISTS,
final-mərkəz giriş sessiyası) və vaxt/nəzarət bağlanmalarını edir, sonra
``_handle_take_exam_post`` həmin attempt-i ``FOR UPDATE`` ilə YENİDƏN yükləyib
giriş yoxlamasını TƏKRARLAYIRDI. İndi POST attempt-i bir dəfə — eyni tenant/slug/
sahiblik filtrləri ilə, sətir kilidi altında — yükləyir və köhnə yolun bütün
yoxlamalarını həmin kilid altında, eyni ardıcıllıqla BİR dəfə edir:

1. giriş qapısı (EXAM-P1-02/03: deaktiv/arxiv/silinmiş imtahan, exclusion —
   exclusion eyni SELECT-də ``EXISTS`` annotasiyasıdır) + final-mərkəz giriş
   sessiyası (etibarsızdırsa tranzaksiyadan KƏNARDA çıxış + 403, köhnə kimi);
2. EX-05 / EX28-04 / EX28-07: yazı pəncərəsi ``now − grace``-dən əvvəl bağlanıbsa
   cəhd «expired» bağlanır (müəllimin əl kilidində yox) — əvvəl bu addım kilidsiz idi;
3. nəzarət resume pəncərəsi bitibsə auto-finish; bitmiş cəhd → nəticə yönləndirməsi;
4. «resumed» → «active»; EXAMQA 2026-10-01: nəzarət kilidi → 423;
5. EXAM-P1-06 OCC (stale tab → 409, idempotent replay), sonra ``write_answers``
   (kilid altında deadline/``is_time_up``, yazılar, revision, finish).

EX-09: ``of=("self",)`` — JOIN-lənmiş ``exams_exam`` sətri kilidlənmir.
Kodlaşdırma (coding) imtahanı və tapılmayan attempt üçün ``None`` qaytarılır —
``take_exam`` köhnə yola (404 / coding səhifəsi) düşür.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext

from apps.exams.features import exam_supervision_enabled
from apps.exams.models import ExamAttempt
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._helpers import append_return_to, autosave_occ_conflict_response, build_exam_result_url, current_return_to
from .access_guard import (
    USER_EXCLUDED_ANNOTATION,
    active_attempt_access_denial_reason,
    final_entry_session_revoked,
    revoke_final_entry_session,
    user_exclusion_annotation,
)


def is_ajax_request(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def finished_attempt_response(request, attempt, *, return_to):
    redirect_url = build_exam_result_url(attempt, return_to=return_to)
    if is_ajax_request(request):
        return JsonResponse(
            {
                "success": True,
                "finished": True,
                "already_finished": True,
                "redirect_url": redirect_url,
            }
        )
    return redirect(redirect_url)


def supervision_locked_response(request, attempt, *, return_to):
    message = pgettext(
        "exams.view.access.message",
        "İmtahanınız nəzarətçi tərəfindən dayandırılıb — kilid açılana qədər cavablar qəbul edilmir.",
    )
    if is_ajax_request(request):
        return JsonResponse({"success": False, "locked": True, "error": message}, status=423)
    messages.error(request, message)
    return redirect(
        append_return_to(
            reverse("exams:take_exam", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id}), return_to
        )
    )


class _EntrySessionRevoked(Exception):
    """Kilid altında aşkarlanır; çıxış (logout) tranzaksiyadan kənarda edilir."""


def _load_locked_attempt(request, *, slug, attempt_id, action):
    # Finish/save_draft bildiriş göndərir (müəllif + tələbə adı) — onlar üçün
    # müəllif/istifadəçi eyni SELECT-də gəlir; autosave-də lazım deyil.
    related = ("exam",) if action == "autosave" else ("exam", "exam__author", "user")
    queryset = (
        ExamAttempt.objects.select_for_update(of=("self",))
        .select_related(*related)
        .annotate(**user_exclusion_annotation(request.user))
        .filter(exam__in=tenant_scoped_exams(request), exam__slug=slug, user=request.user)
        .exclude(exam__exam_type="coding")
    )
    try:
        return queryset.get(id=attempt_id)
    except ExamAttempt.DoesNotExist:
        return None


def run_locked_take_exam_post(request, *, slug, attempt_id, write_answers):
    """Kilidli POST yolu; ``None`` → çağıran köhnə (GET/coding) yola düşür."""
    try:
        return _run_locked(request, slug=slug, attempt_id=attempt_id, write_answers=write_answers)
    except _EntrySessionRevoked:
        revoke_final_entry_session(request)


def _run_locked(request, *, slug, attempt_id, write_answers):
    action = (request.POST.get("submit_action") or "").strip()
    is_ajax = is_ajax_request(request)
    return_to = current_return_to(request)

    with transaction.atomic():
        attempt = _load_locked_attempt(request, slug=slug, attempt_id=attempt_id, action=action)
        if attempt is None:
            return None

        # (1) Tək, avtoritativ giriş yoxlaması — kilid altında.
        reason = active_attempt_access_denial_reason(
            attempt, request.user, user_excluded=getattr(attempt, USER_EXCLUDED_ANNOTATION)
        )
        if reason:
            raise PermissionDenied(reason)
        if final_entry_session_revoked(request, attempt):
            raise _EntrySessionRevoked

        supervision_enabled = exam_supervision_enabled()
        is_manual_supervision_lock = bool(
            supervision_enabled and attempt.supervision_manual_lock and attempt.supervision_status == "locked"
        )
        # (2) Audit 2026-09-13 EX-05 / 2026-09-28 EX28-04, EX28-07: grace pəncərəsi
        # daxilindəki yazı aşağıda `is_time_up` ilə saxlanıb «expired» olur; grace
        # keçibsə cəhd burada (gövdə oxunmadan) bağlanır.
        if not is_manual_supervision_lock:
            attempt.expire_if_write_window_closed()
        # (3) Resume pəncərəsi tələbə qayıtmadan bitibsə — indi bitir.
        if supervision_enabled:
            attempt.expire_if_resume_window_expired()
        if attempt.is_finished:
            return finished_attempt_response(request, attempt, return_to=return_to)

        # (4) Tələbə həqiqətən imtahana qayıdıb → «resumed» halını təmizlə ki,
        # periodik sweep aktiv tələbəni auto-finish etməsin.
        if supervision_enabled and attempt.supervision_status == "resumed":
            from apps.exams.services.supervision import mark_student_returned

            mark_student_returned(attempt)

        # EXAMQA 2026-10-01: nəzarət kilidi (pozuntu limiti və ya nəzarətçinin
        # «dayandır»-ı) yalnız klient overlay-i idi — overlay-i DevTools ilə silən
        # tələbə kilid altında cavab yaza / təhvil verə bilirdi. Kilidli cəhdə
        # yazı qəbul olunmur (423); klient lokal draft-ı saxlayır və kilid
        # açılandan (resumed) sonra növbəti autosave ilə göndərir.
        if supervision_enabled and attempt.supervision_status == "locked":
            return supervision_locked_response(request, attempt, return_to=return_to)

        # (5) EXAM-P1-06: autosave/finish optimistic concurrency — stale tab yazısı
        # 409 alır (helper-də; base_revision yoxdursa geriyə-uyğun).
        occ_conflict = autosave_occ_conflict_response(request, attempt, action)
        if occ_conflict is not None:
            return occ_conflict

        return write_answers(request, attempt=attempt, action=action, is_ajax=is_ajax, return_to=return_to)


__all__ = [
    "finished_attempt_response",
    "is_ajax_request",
    "run_locked_take_exam_post",
    "supervision_locked_response",
]
