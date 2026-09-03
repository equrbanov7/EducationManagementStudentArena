"""R-8 — köçürülmüş (parolu «unusable») hesabın özü-özünə parol bərpası.

FAZA 27 auditinin P0 tapıntısı: köçürülmüş 8 543 hesabın parolu `!`-prefikslidir
(`set_unusable_password`), Django-nun `PasswordResetForm.get_users()` isə belə
hesabları QƏSDƏN süzür → `/accounts/password-reset/` sükutla «done» səhifəsinə
aparır, e-poçt GÖNDƏRMİR.  Nəticə: köçürülmüş istifadəçi nə parolla girə bilir,
nə də özü bərpa edə bilir.

Bu modul girişin açılmasının üç qapısını kilidləyir:

1. ``active`` + REAL e-poçt + unusable parol → OTP + link e-poçtu GEDİR və
   istifadəçi bərpadan sonra sistemə GİRİR;
2. ``staged`` / ``archived`` hesab → heç nə getmir (giriş bağlıdır);
3. ``@placeholder.invalid`` e-poçt → poçt getmir, istifadəçiyə RİM-ə müraciət
   göstərişi çıxır (bu domenə poçt marşrutlanmır — RFC 2606).
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import EmailOTP, UserProfile
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class MigratedAccountPasswordResetTests(TestCase):
    """Köçürülmüş hesabın parol bərpası — R-8."""

    def setUp(self):
        self.owner = User.objects.create_superuser(
            username="reset_root",
            email="reset-root@example.com",
            password="Root-Password-123!",
        )
        self.organization = Organization.objects.create(
            name="Reset University",
            slug="reset-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )

    def _migrated_user(self, *, username, email, access_state=UserProfile.AccessState.ACTIVE, is_active=True):
        """Köçürmənin çıxardığı hesab: parol YOXDUR (unusable), profil vəziyyəti verilir."""
        user = User.objects.create(username=username, email=email, is_active=is_active)
        user.set_unusable_password()
        user.save(update_fields=["password"])
        profile = user.profile
        profile.access_state = access_state
        profile.organization = self.organization
        profile.password_change_required = True
        profile.email_verified = False
        profile.save(update_fields=["access_state", "organization", "password_change_required", "email_verified"])
        return user

    def test_active_migrated_user_with_real_email_receives_reset_and_can_log_in(self):
        user = self._migrated_user(username="myedu.student.7944", email="migrated.student@example.com")
        self.assertFalse(user.has_usable_password())

        response = self.client.post(reverse("accounts:password_reset"), {"email": user.email})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(user.email, mail.outbox[0].to)

        otp = EmailOTP.objects.filter(user=user, purpose=EmailOTP.Purpose.PASSWORD_RESET).latest("created_at")
        code = getattr(otp, "_plain_code", None) or self._code_from_email(mail.outbox[0])
        self.assertTrue(code)

        done = self.client.post(
            reverse("accounts:password_reset_done"),
            {
                "email": user.email,
                "otp_code": code,
                "new_password1": "Migrated-Pass-2026!",
                "new_password2": "Migrated-Pass-2026!",
            },
        )
        self.assertEqual(done.status_code, 302, getattr(done, "context_data", {}).get("form", None))

        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())
        self.assertTrue(self.client.login(username=user.username, password="Migrated-Pass-2026!"))

        # İlk-giriş qapısı İKİNCİ dəfə saxlamır: OTP e-poçtu təsdiqlədi, parolu
        # istifadəçi özü qurdu — `FirstLoginPasswordMiddleware` şərtləri ödənib.
        user.profile.refresh_from_db()
        self.assertFalse(user.profile.password_change_required)
        self.assertTrue(user.profile.email_verified)
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_staged_and_archived_accounts_get_nothing(self):
        for state, username in (
            (UserProfile.AccessState.STAGED, "myedu.student.7945"),
            (UserProfile.AccessState.ARCHIVED, "myedu.student.7946"),
        ):
            with self.subTest(state=state):
                mail.outbox = []
                user = self._migrated_user(
                    username=username,
                    email=f"{username}@example.com",
                    access_state=state,
                    is_active=state != UserProfile.AccessState.STAGED,
                )
                response = self.client.post(reverse("accounts:password_reset"), {"email": user.email})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(mail.outbox, [])
                self.assertFalse(EmailOTP.objects.filter(user=user).exists())

    def test_placeholder_email_gets_rim_guidance_and_no_mail(self):
        user = self._migrated_user(
            username="myedu.student.7947",
            email="myedu.student.7947@placeholder.invalid",
        )
        response = self.client.post(reverse("accounts:password_reset"), {"email": user.email}, follow=False)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RİM")
        self.assertEqual(mail.outbox, [])
        self.assertFalse(EmailOTP.objects.filter(user=user).exists())

    def test_placeholder_email_guidance_does_not_depend_on_an_existing_account(self):
        """Enumerasiya sızmır: göstəriş YALNIZ domenə görədir, bazaya baxmır."""
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "nobody.at.all@placeholder.invalid"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RİM")
        self.assertEqual(mail.outbox, [])

    @staticmethod
    def _code_from_email(message):
        import re

        match = re.search(r"\b(\d{6})\b", message.body)
        return match.group(1) if match else ""
