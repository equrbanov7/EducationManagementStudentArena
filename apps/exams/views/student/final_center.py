"""
Final imtahan mərkəzi — tələbə axını.

Axın: `/exams/final/` (fərdi PIN girişi) → uğurlu yoxlamadan sonra HƏMİN
səhifədə imtahan məlumatı + qaydalar MODALI açılır → təsdiq → gözləmə otağı
→ nəzarətçi otağı başladır → attempt avtomatik açılır (mövcud take_exam).

`/exams/final/` yalnız imtahana giriş üçün ayrıca login səhifəsidir (imtahan
siyahısı YOXDUR — tələbə hansı imtahanın PIN-ini yazırsa o imtahana daxil
olur). Bütün səhifələr imtahan zalı rejimindədir (chrome-suz, IP gate-li);
hər addımda bilet sahibliyi + oturum state-i backend-də yoxlanır.
"""

import logging

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods, require_POST

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_READY,
    TICKET_STATUS_WAITING,
)
from apps.exams.models import FinalExamTicket
from apps.exams.services.exam_center_gate import final_exam_access_allowed, room_ip_access_allowed
from apps.exams.services.final_center import (
    ERROR_LOCKED,
    ERROR_RATE_LIMITED,
    HEARTBEAT_INTERVAL_SECONDS,
    TicketStateError,
    begin_attempt_for_ticket,
    clear_entry_session,
    enter_waiting,
    entry_ticket_id,
    maybe_auto_end,
    store_entry_session,
    student_cancel_waiting,
    sync_ticket_completion,
    validate_entry,
)
from apps.exams.services.language_variants import available_language_options

logger = logging.getLogger("exams.final_center.student")

# İmtahan zalı interfeys dilləri (chrome gizli olduğu üçün öz seçicimiz).
FEXC_UI_LANGUAGES = (("az", "AZ"), ("en", "EN"), ("ru", "RU"))

_TICKET_SELECT_RELATED = (
    "session",
    "session__room",
    "session__invigilator",
    "exam",
    "organization",
    "student",
    "attempt",
)


def _ensure_hall_access(request):
    """İmtahan zalı IP/CIDR qapısı (mövcud exam_center_gate xidməti)."""
    if not final_exam_access_allowed(request):
        raise PermissionDenied(pgettext("exams.view.final_center.permission", "final_center_ip_not_allowed"))


def _room_access_ok(request, room) -> bool:
    """Zalın qeydli kompüterlərinə görə IP qapısı (MAC identifikasiya, IP tətbiq)."""
    return room_ip_access_allowed(request, room)


def _room_access_error():
    return pgettext(
        "exams.final_center.entry",
        "Bu kompüterdən imtahana giriş icazəsi yoxdur. Zəhmət olmasa zaldakı təyin olunmuş kompüterdən daxil olun.",
    )


def _entry_error_message(code):
    if code == ERROR_RATE_LIMITED:
        return pgettext("exams.final_center.entry", "Çox sayda cəhd — bir dəqiqə sonra yenidən yoxlayın.")
    if code == ERROR_LOCKED:
        return pgettext(
            "exams.final_center.entry",
            "Təhlükəsizlik səbəbindən giriş müvəqqəti kilidlənib. Nəzarətçiyə müraciət edin.",
        )
    # Generik mesaj — istifadəçi adı/PIN-in hansının səhv olduğu deyilmir.
    return pgettext("exams.final_center.entry", "Məlumatlar yanlışdır və ya aktiv final imtahanınız yoxdur.")


def _render_login(request, *, error="", username="", modal_ticket=None, modal_error=""):
    """
    Login səhifəsini render edir. ``modal_ticket`` verilibsə PIN yoxlamasından
    keçmiş biletin imtahan-öncəsi məlumat/qaydalar MODALI açıq göstərilir.
    """
    context = {
        "error_message": error,
        "username_value": username,
        "show_gate_modal": modal_ticket is not None,
        "modal_error": modal_error,
        "fexc_ui_languages": FEXC_UI_LANGUAGES,
    }
    if modal_ticket is not None:
        session = modal_ticket.session
        context.update(
            {
                "ticket": modal_ticket,
                "session": session,
                "exam": modal_ticket.exam,
                "room": session.room,
                "language_options": available_language_options(modal_ticket.exam),
            }
        )
    return render(request, "exams/student/final_entry.html", context)


