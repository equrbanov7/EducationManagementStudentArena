"""Test köməkçisi — cəhd üçün REAL zal sessiyası (2026-10-21).

Zal = bilet (``FinalExamTicket``, cəhdə bağlı) + sessiyada doğrulanmış bilet markeri və onun giriş nəsli
(``final_center.entry``) + cəhdin cihaz bağlantısı (``FinalAttemptDevice`` + sessiyadakı cihaz id-si).
"""

from __future__ import annotations

import hashlib
import secrets

from django.utils import timezone

from apps.exams.domain.final_center import TICKET_STATUS_COMPLETED
from apps.exams.models import FinalAttemptDevice, FinalExamTicket
from apps.exams.services.final_center.device_binding import DEVICE_SESSION_KEY
from apps.exams.services.final_center.entry import ENTRY_SESSION_KEY, ENTRY_VERSION_SESSION_KEY, _entry_version

#: Test müştərisinin defolt IP-si və appeals testlərinin universitet IP-si — qeydli zal kompüteri kimi.
HALL_TEST_IPS = ("127.0.0.1", "10.20.30.41")


def register_hall_computers(organization, ips=HALL_TEST_IPS):
    """Sərt zal rejimi (``exam.hall_computer_check``, defolt açıq) üçün aktiv qeydli zal kompüterləri."""
    from apps.exams.models import ExamRoom, ExamRoomComputer

    room, _ = ExamRoom.objects.get_or_create(
        organization=organization, name="Test zalı", defaults={"is_active": True, "is_exam_hall": True}
    )
    for ip in ips:
        octets = [int(part) for part in ip.split(".")]
        mac = "02:00:" + ":".join(f"{octet:02x}" for octet in octets)
        ExamRoomComputer.objects.get_or_create(
            organization=organization,
            room=room,
            ip_address=ip,
            defaults={"label": f"PC-{ip}", "mac_address": mac, "is_active": True},
        )
    return room


def enter_hall(client, attempt, *, device_id=None, bind_device=True, hall_computer=True):
    """``client``-i ``attempt``-in zal sessiyasına qoyur (defolt: qeydli zal kompüterindən); cihaz id-sini qaytarır."""
    if hall_computer:
        register_hall_computers(attempt.exam.organization)
    device_id = device_id or secrets.token_urlsafe(32)
    ticket, _created = FinalExamTicket.objects.get_or_create(
        exam=attempt.exam,
        student=attempt.user,
        defaults={
            "organization": attempt.exam.organization,
            "attempt": attempt,
            "status": TICKET_STATUS_COMPLETED,
            "entry_validated_at": timezone.now(),
        },
    )
    if bind_device:
        FinalAttemptDevice.objects.update_or_create(
            attempt=attempt,
            defaults={
                "organization": attempt.exam.organization,
                "token_hash": hashlib.sha256(f"{attempt.pk}:{device_id}".encode()).hexdigest(),
            },
        )
    session = client.session
    session[ENTRY_SESSION_KEY] = ticket.pk
    session[ENTRY_VERSION_SESSION_KEY] = _entry_version(ticket)
    session[DEVICE_SESSION_KEY] = device_id
    session.save()
    return device_id


def switch_device(client):
    """Eyni sessiya, BAŞQA cihaz id-si (bağlantı ilə üst-üstə düşmür)."""
    session = client.session
    session[DEVICE_SESSION_KEY] = secrets.token_urlsafe(32)
    session.save()


def leave_hall(client):
    session = client.session
    session.pop(ENTRY_SESSION_KEY, None)
    session.pop(ENTRY_VERSION_SESSION_KEY, None)
    session.save()


__all__ = ["HALL_TEST_IPS", "enter_hall", "leave_hall", "register_hall_computers", "switch_device"]
