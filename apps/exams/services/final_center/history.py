"""final_center paketi — oturum əməliyyat TARİXÇƏSİ (audit timeline).

İmtahan mərkəzi rəhbəri / prorektor / rektor kimi yuxarı səviyyələr üçün bütün
əməliyyatları BİR YERDƏ, xronoloji göstərir: PIN yaradılması (kim yaradıb, kimə
verilib), tələbənin PIN ilə girişi, kompüter/yer dəyişmələri, yenidən giriş
anındakı irəliləyiş (nə qədər yazmışdı), zal, oturum həyat dövrü və nəzarət
(pozuntu/dayandırma) hadisələri.

Mənbələr: `AuditLog` (final_exam_ticket + exam_room_session resursları) və
`SupervisionIncident`. Yeni məlumat SAXLANMIR — mövcud audit birləşdirilir.
"""

from django.db.models import Q
from django.utils.translation import gettext_lazy as _l

# reason kodu → (başlıq, fa-ikon, ton). Başlıqlar lazy tərcümə olunur (dil seçiminə görə).
_TICKET_EVENTS = {
    "final_tickets_assigned": (_l("PIN yaradıldı və tələbəyə təyin edildi"), "fa-key", "info"),
    "final_pin_regenerated": (_l("PIN yenidən yaradıldı"), "fa-key", "warn"),
    "final_pin_viewed_by_staff": (_l("PIN nəzarətçiyə göstərildi"), "fa-eye", "info"),
    "final_reentry_pin_issued": (_l("Yenidən giriş PIN-i verildi"), "fa-key", "warn"),
    "final_entry_validated": (_l("Tələbə PIN ilə daxil oldu"), "fa-right-to-bracket", "success"),
    "final_seat_changed": (_l("Kompüter / yer dəyişdirildi"), "fa-desktop", "warn"),
    "final_student_suspended": (_l("Tələbə müvəqqəti dayandırıldı"), "fa-pause", "danger"),
    "final_student_removed": (_l("Tələbə imtahandan çıxarıldı"), "fa-user-slash", "danger"),
    "final_student_readmitted": (_l("Tələbə yenidən buraxıldı"), "fa-user-check", "success"),
}
_SESSION_EVENTS = {
    "final_session_created": (_l("Oturum yaradıldı"), "fa-calendar-plus", "info"),
    "final_room_entry_opened": (_l("Giriş açıldı — tələbələr PIN ilə daxil ola bilər"), "fa-door-open", "info"),
    "final_room_started": (_l("İmtahan başladıldı"), "fa-play", "success"),
    "final_room_ended_auto": (_l("Oturum avtomatik bitirildi"), "fa-stop", "info"),
}
# Prefiks (reason bəzən ": səbəb" və ya "_override" ilə uzanır) → baza kodu.
_KNOWN_CODES = tuple(_TICKET_EVENTS.keys()) + tuple(_SESSION_EVENTS.keys())


def _base_code(reason):
    """Reason sətrindən baza kodunu və əlavə mətni (səbəb) ayırır."""
    reason = (reason or "").strip()
    head = reason.split(":", 1)
    code_part = head[0].strip()
    extra = head[1].strip() if len(head) > 1 else ""
    for code in _KNOWN_CODES:
        if code_part == code or code_part.startswith(code):
            return code, extra
    return code_part, extra


def _detail(code, log, extra):
    from django.utils.translation import gettext as _

    changes = log.changes or {}
    if code == "final_seat_changed":
        pair = changes.get("seat_number") or []
        if len(pair) == 2:
            old = pair[0] if pair[0] is not None else "—"
            new = pair[1] if pair[1] is not None else "—"
            return _("Kompüter %(old)s → %(new)s") % {"old": old, "new": new}
    if code == "final_reentry_pin_issued":
        r = changes.get("reentry") or {}
        answered = r.get("answered")
        total = r.get("total")
        seat = r.get("seat")
        parts = []
        if answered is not None and total is not None:
            parts.append(
                _("bərpa anında %(answered)s/%(total)s cavab yazmışdı") % {"answered": answered, "total": total}
            )
        if seat is not None:
            parts.append(_("kompüter %(seat)s") % {"seat": seat})
        return "; ".join(parts)
    if extra:
        return extra
    return ""


def session_history(session):
    """Oturumun tam əməliyyat tarixçəsi — xronoloji hadisə siyahısı."""
    from apps.audit.models import AuditLog
    from apps.exams.models import FinalExamTicket, SupervisionIncident

    tickets = list(FinalExamTicket.objects.filter(session=session).select_related("student"))
    ticket_map = {str(t.pk): t for t in tickets}
    attempt_ids = [t.attempt_id for t in tickets if t.attempt_id]

    events = []

    logs = (
        AuditLog.objects.filter(
            Q(resource_type="final_exam_ticket", resource_id__in=list(ticket_map.keys()))
            | Q(resource_type="exam_room_session", resource_id=str(session.pk))
        )
        .select_related("user")
        .order_by("created_at")
    )
    for log in logs:
        code, extra = _base_code(log.reason)
        if log.resource_type == "final_exam_ticket":
            spec = _TICKET_EVENTS.get(code)
            ticket = ticket_map.get(log.resource_id)
            student = (ticket.student.get_full_name() or ticket.student.username) if ticket else None
            seat = ticket.seat_number if ticket else None
        else:
            spec = _SESSION_EVENTS.get(code)
            student = None
            seat = None
        if spec is None:
            continue
        title, icon, tone = spec
        events.append(
            {
                "code": code,
                "time": log.created_at,
                "actor": (log.user.get_full_name() or log.user.username) if log.user else "Sistem",
                "student": student,
                "seat": seat,
                "title": title,
                "detail": _detail(code, log, extra),
                "icon": icon,
                "tone": tone,
            }
        )

    if attempt_ids:
        from django.utils.translation import gettext as _

        incidents = (
            SupervisionIncident.objects.filter(attempt_id__in=attempt_ids)
            .select_related("student")
            .order_by("timestamp")
        )
        for inc in incidents:
            student = (inc.student.get_full_name() or inc.student.username) if inc.student_id else None
            events.append(
                {
                    "code": "supervision_incident",
                    "time": inc.timestamp,
                    "actor": student or "Sistem",
                    "student": student,
                    "seat": None,
                    "title": inc.get_event_type_display(),
                    "detail": (
                        (_("Pozuntu sayı: %(n)s") % {"n": inc.violation_count_at_time})
                        if inc.violation_count_at_time
                        else ""
                    ),
                    "icon": "fa-triangle-exclamation",
                    "tone": "warn" if inc.severity in ("info", "low") else "danger",
                }
            )

    events.sort(key=lambda e: e["time"])
    return events


__all__ = ["session_history"]
