"""İmtahan günü — GİRİŞ AXINI yoxlaması (yalnız-oxu).

Final imtahanı kabinetdən BAŞLADILA BİLMİR (assigned_tasks.py:205) — tələbə
`/exams/final/` səhifəsindən username + PIN ilə girir və `org_computer_access_allowed`
qapısından keçir. Bu skript həmin axının səhər işləyib-işləməyəcəyini yoxlayır:

  * hər tələbənin ExamStudentPin-i varmı (siqnalla avtomatik yaranmalı idi);
  * org-da aktiv qeydli kompüter varmı → varsa giriş YALNIZ onlardan mümkündür;
  * MAC məcburiyyəti aktivdirmi;
  * imtahan pəncərəsi və aktivlik.
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.exams.models import Exam, ExamRoom, ExamRoomComputer, ExamStudentPin
from apps.organizations.models import Organization
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()
USERNAMES = ["wcu_togrul_suleymanli", "wcu_turay_huseynov"]


def out(text=""):
    print(text)


@rls_worker_atomic()
@bypass_rls()
def main():
    org_slug = (os.environ.get("PROBE_ORG") or "qerbi-kaspi-universiteti").strip()
    organization = Organization.objects.filter(slug=org_slug).first()
    if organization is None:
        out(f"!! '{org_slug}' tapılmadı")
        return

    out("=" * 74)
    out("1) TƏLƏBƏ PIN-LƏRİ (final girişi bununla olur)")
    out("=" * 74)
    for username in USERNAMES:
        user = User.objects.filter(username=username).first()
        if user is None:
            out(f"  {username}: İSTİFADƏÇİ YOXDUR")
            continue
        pins = ExamStudentPin.objects.filter(student=user).select_related("exam")
        out(f"  {username}: {pins.count()} PIN")
        for pin in pins:
            out(
                f"      imtahan #{pin.exam_id} '{pin.exam.title[:44]}' revoked={bool(getattr(pin, 'revoked_at', None))}"
            )

    out("\n" + "=" * 74)
    out("2) KOMPÜTER QAPISI (org_computer_access_allowed)")
    out("=" * 74)
    computers = ExamRoomComputer.objects.filter(organization=organization, is_active=True)
    total = computers.count()
    out(f"  org-da AKTİV qeydli kompüter: {total}")
    if total == 0:
        out("  ✓ Qapı AÇIQDIR — istənilən kompüterdən giriş mümkündür.")
    else:
        out("  ⚠ Qapı BAĞLIDIR — giriş YALNIZ qeydli kompüterlərdən mümkündür:")
        for room in ExamRoom.objects.filter(organization=organization, is_active=True):
            room_count = computers.filter(room=room).count()
            if room_count:
                out(f"      zal '{room.name}' [{room.code}] — {room_count} kompüter")

    mac_mode = getattr(settings, "EXAM_CLIENT_MAC_RESOLUTION", "off")
    out(f"\n  MAC rejimi (EXAM_CLIENT_MAC_RESOLUTION, arp_agent = MAC məcburi): {mac_mode}")
    out(f"  FINAL_EXAM_ALLOWED_IPS: {getattr(settings, 'FINAL_EXAM_ALLOWED_IPS', 'unset')}")

    out("\n" + "=" * 74)
    out("3) İMTAHANLARIN VƏZİYYƏTİ")
    out("=" * 74)
    now = timezone.now()
    for exam in Exam.objects.filter(organization=organization, allowed_users__username__in=USERNAMES).distinct():
        in_window = bool(exam.start_datetime and exam.end_datetime and exam.start_datetime <= now <= exam.end_datetime)
        out(f"  #{exam.pk} {exam.title[:50]}")
        out(
            f"      tip={exam.exam_type}/{exam.exam_type_extended} aktiv={exam.is_active} sual={exam.questions.count()}"
        )
        out(f"      pəncərədə={in_window}  təyin={[u.username for u in exam.allowed_users.all()]}")


main()
