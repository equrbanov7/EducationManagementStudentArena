"""
İmtahan mərkəzi — tələbə giriş axını (final + midterm).

Axın: `/exams/final/` və ya `/exams/midterm/` (sahib 2026-10-20 — «midterm də final kimidir») fərdi PIN
girişi → uğurlu yoxlamadan sonra HƏMİN səhifədə imtahan məlumatı + qaydalar MODALI açılır → təsdiq →
gözləmə otağı (``final_center_waiting.py``) → nəzarətçi otağı başladır → attempt avtomatik açılır.

Növ uyğunluğu: hər giriş səhifəsi yalnız ÖZ növünün PIN-ini qəbul edir. Hər iki səhifə eyni namizəd
hovuzunu (bir hash büdcəsi) yoxlayır; doğru PIN başqa növün imtahanına aiddirsə tələbə login OLUNMUR və
düzgün ünvan göstərilir. Midterm mərkəz açarı (``exam.midterm_via_center``) söndürülübsə `/exams/midterm/`
yalnız izah göstərir (midterm kabinetdən verilir).

`/exams/final/` yalnız imtahana giriş üçün ayrıca login səhifəsidir (imtahan
siyahısı YOXDUR — tələbə hansı imtahanın PIN-ini yazırsa o imtahana daxil
olur). Bütün səhifələr imtahan zalı rejimindədir (chrome-suz, IP gate-li);
hər addımda bilet sahibliyi + oturum state-i backend-də yoxlanır.
"""

import logging

from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENTRY_OPEN,
    TICKET_STATUS_ABSENT,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_READY,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_WAITING,
)
from apps.exams.models import FinalExamTicket
from apps.exams.services.center_exams import (
    FINAL_KIND,
    MIDTERM_KIND,
    entry_url,
    entry_url_for_exam,
    exam_kind,
    is_center_kind,
)
from apps.exams.services.exam_center_gate import (
    hall_computer_check_enabled,
    org_computer_access_allowed,
    resolve_room_computer,
)
from apps.exams.services.final_center import (
    ERROR_LOCKED,
    ERROR_RATE_LIMITED,
    PinHashBudget,
    TicketStateError,
    admission_block_reason,
    claim_student_pin_entry,
    claim_ticket_pin_entry,
    clear_entry_session,
    ensure_pin_ticket,
    enter_waiting,
    entry_session_matches,
    entry_ticket_id,
    store_entry_session,
    validate_entry,
)
from apps.exams.services.final_center.entry import ERROR_WRONG_KIND
from apps.exams.services.final_center.reentry import cabinet_pin_resume_denial
from apps.exams.services.language_variants import available_language_options
from apps.exams.views.student._final_device import final_entry_network_guarded
from core.rls import bypass_rls

from ._center_common import FEXC_UI_LANGUAGES, TICKET_SELECT_RELATED, ensure_hall_access
from ._center_common import room_access_error as _room_access_error
from ._center_common import room_access_ok as _room_access_ok

logger = logging.getLogger("exams.final_center.student")


def _entry_error_message(code, kind=FINAL_KIND):
    if code == ERROR_RATE_LIMITED:
        return pgettext("exams.final_center.entry", "Çox sayda cəhd — bir dəqiqə sonra yenidən yoxlayın.")
    if code == ERROR_LOCKED:
        return pgettext(
            "exams.final_center.entry",
            "Təhlükəsizlik səbəbindən giriş müvəqqəti kilidlənib. Nəzarətçiyə müraciət edin.",
        )
    # Generik mesaj — istifadəçi adı/PIN-in hansının səhv olduğu deyilmir.
    if kind == MIDTERM_KIND:
        return pgettext("exams.final_center.entry", "Məlumatlar yanlışdır və ya aktiv midterm imtahanınız yoxdur.")
    return pgettext("exams.final_center.entry", "Məlumatlar yanlışdır və ya aktiv final imtahanınız yoxdur.")


def _wrong_kind_message(kind):
    """Doğru PIN, amma digər növün imtahanı — düzgün giriş ünvanı göstərilir (login YOXDUR)."""
    if kind == MIDTERM_KIND:
        return pgettext(
            "exams.final_center.entry",
            "Bu PIN final imtahanına aiddir. Final imtahanına /exams/final/ ünvanından daxil olun.",
        )
    return pgettext(
        "exams.final_center.entry",
        "Bu PIN midterm imtahanına aiddir. Midterm imtahanına /exams/midterm/ ünvanından daxil olun.",
    )


