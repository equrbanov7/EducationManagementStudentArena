"""«Parol sıfırlama» — uçdan-uca axın, bölmə, axtarış, audit, sessiyalar, login vedrələri.

Ssenari (sahib 2026-09-30): operator sıfırlayır → istifadəçi müvəqqəti parolla girir →
öz parolunu qurmağa məcbur edilir (OTP + yeni parol) → sonra sistem normal işləyir.
"""

from __future__ import annotations

import json
import re

from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.services.password_reset_admin import generate_temporary_password
from apps.audit.models import AuditLog
from core import rate_limit as rate_limit_module
from core.rate_limit import is_rate_limited, normalize_rate_identity, record_rate_limit_hit

from .test_account_password_reset import PASSWORD, PERM, PasswordResetTestBase, make_role, make_user

NEW_PASSWORD = "MyBrandNewPass789!"
_AMBIGUOUS = set("0O1lIio")


def _otp_code():
    match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


class GeneratorTest(PasswordResetTestBase):
    def test_password_is_readable_and_strong(self):
        for _ in range(50):
            password = generate_temporary_password()
            self.assertEqual(len(password), 12)
            self.assertFalse(set(password) & _AMBIGUOUS, password)
            self.assertTrue(any(c.isupper() for c in password))
            self.assertTrue(any(c.islower() for c in password))
            self.assertTrue(any(c.isdigit() for c in password))


class SectionTest(PasswordResetTestBase):
    URL = "/accounts/profile/?section=account-password-reset"

    def test_operator_sees_panel(self):
        self.login(self.operator)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn("account-password-reset", response.context["allowed_sections"])
        self.assertContains(response, 'data-profile-section-panel="account-password-reset"')
        self.assertContains(response, "data-pwr-root")
        self.assertContains(response, reverse("accounts:account_password_reset_perform"))
        self.assertContains(response, 'id="pwr-strings"')
        self.assertContains(response, "accounts/js/profile/account_password_reset.js")

    def test_superuser_sees_panel(self):
        self.login(self.superuser)
        response = self.client.get(self.URL)
        self.assertIn("account-password-reset", response.context["allowed_sections"])

    def test_user_without_permission_does_not_get_section(self):
        self.login(self.teacher)
        response = self.client.get(self.URL)
        self.assertNotIn("account-password-reset", response.context["allowed_sections"])
        self.assertNotContains(response, "data-pwr-root")

    def test_wildcard_role_gets_section(self):
        self.login(self.rector)
        response = self.client.get(self.URL)
        self.assertIn("account-password-reset", response.context["allowed_sections"])

    def test_no_inline_script_or_style_in_section_template(self):
        from pathlib import Path

        from django.conf import settings

        path = (
            Path(settings.BASE_DIR) / "apps/accounts/templates/accounts/profile/sections/_account_password_reset.html"
        )
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("<style", text)
        self.assertNotIn('style="', text)
        for match in re.finditer(r"<script(?P<attrs>[^>]*)>", text):
            self.assertIn("src=", match.group("attrs"))


class LookupTest(PasswordResetTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.operator)

    def test_exact_username_returns_confirmation_card(self):
        payload = self.lookup("AYSEL.QULIYEVA").json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "exact")
        [card] = payload["results"]
        self.assertEqual(card["username"], "aysel.quliyeva")
        self.assertEqual(card["full_name"], "Aysel Quliyeva")
        self.assertTrue(card["can_reset"])
        self.assertEqual(card["status"], "active")
        self.assertTrue(card["roles"])
        self.assertIn("last_login", card)
        # PII bu səthdə göstərilmir.
        self.assertNotIn("email", card)

    def test_tolerant_name_search(self):
        payload = self.lookup("Aliyev Elvin").json()
        self.assertEqual(payload["mode"], "search")
        self.assertEqual([row["username"] for row in payload["results"]], ["elvin.aliyev"])

    def test_foreign_tenant_is_invisible(self):
        payload = self.lookup("yad.telebe").json()
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["notice"], "")

    def test_higher_rank_exact_username_explains_reason(self):
        payload = self.lookup("rektor.user").json()
        self.assertEqual(payload["results"], [])
        self.assertTrue(payload["notice"])

    def test_query_too_short(self):
        response = self.lookup("a")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "query_too_short")

    def test_blocked_account_is_listed_but_not_resettable(self):
        self.student.is_active = False
        self.student.save(update_fields=["is_active"])
        [card] = self.lookup("aysel.quliyeva").json()["results"]
        self.assertFalse(card["can_reset"])
        self.assertEqual(card["status"], "blocked")
        self.assertTrue(card["reason"])


