"""İmtahan zalı sessiyasından çıxış (sahib 2026-10-21).

Zal çərçivəsindəki «Zaldan çıx» düyməsi: giriş markeri silinir, logout, növün giriş səhifəsinə
(``/exams/final/`` və ya ``/exams/midterm/``) yönləndirilir — HEÇ VAXT kabinetə yox.
"""

from __future__ import annotations

from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from apps.exams.services.center_exams import FINAL_KIND, end_hall_session, exam_kind, hall_session_ticket


@require_POST
def hall_session_exit(request):
    ticket = hall_session_ticket(request)
    kind = exam_kind(ticket.exam) if ticket is not None else FINAL_KIND
    return redirect(end_hall_session(request, kind))


__all__ = ["hall_session_exit"]
