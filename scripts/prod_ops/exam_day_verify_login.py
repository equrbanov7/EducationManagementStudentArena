"""Tələbələr parolla girə bilirmi və PIN-lərini görürmü — YALNIZ-OXU yoxlama.

Parol `EXAM_TEMP_PASSWORD` secret-indən gəlir və `check_password()` ilə hash-ə
qarşı yoxlanır: heç bir giriş edilmir, sessiya açılmır, parol log-a YAZILMIR.

PIN dəyəri də log-a yazılmır (GitHub run logları qalıcıdır) — yalnız görünüb-
görünmədiyi və uzunluğu bildirilir.

Yoxlananlar:
  * parol hash-i secret-dəki dəyərlə uyğun gəlirmi;
  * hesab giriş üçün yararlıdırmı (is_active, üzvlük aktiv);
  * OTP/ilk-giriş maneəsi söndürülübmü;
  * kabinetdə PIN görünürmü (`student_visible_pin` — UI-nin işlətdiyi funksiya).
"""

import os

from django.contrib.auth import get_user_model

from apps.exams.models import Exam
from apps.exams.services.student_pins import student_visible_pin
from apps.organizations.models import Membership, Organization
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

User = get_user_model()

ORG_SLUG = (os.environ.get("SEED_ORG") or "qerbi-kaspi-universiteti").strip()
PASSWORD = os.environ.get("EXAM_TEMP_PASSWORD") or ""
USERNAMES = [
    "wcu_togrul_suleymanli",
    "wcu_turay_huseynov",
    "wcu_elshen_emrahov",
]


def out(text=""):
    print(text)


def mark(ok):
    return "✓" if ok else "✗"


@rls_worker_atomic()
@bypass_rls()
def main():
    organization = Organization.objects.filter(slug=ORG_SLUG).first()
    if organization is None:
        out(f"!! '{ORG_SLUG}' tapılmadı")
        return
    if not PASSWORD:
        out("!! EXAM_TEMP_PASSWORD secret-i boşdur — parol yoxlanıla bilmir.")
        return

    out("=" * 74)
    out("GİRİŞ YOXLAMASI (parol secret-dən, log-a yazılmır)")
    out("=" * 74)

    for username in USERNAMES:
        user = User.objects.filter(username=username).first()
        out(f"\n{username}")
        if user is None:
            out("   ✗ İSTİFADƏÇİ YOXDUR")
            continue

        password_ok = user.check_password(PASSWORD)
        membership = Membership.objects.filter(user=user, organization=organization).first()
        profile = getattr(user, "profile", None)

        out(f"   {mark(password_ok)} parol secret-dəki dəyərlə uyğundur")
        out(f"   {mark(user.is_active)} hesab aktivdir (is_active)")
        out(f"   {mark(bool(membership and membership.is_active))} təşkilat üzvlüyü aktivdir")
        if profile is not None:
            no_otp = (not profile.password_change_required) and profile.email_verified
            out(f"   {mark(no_otp)} OTP/ilk-giriş maneəsi yoxdur")
            out(f"       (parol_dəyiş={profile.password_change_required} email_təsdiq={profile.email_verified})")
        else:
            out("   ✗ profil yoxdur")

    out("\n" + "=" * 74)
    out("KABİNETDƏ PIN GÖRÜNÜŞÜ (UI-nin işlətdiyi student_visible_pin)")
    out("=" * 74)
    for exam in Exam.objects.filter(organization=organization, allowed_users__username__in=USERNAMES).distinct():
        out(f"\n#{exam.pk} {exam.title[:52]}")
        for user in exam.allowed_users.all():
            pin = student_visible_pin(exam, user)
            if pin:
                out(f"   ✓ {user.username}: PIN görünür ({len(str(pin))} rəqəm) — dəyər log-a yazılmır")
            else:
                out(f"   ✗ {user.username}: PIN GÖRÜNMÜR (görünmə pəncərəsi və ya status maneəsi)")


main()
