"""exam_center paketi — canlı otaq monitoru + oturum həyat dövrü endpoint-ləri.

Bütün dəyişdirici əməliyyatlar CSRF-qorumalı POST-lardır; WS yalnız oxu
kanalıdır. İdempotentlik servis qatındakı şərti UPDATE-lərlə təmin olunur.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.exams.services.final_center import (
    HEARTBEAT_INTERVAL_SECONDS,
    RoomSessionStateError,
    TicketStateError,
    can_manage_final_center,
    cancel_session,
    end_room,
    open_entry,
    regenerate_pin,
    remove_student,
    session_monitor_snapshot,
    start_room,
)
from core.audit import log_action
from core.constants import AuditAction

from ._shared import get_center_session_or_404, get_session_ticket_or_404


@login_required
def exam_center_session_monitor(request, session_id):
    """Nəzarətçi otaq paneli — real vaxt WS + snapshot fallback."""
    _organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    snapshot = session_monitor_snapshot(session)
    return render(
        request,
        "exams/exam_center/session_monitor.html",
        {
            "session": session,
            "snapshot": snapshot,
            "ws_path": f"/ws/exams/final/room/{session.pk}/",
            "heartbeat_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "can_manage": can_manage_final_center(request.user),
        },
    )


@login_required
def exam_center_session_snapshot(request, session_id):
    """Monitorun JSON snapshot-u (ilkin yüklənmə + WS-siz fallback, aşağı tezlik)."""
    _organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    return JsonResponse(session_monitor_snapshot(session))


@login_required
@never_cache
def exam_center_ticket_snapshot(request, session_id, ticket_id):
    """
    Bir tələbənin "çiyni üzərindən" canlı görüntüsü: hazırda hansı sualı yazır,
    nə cavablayıb, supervision hadisələri. Yalnız oxu — mövcud supervision
    snapshot xidmətini təkrar istifadə edir (final attempt-lər də ExamAttempt-dir).
    """
    from apps.exams.services.supervision import get_attempt_live_snapshot

    _organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    ticket = get_session_ticket_or_404(session, ticket_id)

    if not ticket.attempt_id:
        # Hələ imtahana başlamayıb — kompüterdə tələbə var, amma iş yoxdur.
        return JsonResponse(
            {
                "has_attempt": False,
                "student_name": ticket.student.get_full_name() or ticket.student.username,
                "student_username": ticket.student.username,
                "seat": ticket.seat_number,
                "ticket_status": ticket.status,
                "exam_title": ticket.exam.title,
            }
        )

    snapshot = get_attempt_live_snapshot(ticket.attempt)
    snapshot["has_attempt"] = True
    snapshot["seat"] = ticket.seat_number
    snapshot["ticket_status"] = ticket.status
    snapshot["exam_title"] = ticket.exam.title
    snapshot["session_id"] = session.pk
    return JsonResponse(snapshot)


@login_required
@require_POST
def exam_center_ticket_resume(request, session_id, ticket_id):
    """
    Dayandırılmış (locked) tələbənin imtahanını bərpa edir — mövcud supervision
    ``teacher_resume_attempt`` xidmətini təkrar işlədir. ``grant_extra_chance=1``
    verilibsə tələbəyə əlavə şans verilir (pozuntu sayğacı bir vahid azalır).
    """
    from apps.exams.services.supervision import teacher_resume_attempt

    _organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    ticket = get_session_ticket_or_404(session, ticket_id)
    if not ticket.attempt_id:
        return JsonResponse(
            {"success": False, "error": pgettext("exams.final_center.message", "Aktiv cəhd yoxdur.")}, status=400
        )
    grant_extra_chance = request.POST.get("grant_extra_chance") == "1"
    try:
        teacher_resume_attempt(ticket.attempt, request.user, grant_extra_chance=grant_extra_chance)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=409)
    return JsonResponse({"success": True})


@login_required
@require_POST
def exam_center_ticket_reentry(request, session_id, ticket_id):
    """
    YENİDƏN GİRİŞ (best practice: proktorlu bərpa). Bağlantısı kəsilmiş / brauzeri
    çökmüş / kompüteri dəyişmiş tələbəyə YENİ PIN verir — tələbə ``/exams/final/``
    -dan həmin PIN ilə daxil olub imtahana OLDUĞU YERDƏN davam edir. Cəhd toxunulmur
    (cavablar autosave-dədir); kilidlidirsə əvvəlcə açılır. Xam PIN BİR DƏFƏ qaytarılır
    (nəzarətçi şifahi/əl ilə tələbəyə çatdırır) və audit-ə yazılır — PIN log-a düşmür.
    """
    from apps.exams.domain.final_center import TICKET_STATUS_ACTIVE

    organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    ticket = get_session_ticket_or_404(session, ticket_id)
    if ticket.status != TICKET_STATUS_ACTIVE or not ticket.attempt_id:
        return JsonResponse(
            {
                "success": False,
                "error": pgettext(
                    "exams.final_center.message", "Yenidən giriş yalnız imtahanda olan tələbəyə verilir."
                ),
            },
            status=400,
        )
    if ticket.attempt.is_finished:
        return JsonResponse(
            {"success": False, "error": pgettext("exams.final_center.message", "İmtahan artıq bitib.")},
            status=400,
        )
    # Kilidlidirsə əvvəlcə aç ki, yenidən daxil olanda davam edə bilsin.
    if ticket.attempt.supervision_status == "locked":
        from apps.exams.services.supervision import teacher_resume_attempt

        try:
            teacher_resume_attempt(ticket.attempt, request.user)
        except ValueError:
            pass
    # Bərpa anındakı irəliləyiş + kompüter (tarixçə üçün): tələbə PIN alanda nə
    # qədər yazmışdı və hansı kompüterdə idi — audit-ə yazılır.
    from apps.exams.services.supervision import get_attempt_live_snapshot

    snap = get_attempt_live_snapshot(ticket.attempt)
    progress = {
        "seat": ticket.seat_number,
        "answered": snap.get("answered"),
        "total": snap.get("total_questions"),
    }
    try:
        raw_pin = regenerate_pin(ticket, request.user, request=request)
    except TicketStateError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=409)

    log_action(
        AuditAction.VIEW,
        user=request.user,
        organization=organization,
        obj=ticket,
        reason="final_reentry_pin_issued",
        request=request,
        resource_type="final_exam_ticket",
        resource_id=str(ticket.pk),
        changes={"reentry": progress},
    )
    return JsonResponse(
        {"success": True, "pin": raw_pin, "student_name": ticket.student.get_full_name() or ticket.student.username}
    )


@login_required
@require_POST
def exam_center_session_open_entry(request, session_id):
    _organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    if open_entry(session, request.user, request=request):
        messages.success(
            request, pgettext("exams.final_center.message", "Giriş açıldı — tələbələr PIN ilə daxil ola bilər.")
        )
    else:
        messages.warning(
            request, pgettext("exams.final_center.message", "Giriş artıq açıqdır və ya oturum bu mərhələdə deyil.")
        )
    return redirect("exams:exam_center_session_monitor", session_id=session.pk)


@login_required
@require_POST
def exam_center_session_start(request, session_id):
    """
    Sinxron start. Təsdiq modalı frontend-dədir; icazə + state + vaxt pəncərəsi
    burada yenidən yoxlanır. Override yalnız imtahan mərkəzi üçün mümkündür və
    audit-də qeyd olunur.
    """
    _organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    try:
        started = start_room(session, request.user, request=request)
    except RoomSessionStateError as exc:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": str(exc)}, status=409)
        messages.error(request, str(exc))
        return redirect("exams:exam_center_session_monitor", session_id=session.pk)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": started, "state": session.state})
    if started:
        messages.success(
            request, pgettext("exams.final_center.message", "İmtahan bütün hazır tələbələr üçün başladıldı.")
        )
    else:
        messages.warning(
            request,
            pgettext("exams.final_center.message", "Oturum artıq başladılıb və ya start üçün uyğun mərhələdə deyil."),
        )
    return redirect("exams:exam_center_session_monitor", session_id=session.pk)


@login_required
@require_POST
def exam_center_session_end(request, session_id):
    _organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    ended = end_room(session, request.user, request=request)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": ended, "state": session.state})
    if ended:
        messages.success(
            request,
            pgettext("exams.final_center.message", "Oturum bitirildi — aktiv cəhdlər avtomatik təhvil verildi."),
        )
    else:
        messages.warning(
            request, pgettext("exams.final_center.message", "Oturum aktiv deyil — bitirmə tətbiq olunmadı.")
        )
    return redirect("exams:exam_center_session_monitor", session_id=session.pk)


@login_required
@require_POST
def exam_center_session_cancel(request, session_id):
    _organization, session = get_center_session_or_404(request, session_id)
    reason = (request.POST.get("reason") or "").strip()
    if cancel_session(session, request.user, request=request, reason=reason):
        messages.success(
            request, pgettext("exams.final_center.message", "Oturum ləğv edildi və PIN-lər etibarsızlaşdırıldı.")
        )
    else:
        messages.warning(request, pgettext("exams.final_center.message", "Oturum bu mərhələdə ləğv oluna bilməz."))
    return redirect("exams:exam_center_session_list")


@login_required
@require_POST
def exam_center_ticket_remove(request, session_id, ticket_id):
    """Tələbənin çıxarılması/dayandırılması — səbəb MƏCBURİDİR."""
    _organization, session = get_center_session_or_404(request, session_id, for_supervision=True)
    ticket = get_session_ticket_or_404(session, ticket_id)
    action = (request.POST.get("action") or "removed").strip()
    if action not in ("removed", "suspended", "technical"):
        action = "removed"
    reason = (request.POST.get("reason") or "").strip()
    allow_reentry = request.POST.get("allow_reentry") == "1"

    try:
        done = remove_student(
            ticket,
            request.user,
            action=action,
            reason=reason,
            allow_reentry=allow_reentry,
            request=request,
        )
    except TicketStateError as exc:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect("exams:exam_center_session_monitor", session_id=session.pk)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": done, "status": ticket.status})
    if done:
        messages.success(
            request, pgettext("exams.final_center.message", "Tələbə üzrə əməliyyat tətbiq olundu və qeydə alındı.")
        )
    else:
        messages.warning(
            request,
            pgettext("exams.final_center.message", "Əməliyyat tətbiq olunmadı — bilet vəziyyəti artıq dəyişib."),
        )
    return redirect("exams:exam_center_session_monitor", session_id=session.pk)


__all__ = [
    "exam_center_session_cancel",
    "exam_center_session_end",
    "exam_center_session_monitor",
    "exam_center_session_open_entry",
    "exam_center_session_snapshot",
    "exam_center_session_start",
    "exam_center_ticket_reentry",
    "exam_center_ticket_remove",
    "exam_center_ticket_resume",
    "exam_center_ticket_snapshot",
]