def _route_validated_ticket(request, ticket):
    """
    PIN yoxlamasından keçmiş bilet üçün marşrut:
    * oturum bağlıdırsa → login (mesajla);
    * gözləmə/hazır → gözləmə otağı;
    * aktiv + attempt → imtahan (take_exam);
    * təyin olunub → imtahan-öncəsi modal.
    """
    session = ticket.session
    if not _room_access_ok(request, session.room):
        clear_entry_session(request)
        return _render_login(request, error=_room_access_error())
    if session.state not in (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE):
        clear_entry_session(request)
        return _render_login(
            request,
            error=pgettext("exams.final_center.entry", "Oturum hazırda giriş üçün açıq deyil."),
        )
    if ticket.status in (TICKET_STATUS_WAITING, TICKET_STATUS_READY):
        return redirect("exams:final_exam_waiting", ticket_id=ticket.pk)
    if ticket.status == TICKET_STATUS_ACTIVE and ticket.attempt_id:
        return redirect("exams:take_exam", slug=ticket.exam.slug, attempt_id=ticket.attempt_id)
    return _render_login(request, modal_ticket=ticket)


def _validated_session_ticket(request):
    """Sessiyada saxlanan (PIN-dən keçmiş) bileti qaytarır, yoxdursa None."""
    ticket_id = entry_ticket_id(request)
    if not request.user.is_authenticated or not ticket_id:
        return None
    return (
        FinalExamTicket.objects.select_related(*_TICKET_SELECT_RELATED)
        .filter(pk=ticket_id, student=request.user)
        .first()
    )


@require_http_methods(["GET", "POST"])
def final_exam_entry(request):
    """
    `/exams/final/` — fərdi PIN ilə imtahan girişi (imtahan siyahısı YOX).

    Platformanın normal autentifikasiyasını ƏVƏZ ETMİR — yalnız imtahan zalı
    axını üçündür. Uğurlu PIN yoxlamasından sonra sessiya həmin tələbəyə
    rotasiya olunur və (PRG ilə) imtahan-öncəsi modal açılır.
    """
    _ensure_hall_access(request)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "confirm":
            return _handle_confirm(request)
        if action == "back":
            # Modaldan geri qayıdanda istifadəçi adını saxla ki, login formasında
            # yenidən yazılmasın (PIN TƏHLÜKƏSİZLİK səbəbindən saxlanmır).
            kept_username = request.user.username if request.user.is_authenticated else ""
            clear_entry_session(request)
            logout(request)
            if kept_username:
                request.session["final_entry_username"] = kept_username
            return redirect("exams:final_exam_entry")
        return _handle_login(request)

    # GET — sessiyada təsdiqlənmiş bilet varsa uyğun mərhələyə yönləndir/modal göstər.
    ticket = _validated_session_ticket(request)
    if ticket is not None:
        return _route_validated_ticket(request, ticket)
    if entry_ticket_id(request):
        # Sessiyada qalıq id var, amma bilet tapılmadı — təmizlə.
        clear_entry_session(request)
    return _render_login(request, username=request.session.pop("final_entry_username", ""))


def _handle_login(request):
    username = request.POST.get("username", "")
    raw_pin = request.POST.get("pin", "")
    ticket, error_code = validate_entry(request, username, raw_pin)
    if ticket is None:
        # Bilet (otaq-oturum) sistemi olmayan finallar: tələbə username +
        # kabinetdə gördüyü fərdi PIN ilə birbaşa imtahana daxil olur.
        pin_response = _handle_student_pin_login(request, username, raw_pin)
        if pin_response is not None:
            return pin_response
        return _render_login(request, error=_entry_error_message(error_code), username=(username or "").strip())

    # Zal-səviyyəli kompüter (IP) qapısı: bilet tapıldı, amma sorğu zalın qeydli
    # kompüterindən gəlmirsə girişə icazə vermə (istifadəçini login DA ETMƏ).
    if not _room_access_ok(request, ticket.session.room):
        return _render_login(request, error=_room_access_error(), username=(username or "").strip())

    # Fərqli istifadəçi login-i varsa təmizlə, sonra bilet sahibini login et.
    if request.user.is_authenticated and request.user.pk != ticket.student_id:
        logout(request)
    if not request.user.is_authenticated or request.user.pk != ticket.student_id:
        login(request, ticket.student, backend="apps.accounts.backends.EmailOrUsernameBackend")
    request.session["active_organization"] = ticket.organization.slug
    store_entry_session(request, ticket)
    # PRG: modal GET-də göstərilir (refresh təkrar POST etmir).
    return redirect("exams:final_exam_entry")


