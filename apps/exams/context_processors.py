"""Şablon konteksti — imtahan zalı sessiyasının «chrome»-suz çərçivəsi (sahib 2026-10-21).

Sahib: «İmtahan zalında imtahan verərkən midterm və ya final — yuxarıdakı header görünməməlidir, nəticəyə baxanda
da olmaz». ``base.html`` bu bayrağa baxır: zal sessiyasında (doğrulanmış bilet markeri) sayt başlığı, ⌘K axtarış,
«Qoşul», dil menyusu, istifadəçi menyusu, AI düyməsi, footer, elan popup-u render OLUNMUR — yerinə minimal zal
çərçivəsi (universitet nişanı + imtahan adı + eyni səhifədə dil seçici + «Zaldan çıx») gəlir.

Qərar YEGANƏ yerdədir: ``apps.exams.services.center_exams.hall_session_active``. Bayraq ucuzdur (sessiya oxusu);
imtahan adı yalnız şablon ona müraciət edəndə bir dar sorğu ilə gətirilir.
"""

from __future__ import annotations

from django.utils.functional import cached_property


class HallChrome:
    """``{{ hall_chrome.active }}`` / ``{{ hall_chrome.exam_title }}`` / ``{{ hall_chrome.kind }}``."""

    def __init__(self, request):
        self._request = request

    @cached_property
    def active(self) -> bool:
        from apps.exams.services.center_exams import hall_session_active

        try:
            return hall_session_active(self._request)
        except Exception:  # noqa: BLE001 — çərçivə qərarı səhifəni sındırmasın
            return False

    @cached_property
    def _ticket(self):
        if not self.active:
            return None
        from apps.exams.services.center_exams import hall_session_ticket

        try:
            return hall_session_ticket(self._request)
        except Exception:  # noqa: BLE001
            return None

    @cached_property
    def exam_title(self) -> str:
        ticket = self._ticket
        return getattr(getattr(ticket, "exam", None), "title", "") or ""

    @cached_property
    def kind(self) -> str:
        from apps.exams.services.center_exams import exam_kind

        ticket = self._ticket
        return exam_kind(ticket.exam) if ticket is not None else ""

    def __bool__(self) -> bool:
        return self.active


def hall_session_chrome(request):
    return {"hall_chrome": HallChrome(request)}
