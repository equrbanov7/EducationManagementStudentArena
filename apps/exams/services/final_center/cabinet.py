"""final_center paketi — tələbə kabineti üçün final imtahan konteksti.

Tələbənin profil/tapşırıq panelində final imtahanı üçün: PIN (yalnız görünmə
pəncərəsi daxilində), oturum vaxt aralığı və giriş vəziyyəti. Kabinetdən
imtahan BAŞLADILMIR — yalnız məlumat + PIN göstərilir; giriş `/exams/final/`
ünvanından PIN ilə edilir.
"""

from apps.exams.domain.final_center import ROOM_SESSION_STATE_CANCELLED
from apps.exams.models import FinalExamTicket

from .pins import student_visible_pin


def student_final_exam_context(user, exam) -> dict:
    """
    Tələbənin bu final imtahanı üzrə bileti varsa kabinet konteksti qaytarır.

    ``has_ticket=False`` — bilet təyin olunmayıb (mərkəz hələ təyinat etməyib).
    ``pin`` yalnız görünmə pəncərəsi daxilində və uyğun statuslarda dolur
    (bax: ``student_visible_pin``), əks halda None.
    """
    if not getattr(user, "is_authenticated", False):
        return {"has_ticket": False}

    ticket = (
        FinalExamTicket.objects.filter(student=user, exam=exam)
        .exclude(session__state=ROOM_SESSION_STATE_CANCELLED)
        .select_related("session", "session__room")
        .order_by("session__scheduled_start")
        .first()
    )
    if ticket is None:
        return {"has_ticket": False}

    session = ticket.session
    return {
        "has_ticket": True,
        "pin": student_visible_pin(ticket),
        "status": ticket.status,
        "window_start": session.scheduled_start,
        "window_end": session.scheduled_end,
        "room_name": session.room.name,
        "session_state": session.state,
        "entry_open": session.state in ("entry_open", "active"),
    }


__all__ = ["student_final_exam_context"]