def _handle_student_pin_login(request, username, raw_pin):
    """Biletsiz final girişi (fərdi ExamStudentPin ilə) — birbaşa imtahana keçir.

    Uyğun imtahan tapılmasa ``None`` qaytarır (çağıran generik xəta göstərir).
    Gözləmə otağı/nəzarətçi yoxdur — PIN doğrulanan kimi cəhd açılır.
    """
    from apps.exams.services.attempts import _start_or_resume_attempt
    from apps.exams.services.student_pins import resolve_student_pin_login
    from apps.exams.views.student._helpers import ensure_student_exam_tenant_context

    exam, student = resolve_student_pin_login(username, raw_pin)
    if exam is None:
        return None

    can_start, reason = exam.can_user_start(student, code=raw_pin)
    if not can_start:
        return _render_login(request, error=reason or _entry_error_message(None), username=(username or "").strip())

    # Sual təyin olunmayıbsa imtahanı BAŞLATMA — tələbəni ümumi imtahan
    # siyahısına (exams/available) atmaq olmaz; giriş səhifəsində xəbərdarlıq göstər.
    if not exam.questions.filter(is_active=True).exists():
        return _render_login(
            request,
            error=pgettext(
                "exams.final_center.entry",
                "İmtahana hələ sual əlavə olunmayıb. Zəhmət olmasa imtahan mərkəzi ilə əlaqə saxlayın.",
            ),
            username=(username or "").strip(),
        )

    # Fərqli istifadəçi login-i varsa təmizlə, sonra imtahan tələbəsini login et.
    if request.user.is_authenticated and request.user.pk != student.pk:
        logout(request)
    if not request.user.is_authenticated or request.user.pk != student.pk:
        login(request, student, backend="apps.accounts.backends.EmailOrUsernameBackend")
    if exam.organization_id:
        request.session["active_organization"] = exam.organization.slug

    ensure_student_exam_tenant_context(request)
    return _start_or_resume_attempt(request, exam)


def _handle_confirm(request):
    """İmtahan-öncəsi modal təsdiqi: qaydalar + dil → gözləmə otağı."""
    ticket = _validated_session_ticket(request)
    if ticket is None:
        clear_entry_session(request)
        return redirect("exams:final_exam_entry")

    session = ticket.session
    if session.state not in (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE):
        clear_entry_session(request)
        return _render_login(
            request,
            error=pgettext("exams.final_center.entry", "Oturum hazırda giriş üçün açıq deyil."),
        )

    if request.POST.get("accept_rules") != "1":
        return _render_login(
            request,
            modal_ticket=ticket,
            modal_error=pgettext("exams.final_center.gate", "Davam etmək üçün imtahan qaydalarını təsdiqləyin."),
        )
    try:
        enter_waiting(ticket, language=(request.POST.get("language") or "").strip(), request=request)
    except TicketStateError as exc:
        return _render_login(request, modal_ticket=ticket, modal_error=str(exc))
    return redirect("exams:final_exam_waiting", ticket_id=ticket.pk)


def _resolve_own_ticket(request, ticket_id):
    """
    Bilet sahibliyi + PIN girişindən keçmə yoxlaması. Girişsiz birbaşa URL
    yığan istifadəçi login səhifəsinə qaytarılır.
    """
    ticket = get_object_or_404(
        FinalExamTicket.objects.select_related(*_TICKET_SELECT_RELATED),
        pk=ticket_id,
        student=request.user,
    )
    if entry_ticket_id(request) != ticket.pk:
        return ticket, redirect("exams:final_exam_entry")
    return ticket, None


