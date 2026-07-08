"""final_center paketi — tələbə kabineti üçün final imtahan konteksti.

Tələbənin profil/tapşırıq panelində final imtahanı üçün: PIN (yalnız görünmə
pəncərəsi daxilində), oturum vaxt aralığı və giriş vəziyyəti. Kabinetdən
imtahan BAŞLADILMIR — yalnız məlumat + PIN göstərilir; giriş `/exams/final/`
ünvanından PIN ilə edilir.
"""

from django.utils import timezone

from apps.exams.models import FinalExamTicket

from .pins import student_visible_pin


def student_final_exam_context(user, exam) -> dict:
    """
    Tələbənin bu final imtahanı üzrə bileti varsa kabinet konteksti qaytarır.

    Oturum sisteminin ləğvindən sonra (2026-07): vaxt pəncərəsi İMTAHANIN öz
    cədvəlindən (``exam.start_datetime``/``end_datetime``) gəlir — bilet zala
    yalnız giriş anında qoşulur, ona görə kabinetdə zal göstərilmir (istənilən
    zaldakı kompüterdən girmək olar). ``has_ticket=False`` — təyinat yoxdur.
    ``pin`` yalnız görünmə pəncərəsi daxilində və uyğun statuslarda dolur.
    """
    if not getattr(user, "is_authenticated", False):
        return {"has_ticket": False}

    ticket = (
        FinalExamTicket.objects.filter(student=user, exam=exam)
        .select_related("session", "session__room")
        .order_by("-created_at")
        .first()
    )
    if ticket is None:
        return {"has_ticket": False}

    now = timezone.now()
    start = exam.start_datetime
    end = exam.end_datetime
    within_window = bool(start and start <= now) and bool(not end or now <= end)
    return {
        "has_ticket": True,
        "pin": student_visible_pin(ticket),
        "status": ticket.status,
        "window_start": start,
        "window_end": end,
        "room_name": None,  # zaldan asılı deyil — istənilən zaldakı kompüterdən
        "session_state": ticket.session.state if ticket.session_id else None,
        "entry_open": within_window,
    }


__all__ = ["student_final_exam_context"]