def _midterm_entry_disabled_message():
    return pgettext(
        "exams.final_center.entry",
        "Midterm imtahanları hazırda imtahan mərkəzi vasitəsilə keçirilmir — imtahana kabinetinizdəki "
        "«Təyin olunmuş imtahanlar» bölməsindən başlayın.",
    )


def _no_room_message():
    return pgettext(
        "exams.final_center.entry",
        "Zal müəyyən edilmədi — imtahan zalının nəzarətçisinə müraciət edin.",
    )


def _claim_failure_message(room, kind=FINAL_KIND):
    """Claim uğursuzluğunun tələbəyə deyilə bilən səbəbini seç.

    Açıq oturumun olmaması nəzarətçi hərəkətidir — bunu deməkdə təhlükəsizlik
    riski yoxdur; qalan səbəblər (sərf olunmuş PIN, tutulmuş yer) generik qalır.
    """
    from apps.exams.models import ExamRoomSession

    with bypass_rls():
        has_open_sitting = ExamRoomSession.objects.filter(
            room=room,
            state__in=(ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE),
        ).exists()
    if not has_open_sitting:
        return pgettext(
            "exams.final_center.entry",
            "Bu zalda hazırda açıq imtahan oturumu yoxdur — nəzarətçinin oturumu açmasını gözləyin.",
        )
    return _entry_error_message(None, kind)