@login_required
def final_exam_waiting(request, ticket_id):
    """
    Gözləmə otağı. Real vaxt WS ilə işləyir (yüksək tezlikli polling YOX);
    WS mümkün olmayanda aşağı tezlikli fallback poll (state endpoint) var.
    """
    _ensure_hall_access(request)
    ticket, deny = _resolve_own_ticket(request, ticket_id)
    if deny is not None:
        return deny
    if not _room_access_ok(request, ticket.session.room):
        raise PermissionDenied(pgettext("exams.view.final_center.permission", "final_center_ip_not_allowed"))

    session = ticket.session
    if ticket.status == TICKET_STATUS_ACTIVE and ticket.attempt_id:
        return redirect("exams:take_exam", slug=ticket.exam.slug, attempt_id=ticket.attempt_id)
    if ticket.status not in (TICKET_STATUS_WAITING, TICKET_STATUS_READY):
        # Hələ təsdiqlənməyib — login/modal səhifəsinə qaytar.
        return redirect("exams:final_exam_entry")

    return render(
        request,
        "exams/student/final_waiting.html",
        {
            "ticket": ticket,
            "session": session,
            "exam": ticket.exam,
            "room": session.room,
            "ws_path": f"/ws/exams/final/wait/{ticket.pk}/",
            "heartbeat_seconds": HEARTBEAT_INTERVAL_SECONDS,
            "state_url": reverse("exams:final_ticket_state", kwargs={"ticket_id": ticket.pk}),
            "begin_url": reverse("exams:final_exam_begin", kwargs={"ticket_id": ticket.pk}),
            "cancel_url": reverse("exams:final_exam_cancel", kwargs={"ticket_id": ticket.pk}),
            "session_already_active": session.state == ROOM_SESSION_STATE_ACTIVE,
        },
    )


@login_required
@require_POST
def final_exam_cancel(request, ticket_id):
    """Start-dan əvvəl gözləmə otağından imtina — cəhd haqqı yanmır."""
    _ensure_hall_access(request)
    ticket, deny = _resolve_own_ticket(request, ticket_id)
    if deny is not None:
        return deny
    student_cancel_waiting(ticket, request=request)
    clear_entry_session(request)
    logout(request)
    return redirect("exams:final_exam_entry")


@login_required
@require_POST
def final_exam_begin(request, ticket_id):
    """
    Oturum AKTİV olduqdan sonra attempt-in yaradılması. Sinxron startda hər
    müştəri kiçik təsadüfi gecikmə ilə bu endpoint-i çağırır — sual seti
    WS broadcast-ı ilə YOX, autentifikasiyalı HTTP ilə yüklənir.
    """
    _ensure_hall_access(request)
    ticket, deny = _resolve_own_ticket(request, ticket_id)
    if deny is not None:
        return JsonResponse({"success": False, "redirect_url": reverse("exams:final_exam_entry")}, status=403)
    if not _room_access_ok(request, ticket.session.room):
        return JsonResponse(
            {"success": False, "error": str(_room_access_error()), "redirect_url": reverse("exams:final_exam_entry")},
            status=403,
        )

    try:
        attempt = begin_attempt_for_ticket(ticket)
    except TicketStateError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=409)

    return JsonResponse(
        {
            "success": True,
            "redirect_url": reverse("exams:take_exam", kwargs={"slug": ticket.exam.slug, "attempt_id": attempt.pk}),
        }
    )


@login_required
def final_ticket_state(request, ticket_id):
    """
    Aşağı tezlikli fallback poll (WS kəsiləndə). Kompakt payload — sual/cavab
    məlumatı YOXDUR.
    """
    ticket, deny = _resolve_own_ticket(request, ticket_id)
    if deny is not None:
        return JsonResponse({"error": "entry_required"}, status=403)

    session = ticket.session
    maybe_auto_end(session)
    session.refresh_from_db(fields=["state", "started_at", "ended_at"])
    if ticket.status == TICKET_STATUS_ACTIVE:
        sync_ticket_completion(ticket)

    return JsonResponse(
        {
            "session_state": session.state,
            "ticket_status": ticket.status,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "server_now": timezone.now().isoformat(),
        }
    )


__all__ = [
    "final_exam_begin",
    "final_exam_cancel",
    "final_exam_entry",
    "final_exam_waiting",
    "final_ticket_state",
]
