"""İmtahan mərkəzi (final/midterm) tələbə səhifələrinin ortaq köməkçiləri.

``final_center.py`` (giriş) və ``final_center_waiting.py`` (gözləmə otağı) bölünəndə (2026-10-20, modul-ölçü
qapısı) ortaq qalan zal qapısı, otaq IP yoxlaması və bilet ``select_related`` siyahısı.
"""

from django.core.exceptions import PermissionDenied
from django.utils.translation import pgettext

from apps.exams.services.exam_center_gate import (
    ensure_hall_computer,
    final_exam_access_allowed,
    room_ip_access_allowed,
)
from apps.exams.services.exam_network import ExamNetworkDenied, final_entry_network_allowed

# İmtahan zalı interfeys dilləri (chrome gizli olduğu üçün öz seçicimiz).
FEXC_UI_LANGUAGES = (("az", "AZ"), ("en", "EN"), ("ru", "RU"))

TICKET_SELECT_RELATED = (
    "session",
    "session__room",
    "session__invigilator",
    "exam",
    "organization",
    "student",
    "attempt",
)


def ensure_hall_access(request, organization=None):
    """İmtahan zalı IP/CIDR qapısı (mövcud exam_center_gate xidməti).

    2026-10-13 (gecə): əvvəlcə universitet şəbəkəsi (``EXAM_FINAL_INTERNAL_ONLY``) — kənar zona
    ``ExamNetworkDenied`` alır, ``final_entry_network_guarded`` onu aydın 403 səhifəsinə/JSON-a çevirir.
    2026-10-21 (sahib, sərt zal rejimi): sonra QEYDLİ zal kompüteri — ``exam.hall_computer_check`` açıqdırsa
    qeydsiz kompüter ``HallComputerDenied`` alır (giriş forması da göstərilmir → xəbərdarlıq səhifəsi).
    ``organization`` — bilet məlumdursa onun org-u; giriş səhifəsində ``None`` (istənilən org-un zalı).
    """
    if not final_entry_network_allowed(request):
        raise ExamNetworkDenied()
    ensure_hall_computer(request, organization)
    if not final_exam_access_allowed(request):
        raise PermissionDenied(pgettext("exams.view.final_center.permission", "final_center_ip_not_allowed"))


def room_access_ok(request, room) -> bool:
    """Zalın qeydli kompüterlərinə görə IP qapısı (MAC identifikasiya, IP tətbiq)."""
    return room_ip_access_allowed(request, room)


def room_access_error():
    return pgettext(
        "exams.final_center.entry",
        "Bu kompüterdən imtahana giriş icazəsi yoxdur. Zəhmət olmasa zaldakı təyin olunmuş kompüterdən daxil olun.",
    )


__all__ = [
    "FEXC_UI_LANGUAGES",
    "TICKET_SELECT_RELATED",
    "ensure_hall_access",
    "room_access_error",
    "room_access_ok",
]