def _render_login(request, kind=FINAL_KIND, *, error="", username="", modal_ticket=None, modal_error=""):
    """
    Login səhifəsini render edir. ``modal_ticket`` verilibsə PIN yoxlamasından
    keçmiş biletin imtahan-öncəsi məlumat/qaydalar MODALI açıq göstərilir.
    ``kind`` — giriş səhifəsinin növü (başlıq/forma ünvanı); modal həmişə biletin öz növündədir.
    """
    if modal_ticket is not None:
        kind = exam_kind(modal_ticket.exam) or kind
    context = {
        "error_message": error,
        "username_value": username,
        "show_gate_modal": modal_ticket is not None,
        "modal_error": modal_error,
        "fexc_ui_languages": FEXC_UI_LANGUAGES,
        "entry_kind": kind,
        "entry_is_midterm": kind == MIDTERM_KIND,
        "entry_url": entry_url(kind),
        "entry_disabled": not is_center_kind(kind),
    }
    if modal_ticket is not None:
        session = modal_ticket.session
        context.update(
            {
                "ticket": modal_ticket,
                "session": session,
                "exam": modal_ticket.exam,
                "room": session.room if session else None,
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
    # İmtahanı bitirmiş / çıxarılmış / gəlməyən bilet üçün giriş qaydaları
    # modalını TƏKRAR göstərmə (oturum hələ açıq olsa belə). Tələbə imtahandan
    # çıxıb — sessiyanı təmizlə, logout et və təmiz login səhifəsinə qaytar.
    # (Məs. final apellyasiyasından sonra bura yönlənmə.)
    kind = exam_kind(ticket.exam)
    if ticket.status in (TICKET_STATUS_COMPLETED, TICKET_STATUS_REMOVED, TICKET_STATUS_ABSENT):
        clear_entry_session(request)
        logout(request)
        return redirect(entry_url(kind))

    session = ticket.session
    if session is None:
        # Oturum bağlanmayıb/qopub — yenidən daxil olsun (kompüter IP → zal).
        clear_entry_session(request)
        return _render_login(
            request,
            kind,
            error=pgettext("exams.final_center.entry", "Zal oturumuna qoşulmayıb — yenidən daxil olun."),
        )
    if not _room_access_ok(request, session.room):
        clear_entry_session(request)
        return _render_login(request, kind, error=_room_access_error())
    if session.state not in (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE):
        clear_entry_session(request)
        return _render_login(
            request,
            kind,
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
    ticket = (
        FinalExamTicket.objects.select_related(*TICKET_SELECT_RELATED)
        .filter(pk=ticket_id, student=request.user)
        .first()
    )
    return ticket if ticket is not None and entry_session_matches(request, ticket) else None


def _center_entry(request, kind):
    """
    Fərdi PIN ilə imtahan girişi (imtahan siyahısı YOX) — `/exams/final/` və `/exams/midterm/`.

    Platformanın normal autentifikasiyasını ƏVƏZ ETMİR — yalnız imtahan zalı
    axını üçündür. Uğurlu PIN yoxlamasından sonra sessiya həmin tələbəyə
    rotasiya olunur və (PRG ilə) imtahan-öncəsi modal açılır.
    """
    ensure_hall_access(request)

    if not is_center_kind(kind):
        # Midterm mərkəz açarı söndürülüb — midterm kabinetdən verilir; giriş formu YOXDUR.
        return _render_login(request, kind, error=_midterm_entry_disabled_message())

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "confirm":
            return _handle_confirm(request, kind)
        if action == "back":
            # Modaldan geri qayıdanda istifadəçi adını saxla ki, login formasında
            # yenidən yazılmasın (PIN TƏHLÜKƏSİZLİK səbəbindən saxlanmır).
            kept_username = request.user.username if request.user.is_authenticated else ""
            clear_entry_session(request)
            logout(request)
            if kept_username:
                request.session["final_entry_username"] = kept_username
            return redirect(entry_url(kind))
        return _handle_login(request, kind)

    # GET — sessiyada təsdiqlənmiş bilet varsa uyğun mərhələyə yönləndir/modal göstər.
    ticket = _validated_session_ticket(request)
    if ticket is not None:
        if exam_kind(ticket.exam) != kind:
            # Təsdiqlənmiş bilet digər növün imtahanıdır — öz giriş səhifəsində davam etsin.
            return redirect(entry_url_for_exam(ticket.exam))
        return _route_validated_ticket(request, ticket)
    if entry_ticket_id(request):
        # Sessiyada qalıq id var, amma bilet tapılmadı — təmizlə.
        clear_entry_session(request)
    return _render_login(request, kind, username=request.session.pop("final_entry_username", ""))


@require_http_methods(["GET", "POST"])
@final_entry_network_guarded
def final_exam_entry(request):
    """`/exams/final/` — final imtahanının zal girişi."""
    return _center_entry(request, FINAL_KIND)


@require_http_methods(["GET", "POST"])
@final_entry_network_guarded
def midterm_exam_entry(request):
    """`/exams/midterm/` — midterm imtahanının zal girişi (sahib 2026-10-20: final ilə eyni proses)."""
    return _center_entry(request, MIDTERM_KIND)


def _handle_login(request, kind=FINAL_KIND):
    username = request.POST.get("username", "")
    raw_pin = request.POST.get("pin", "")
    # Tutum testi 2026-10-06: bilet və fərdi-PIN yolları BİR hash büdcəsini paylaşır —
    # hər sonluq (uğur/səhv/naməlum istifadəçi) ≈1 tam PBKDF2, 3–4 yox.
    budget = PinHashBudget()
    uname = (username or "").strip()
    ticket, error_code = validate_entry(request, username, raw_pin, budget=budget, kind=kind)
    if ticket is None:
        # Audit 2026-09-13 EX-06 (P2): IP+istifadəçi limiteri dolanda bilet
        # yolu «rate_limited» qaytarır, amma fərdi-PIN yolu yenə işləyirdi —
        # limit yan keçilirdi. Limit aşımı hər iki yolu bağlayır.
        if error_code == ERROR_RATE_LIMITED:
            return _render_login(request, kind, error=_entry_error_message(error_code, kind), username=uname)
        if error_code == ERROR_WRONG_KIND:
            return _render_login(request, kind, error=_wrong_kind_message(kind), username=uname)
        # Bilet (otaq-oturum) sistemi olmayan finallar: tələbə username +
        # kabinetdə gördüyü fərdi PIN ilə birbaşa imtahana daxil olur.
        pin_response = _handle_student_pin_login(request, username, raw_pin, budget=budget, kind=kind)
        if pin_response is not None:
            return pin_response
        return _render_login(request, kind, error=_entry_error_message(error_code, kind), username=uname)

    # Kompüter IP → ZAL (oturum sisteminin ləğvi, 2026-07): bilet imtahana bağlıdır,
    # tələbə hansı zalda olduğunu qeydli kompüterin IP-si müəyyən edir. Qeydiyyatsız
    # kompüterdən giriş yoxdur (istifadəçini login DA ETMƏ).
    room, computer = resolve_room_computer(request, ticket.organization)
    if room is None and not hall_computer_check_enabled():
        # Zal kompüteri yoxlaması söndürülüb (sahib 2026-10-21): kompüter zalı müəyyən etmirsə biletin artıq
        # təyin olunduğu zal oturumu götürülür; o da yoxdursa tələbə nəzarətçiyə yönləndirilir.
        if ticket.session_id is None:
            return _render_login(request, kind, error=_no_room_message(), username=uname)
        room = ticket.session.room
    if room is None:
        return _render_login(request, kind, error=_room_access_error(), username=uname)

    # Otağa bağlama + birdəfəlik PIN claim-i eyni ticket lock-u altında gedir:
    # paralel ikinci kompüter nə sessiya ala, nə də attempt location-ını dəyişə bilər.
    ticket = claim_ticket_pin_entry(ticket, room, computer)
    if ticket is None:
        return _render_login(request, kind, error=_claim_failure_message(room, kind), username=uname)

    # Fərqli istifadəçi login-i varsa təmizlə, sonra bilet sahibini login et.
    if request.user.is_authenticated and request.user.pk != ticket.student_id:
        logout(request)
    if not request.user.is_authenticated or request.user.pk != ticket.student_id:
        login(request, ticket.student, backend="apps.accounts.backends.EmailOrUsernameBackend")
    request.session["active_organization"] = ticket.organization.slug
    store_entry_session(request, ticket)
    # PRG: modal GET-də göstərilir (refresh təkrar POST etmir).
    return redirect(entry_url(kind))


def _handle_student_pin_login(request, username, raw_pin, budget=None, kind=FINAL_KIND):
    """Fərdi ExamStudentPin ilə final/midterm girişi — GÖZLƏMƏ OTAĞI axını.

    2026-10-20: midterm də eyni kabinet PIN-i ilə girir (tələbə kabinetdə gördüyü PIN-i saxlayır).
    PIN digər növün imtahanına aiddirsə login OLUNMUR — düzgün ünvan göstərilir.

    Uyğun imtahan tapılmasa ``None`` qaytarır (çağıran generik xəta göstərir).
    Tələbə qeydli zal kompüterindən girəndə imtahan DƏRHAL BAŞLAMIR: daxili
    bilet + zal oturumu yaradılır (bilet PIN-siz, yalnız vəziyyət daşıyıcısı),
    tələbə imtahan-öncəsi modal → gözləmə otağına düşür və nəzarətçi zal
    monitorunda «Başlat» vuranda imtahan açılır (sinxron start). Org-da qeydli
    kompüter yoxdursa köhnə birbaşa-başlama davranışı qalır.
    """
    from apps.exams.services.attempts import _start_or_resume_attempt
    from apps.exams.services.student_pins import resolve_student_pin_login, student_pin_login_rate_limited
    from apps.exams.views.student._helpers import ensure_student_exam_tenant_context

    uname = (username or "").strip()

    # Freeze-safe throttle (EXAM-SEC-002): this ExamStudentPin route is the
    # second entry path and must not stay brute-forceable when the ticket
    # path's IP limiter trips.  The throttle is keyed per-username (never per
    # shared IP), so localhost / a NAT'd exam hall cannot freeze other students,
    # and stopping one student never blocks the rest.
    if uname and student_pin_login_rate_limited(uname):
        logger.warning("student_pin_login rate limited for username=%s", uname)
        return _render_login(request, kind, error=_entry_error_message(ERROR_RATE_LIMITED, kind), username=uname)

    exam, student = resolve_student_pin_login(username, raw_pin, budget=budget)
    if exam is None:
        return None
    if exam_kind(exam) != kind:
        return _render_login(request, kind, error=_wrong_kind_message(kind), username=uname)
    # Resolver PIN-i kəsilmiş (strip) formada yoxlayıb; eyni dəyər memo-ya düşür və
    # ``can_user_start`` təkrar tam hash etmir.
    raw_pin = (raw_pin or "").strip()

    # Qeydli kompüter qapısı: biletsiz yol da yalnız icazə verilmiş zal
    # kompüterlərindən işləyir (org-da qeydli kompüter varsa). Bax
    # ``org_computer_access_allowed`` — MAC rejimində MAC, əks halda IP ilə.
    if not org_computer_access_allowed(request, exam.organization if exam.organization_id else None):
        return _render_login(request, kind, error=_room_access_error(), username=uname)

    # Kompüterin zalı (MAC/IP → zal). Cəhd aşağıda zal/kompüterlə möhürlənir ki,
    # zal monitoru biletsiz imtahanları da göstərsin.
    #
    # QEYD (2026-07 dəyişikliyi): otaq izolyasiyası LƏĞV edildi — eyni imtahan
    # eyni anda BİR NEÇƏ zalda keçirilə bilər (böyük imtahanlar bir neçə otağa
    # bölünür). Giriş onsuz da yalnız QEYDLİ kompüterdən (yuxarıdakı
    # ``org_computer_access_allowed`` — MAC/IP gate) + fərdi PIN + cəhd limiti
    # ilə idarə olunur; imtahanı bir zala bağlamaq artıq idi və istənilən
    # uyğun-MAC zaldan girişi səhvən bloklayırdı.
    entry_room, entry_computer = (None, None)
    if exam.organization_id:
        entry_room, entry_computer = resolve_room_computer(request, exam.organization)

    # Credential artıq resolve_student_pin_login ilə konkret tələbə+imtahana
    # bağlanıb. Public request-də tenant hələ qurulmadığı üçün start siyasəti
    # və sual mövcudluğu həmin dar, credential-scoped bypass daxilində yoxlanır.
    with bypass_rls():
        can_start, reason = exam.can_user_start(student, code=raw_pin)
        has_active_questions = exam.questions.filter(is_active=True).exists()
        # Audit 2026-09-28 EXA-04: qayıb limiti buraxılış qapısı PIN yolunda da
        # (login-dən ƏVVƏL, credential-scoped bypass daxilində) — FAIL-CLOSED.
        admission_reason = admission_block_reason(student, exam) if can_start else None
    if not can_start:
        return _render_login(request, kind, error=reason or _entry_error_message(None, kind), username=uname)
    if admission_reason:
        return _render_login(request, kind, error=admission_reason, username=uname)

    # Sual təyin olunmayıbsa imtahanı BAŞLATMA — tələbəni ümumi imtahan
    # siyahısına (exams/available) atmaq olmaz; giriş səhifəsində xəbərdarlıq göstər.
    if not has_active_questions:
        return _render_login(
            request,
            kind,
            error=pgettext(
                "exams.final_center.entry",
                "İmtahana hələ sual əlavə olunmayıb. Zəhmət olmasa imtahan mərkəzi ilə əlaqə saxlayın.",
            ),
            username=uname,
        )

    # Zal axını: bilet + oturum (login-dən ƏVVƏL — rədd halında istifadəçi
    # login OLUNMUR, _handle_login ilə eyni davranış).
    pin_ticket = None
    if entry_room is not None:
        # 2026-10-13 (gecə): davam edən cəhd — köhnə PIN (yeni PIN verilib) / başqa kompüter rədd olunur.
        resume_denial, move_attempt = cabinet_pin_resume_denial(request, exam, student, entry_computer)
        if resume_denial:
            return _render_login(request, kind, error=resume_denial, username=uname)
        pin_ticket, ticket_error = ensure_pin_ticket(
            exam, student, entry_room, entry_computer, move_attempt=move_attempt
        )
        if pin_ticket is None:
            return _render_login(request, kind, error=ticket_error, username=uname)
        # W4 R7: claim + giriş audit hadisəsi (tarixçə «Girişlər» KPI-ı).
        pin_ticket = claim_student_pin_entry(pin_ticket, request=request)
        if pin_ticket is None:
            return _render_login(request, kind, error=_entry_error_message(None, kind), username=uname)

    # Fərqli istifadəçi login-i varsa təmizlə, sonra imtahan tələbəsini login et.
    if request.user.is_authenticated and request.user.pk != student.pk:
        logout(request)
    if not request.user.is_authenticated or request.user.pk != student.pk:
        login(request, student, backend="apps.accounts.backends.EmailOrUsernameBackend")
    if exam.organization_id:
        request.session["active_organization"] = exam.organization.slug

    ensure_student_exam_tenant_context(request)

    if pin_ticket is None:
        # Org zal-kompüter sistemi işlətmir → köhnə birbaşa başlama davranışı.
        return _start_or_resume_attempt(request, exam)

    # PRG: imtahan-öncəsi modal GET-də açılır → təsdiq → gözləmə otağı →
    # nəzarətçi startı (bax _route_validated_ticket / _handle_confirm).
    store_entry_session(request, pin_ticket)
    return redirect(entry_url(kind))


def _handle_confirm(request, kind=FINAL_KIND):
    """İmtahan-öncəsi modal təsdiqi: qaydalar + dil → gözləmə otağı."""
    ticket = _validated_session_ticket(request)
    if ticket is None:
        clear_entry_session(request)
        return redirect(entry_url(kind))
    if exam_kind(ticket.exam) != kind:
        return redirect(entry_url_for_exam(ticket.exam))

    session = ticket.session
    if session is None or session.state not in (ROOM_SESSION_STATE_ENTRY_OPEN, ROOM_SESSION_STATE_ACTIVE):
        clear_entry_session(request)
        return _render_login(
            request,
            kind,
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


__all__ = [
    "final_exam_entry",
    "midterm_exam_entry",
]
