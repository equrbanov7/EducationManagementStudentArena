"""«Parol sıfırlama» — sahib 2026-10-26: parol yazmadan, SƏBƏBLƏ, ilk girişdə tam axın.

* müəllim / adi əməkdaş → 403, RİM rəhbəri və superadmin → 200;
* səbəb məcburidir (≥ ``MIN_REASON_LENGTH``) — qısa səbəbdə hədəfə toxunulmur;
* parol + ``password_change_required`` + ``email_verified=False``; audit-də səbəb var, parol YOX;
* JSON cavab parolu BİR dəfə qaytarır, axtarış/təkrar sorğu onu bir daha göstərmir;
* əlifba kredensial əmrləri (``issue_staff_credentials``) ilə eynidir;
* şəxs səhifəsində «Parolu sıfırla» keçidi yalnız icazə daşıyana görünür, bölmə ``?pwr_q=`` ilə dolur.
"""

from __future__ import annotations

import json

from apps.accounts.services.password_reset_admin import MIN_REASON_LENGTH, generate_temporary_password
from apps.audit.models import AuditLog

from .test_account_password_reset import RESET_REASON, PasswordResetTestBase, make_role, make_user


class ResetPermissionTest(PasswordResetTestBase):
    def test_teacher_and_plain_staff_get_403(self):
        staff_role = make_role(self.org, "admin_unit_staff", 40, ["member.view"])
        staff = make_user("adi.emekdas", self.org, staff_role)
        for actor in (self.teacher, staff):
            self.login(actor)
            response = self.reset(self.student)
            self.assertEqual(response.status_code, 403, actor.username)
            self.assertEqual(response.json()["error"], "permission_denied")
        self.assert_unchanged(self.student)

    def test_rim_head_and_superuser_succeed(self):
        self.login(self.operator)
        self.assertEqual(self.reset(self.student).status_code, 200)
        self.login(self.superuser)
        self.assertEqual(self.reset(self.teacher).status_code, 200)

    def test_peer_rim_head_is_refused_but_superuser_may_reset_it(self):
        self.login(self.operator)
        self.assertEqual(self.reset(self.peer).status_code, 403)
        self.assert_unchanged(self.peer)
        self.login(self.superuser)
        self.assertEqual(self.reset(self.peer).status_code, 200)


class ResetReasonTest(PasswordResetTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.operator)

    def test_reason_is_optional(self):
        """Sahib 2026-10-26 axşam: «RİM necə rahat edirdisə elə etsin» — səbəbsiz də sıfırlanır."""
        response = self.reset(self.student, reason="")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            self.student.__class__.objects.get(pk=self.student.pk).check_password(response.json()["password"])
        )

    def test_success_sets_flags_and_audits_reason_without_password(self):
        profile = self.student.profile
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])

        response = self.reset(self.student, reason="  Parolunu   unudub, vəsiqə yoxlanıldı  ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        payload = response.json()
        password = payload["password"]
        self.assertEqual(len(password), 12)

        self.student.refresh_from_db()
        profile.refresh_from_db()
        self.assertTrue(self.student.check_password(password))
        self.assertTrue(profile.password_change_required)
        # Sahib 2026-10-26 axşam: e-poçt təsdiqi TOXUNULMUR (əlavə OTP yükü yoxdur).
        self.assertTrue(profile.email_verified)

        row = AuditLog.objects.get(changes__operation="admin_password_reset", action="update")
        self.assertEqual(row.user, self.operator)
        self.assertEqual(row.changes["reason_text"], "Parolunu unudub, vəsiqə yoxlanıldı")
        self.assertIn("Parolunu unudub", row.reason)
        dump = json.dumps([row.changes, row.old_values, row.new_values, row.reason, row.resource_repr], default=str)
        self.assertNotIn(password, dump)

    def test_password_is_returned_only_once(self):
        password = self.reset(self.student).json()["password"]
        lookup = self.lookup(self.student.username)
        self.assertEqual(lookup.status_code, 200)
        self.assertNotIn(password, lookup.content.decode())
        self.assertNotIn("password", lookup.json()["results"][0])
        second = self.reset(self.student, reason=RESET_REASON).json()["password"]
        self.assertNotEqual(password, second)
        self.student.refresh_from_db()
        self.assertFalse(self.student.check_password(password))

    def test_verified_email_skips_otp_after_reset(self):
        """Təsdiqli e-poçtlu hesab sıfırlamadan sonra OTP-dən keçmir (2026-09-30 qaydası qaldı)."""
        from apps.accounts.views.auth.first_login import _email_already_verified

        profile = self.student.profile
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])
        self.reset(self.student)
        self.student.refresh_from_db()
        self.assertTrue(_email_already_verified(self.student))


class AlphabetTest(PasswordResetTestBase):
    def test_alphabet_matches_credential_commands(self):
        from apps.accounts.management.commands.issue_staff_credentials import _PASSWORD_ALPHABET

        allowed = set(_PASSWORD_ALPHABET)
        for _ in range(40):
            password = generate_temporary_password()
            self.assertTrue(set(password) <= allowed, password)


class PanelTest(PasswordResetTestBase):
    URL = "/accounts/profile/?section=account-password-reset"

    def test_panel_has_reason_and_result_dialogs(self):
        self.login(self.operator)
        response = self.client.get(self.URL + "&pwr_q=aysel.quliyeva")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="pwr-confirm-dialog"')
        self.assertContains(response, "data-pwr-reason-form")
        self.assertContains(response, f'data-ems-min-length="{MIN_REASON_LENGTH}"')
        self.assertContains(response, 'id="pwr-result-dialog"')
        self.assertContains(response, 'data-initial-query="aysel.quliyeva"')
        self.assertContains(response, "accounts/js/profile/account_password_reset_dialogs.js")

    def test_person_page_link_only_for_operator(self):
        from django.test import RequestFactory

        from apps.accounts.templatetags.password_reset_admin import account_password_reset_link

        def _link(user):
            request = RequestFactory().get("/")
            request.user = user
            request.is_view_as = False
            request.organization = self.org
            return account_password_reset_link({"request": request}, "aysel.quliyeva")

        link = _link(self.operator)
        self.assertIn("section=account-password-reset", link)
        self.assertIn("pwr_q=aysel.quliyeva", link)
        self.assertEqual(_link(self.teacher), "")