class ResetEffectsTest(PasswordResetTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.operator)

    def test_success_sets_temp_password_flag_and_audit_without_password(self):
        with self.assertLogs("apps.accounts", level="INFO") as logs:
            response = self.reset(self.student, HTTP_USER_AGENT="PwdTestAgent/1.0")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        payload = response.json()
        password = payload["password"]
        self.assertEqual(len(password), 12)
        self.assertTrue(payload["user"]["password_change_required"])

        self.student.refresh_from_db()
        self.student.profile.refresh_from_db()
        self.assertTrue(self.student.check_password(password))
        self.assertFalse(self.student.check_password(PASSWORD))
        self.assertTrue(self.student.profile.password_change_required)

        row = AuditLog.objects.filter(changes__operation="admin_password_reset", action="update").get()
        self.assertEqual(row.user, self.operator)
        self.assertEqual(row.organization, self.org)
        self.assertEqual(row.object_id, str(self.student.pk))
        self.assertEqual(row.user_agent, "PwdTestAgent/1.0")
        self.assertTrue(row.ip_address)
        self.assertIsNotNone(row.created_at)
        serialized = json.dumps(
            [row.changes, row.old_values, row.new_values, row.reason, row.resource_repr], default=str
        )
        self.assertNotIn(password, serialized)
        # Parol log-a da düşmür.
        self.assertNotIn(password, "\n".join(logs.output))

    def test_other_sessions_of_target_are_invalidated(self):
        target_client = Client()
        target_client.force_login(self.student)
        self.assertEqual(self.reset(self.student).status_code, 200)
        response = target_client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    @override_settings(RATELIMIT_ENABLE=True, LOGIN_ACCOUNT_RATE_LIMIT="3/1h")
    def test_account_login_bucket_is_cleared(self):
        from apps.accounts.views.auth.constants import LOGIN_LIMIT_SCOPE_ACCOUNT

        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        key = normalize_rate_identity(self.student.username)
        for _ in range(3):
            record_rate_limit_hit(LOGIN_LIMIT_SCOPE_ACCOUNT, "3/1h", key)
        self.assertTrue(is_rate_limited(LOGIN_LIMIT_SCOPE_ACCOUNT, "3/1h", key)[0])
        self.assertEqual(self.reset(self.student).status_code, 200)
        self.assertFalse(is_rate_limited(LOGIN_LIMIT_SCOPE_ACCOUNT, "3/1h", key)[0])


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EndToEndFlowTest(PasswordResetTestBase):
    def test_reset_then_forced_change_then_normal_use(self):
        # 1) Operator sıfırlayır.
        self.login(self.operator)
        password = self.reset(self.student).json()["password"]

        # 2) Tələbə müvəqqəti parolla (tələbə portalından) girir.
        student_client = Client()
        response = student_client.post(
            reverse("accounts:student_login"), {"username": "aysel.quliyeva", "password": password}
        )
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))

        # 3) Hər səhifə məcburi parol dəyişikliyinə yönləndirir.
        set_password_url = reverse("accounts:set_initial_password")
        response = student_client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], set_password_url)

        # 4) OTP + öz parolu.
        student_client.post(set_password_url, {"action": "send_otp", "email": "aysel.quliyeva@pwd.example.com"})
        response = student_client.post(
            set_password_url,
            {"action": "set_password", "code": _otp_code(), "password1": NEW_PASSWORD, "password2": NEW_PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:profile"))

        # 5) Artıq normal işləyir; müvəqqəti parol keçərsizdir.
        self.student.refresh_from_db()
        self.student.profile.refresh_from_db()
        self.assertFalse(self.student.profile.password_change_required)
        self.assertTrue(self.student.check_password(NEW_PASSWORD))
        self.assertFalse(self.student.check_password(password))
        self.assertEqual(student_client.get(reverse("accounts:profile")).status_code, 200)

        fresh = Client()
        response = fresh.post(reverse("accounts:student_login"), {"username": "aysel.quliyeva", "password": password})
        self.assertEqual(response.status_code, 200)  # forma səhvlə qayıdır — köhnə parol işləmir
        response = fresh.post(
            reverse("accounts:student_login"), {"username": "aysel.quliyeva", "password": NEW_PASSWORD}
        )
        self.assertEqual(response.status_code, 302)

    def test_delegated_role_flow_for_teacher(self):
        """RİM rəhbərindən başqa (açar verilmiş) rol müəllimin də parolunu sıfırlaya bilir."""
        office = make_user("kadr.isci", self.org, make_role(self.org, "hr_clerk", 70, [PERM]))
        self.login(office)
        password = self.reset(self.teacher).json()["password"]
        teacher_client = Client()
        response = teacher_client.post(
            reverse("accounts:staff_login"), {"username": "elvin.aliyev", "password": password}
        )
        self.assertEqual(response.status_code, 302)
        response = teacher_client.get(reverse("accounts:profile"))
        self.assertEqual(response["Location"], reverse("accounts:set_initial_password"))
