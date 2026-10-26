"""«İstifadəçi adını dəyiş» — operator başqasının adını PAROLU BİLMƏDƏN dəyişir (sahib 2026-10-26).

* icazə: `account.password_reset` daşımayan (müəllim, adi əməkdaş) → 403; RİM rəhbəri və superadmin → 200;
* səbəb istəyə bağlıdır (sahib 2026-10-26 axşam), yazılsa audit-ə düşür;
* ad qaydası: kanonik (kiçik hərf), simvol/uzunluq/rezerv, cari addan fərqli, böyük-kiçik hərfə həssas
  olmayan unikallıq;
* superuser hədəf və eyni rütbəli RİM rəhbəri rədd edilir, yad tenant «tapılmadı»;
* audit sətrində köhnə/yeni ad + səbəb var, parol yoxdur;
* parol, ``email_verified``, ``password_change_required`` və hədəfin açıq sessiyası DƏYİŞMİR; yeni adla giriş
  işləyir, köhnə adla işləmir; hədəfə bildiriş gedir;
* «Avtomatik təklif» — ``ad.soyad`` / tutulubsa ``ad.soyad2``; kartda ``can_rename`` (bloklanmış hesaba da).
"""

from __future__ import annotations

import json

from django.apps import apps
from django.contrib.auth import authenticate, get_user
from django.http import HttpRequest
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import Membership

from .test_account_password_reset import PASSWORD, PasswordResetTestBase, make_role, make_user

REASON = "Soyad sənəddə fərqli yazılıb, müraciətlə düzəliş"
OPERATION = "admin_username_change"


class _Base(PasswordResetTestBase):
    def rename(self, target, new_username, reason=REASON, client=None):
        return (client or self.client).post(
            reverse("accounts:account_username_change_perform"),
            {"user_id": getattr(target, "pk", target), "new_username": new_username, "reason": reason},
            content_type="application/json",
        )

    def suggest(self, target, client=None):
        return (client or self.client).post(
            reverse("accounts:account_username_change_suggest"),
            {"user_id": getattr(target, "pk", target)},
            content_type="application/json",
        )

    def username_of(self, user):
        user.refresh_from_db()
        return user.username


class RenamePermissionTest(_Base):
    def test_non_holders_get_403_and_nothing_changes(self):
        staff_role = make_role(self.org, "admin_unit_staff", 40, ["member.view"])
        staff = make_user("adi.emekdas", self.org, staff_role)
        for actor in (self.teacher, staff):
            self.login(actor)
            response = self.rename(self.student, "aysel.yeni")
            self.assertEqual(response.status_code, 403, actor.username)
            self.assertEqual(response.json()["error"], "permission_denied")
        self.assertEqual(self.username_of(self.student), "aysel.quliyeva")

    def test_superuser_target_is_refused(self):
        Membership.objects.create(user=self.superuser, organization=self.org, role=self.student_role, is_active=True)
        self.login(self.operator)
        response = self.rename(self.superuser, "root.yeni")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "target_is_superadmin")
        self.assertEqual(self.username_of(self.superuser), "root_pwd")

    def test_same_rank_rim_head_refused_but_superuser_may_rename(self):
        self.login(self.operator)
        response = self.rename(self.peer, "peer.rehber.yeni")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "target_rank_too_high")
        self.assertEqual(self.username_of(self.peer), "rim.peer")
        self.assertTrue(AuditLog.objects.filter(action="deny", changes__operation=OPERATION).exists())

        self.login(self.superuser)
        self.assertEqual(self.rename(self.peer, "peer.rehber.yeni").status_code, 200)
        self.assertEqual(self.username_of(self.peer), "peer.rehber.yeni")

    def test_self_and_foreign_tenant_refused(self):
        self.login(self.operator)
        self.assertEqual(self.rename(self.operator, "rim.rehber2").json()["error"], "target_is_self")
        response = self.rename(self.foreign, "yad.yeni")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.username_of(self.foreign), "yad.telebe")


class RenameValidationTest(_Base):
    def setUp(self):
        super().setUp()
        self.login(self.operator)

    def test_reason_is_optional(self):
        """Sahib 2026-10-26 axşam: səbəb istəyə bağlıdır (RİM rahat işləsin)."""
        response = self.rename(self.student, "aysel.yeni", reason="")
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(self.username_of(self.student), "aysel.yeni")

    def test_uniqueness_is_case_insensitive(self):
        response = self.rename(self.student, "ELVIN.Aliyev")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "taken")
        self.assertEqual(self.username_of(self.student), "aysel.quliyeva")

    def test_invalid_names(self):
        cases = {
            "aysel quliyeva": "pattern",
            "aysel@mail.az": "pattern",
            "aysel..q": "pattern",
            ".aysel": "pattern",
            "ayşə.q": "pattern",
            "ay": "length",
            "a" * 31: "length",
            "admin": "reserved",
            "qa.aysel": "reserved",
            "": "required",
        }
        for value, code in cases.items():
            response = self.rename(self.student, value)
            self.assertEqual(response.status_code, 400, value)
            self.assertEqual(response.json()["error"], code, value)
            self.assertTrue(response.json()["message"], value)
        self.assertEqual(self.username_of(self.student), "aysel.quliyeva")

    def test_same_name_even_with_other_case_is_refused(self):
        response = self.rename(self.student, "  Aysel.Quliyeva ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "same")


class RenameSuccessTest(_Base):
    def test_only_username_changes_login_and_session_survive(self):
        profile = self.student.profile
        profile.email_verified = True
        profile.save(update_fields=["email_verified"])
        password_hash = self.student.password
        target_client = self.client_class()
        target_client.force_login(self.student)

        self.login(self.operator)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.rename(self.student, "  Aysel.Quliyeva.Yeni ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        payload = response.json()
        self.assertEqual(payload["old_username"], "aysel.quliyeva")
        self.assertEqual(payload["user"]["username"], "aysel.quliyeva.yeni")

        self.student.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(self.student.username, "aysel.quliyeva.yeni")
        self.assertEqual(self.student.password, password_hash)
        self.assertTrue(profile.email_verified)
        self.assertFalse(profile.password_change_required)
        self.assertIsNone(profile.username_changed_at)  # operator dəyişikliyi öz gözləmə müddətini başlatmır

        self.assertEqual(authenticate(username="aysel.quliyeva.yeni", password=PASSWORD), self.student)
        self.assertIsNone(authenticate(username="aysel.quliyeva", password=PASSWORD))

        # Hədəfin açıq sessiyası qalır (sessiya heşi parola bağlıdır, ada yox).
        request = HttpRequest()
        request.session = target_client.session
        self.assertEqual(get_user(request).pk, self.student.pk)

        notification = apps.get_model("notifications", "InAppNotification").objects.get(recipient=self.student)
        self.assertIn("aysel.quliyeva.yeni", notification.message)
        self.assertIn("RİM", notification.message)

    def test_audit_row_has_old_new_and_reason_without_password(self):
        self.login(self.operator)
        self.rename(self.student, "aysel.q2", reason="  Soyad sənəddə   fərqli yazılıb  ")

        row = AuditLog.objects.get(changes__operation=OPERATION, action="update")
        self.assertEqual(row.user, self.operator)
        self.assertEqual(row.old_values, {"username": "aysel.quliyeva"})
        self.assertEqual(row.new_values, {"username": "aysel.q2"})
        self.assertEqual(row.changes["old_username"], "aysel.quliyeva")
        self.assertEqual(row.changes["new_username"], "aysel.q2")
        self.assertEqual(row.changes["reason_text"], "Soyad sənəddə fərqli yazılıb")
        self.assertFalse(row.changes["password_changed"])
        dump = json.dumps([row.changes, row.old_values, row.new_values, row.reason], default=str)
        self.assertNotIn(PASSWORD, dump)

    def test_blocked_account_can_be_renamed_and_card_shows_it(self):
        self.student.is_active = False
        self.student.save(update_fields=["is_active"])
        self.login(self.operator)

        card = self.lookup("aysel.quliyeva").json()["results"][0]
        self.assertFalse(card["can_reset"])
        self.assertTrue(card["can_rename"])
        self.assertEqual(self.rename(self.student, "aysel.blok").status_code, 200)

    def test_deleted_account_is_refused(self):
        profile = self.student.profile
        profile.is_deleted = True
        profile.save(update_fields=["is_deleted"])
        self.login(self.operator)
        response = self.rename(self.student, "aysel.silinib")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "target_deleted")


class SuggestAndPanelTest(_Base):
    def test_suggestion_is_free_ad_soyad(self):
        self.login(self.operator)
        current = self.suggest(self.student).json()
        self.assertEqual(current, {"ok": True, "username": "aysel.quliyeva", "is_current": True})

        other = make_user("x.qeyri", self.org, self.student_role, first="Aysel", last="Quliyeva")
        payload = self.suggest(other).json()
        self.assertEqual(payload["username"], "aysel.quliyeva2")
        self.assertFalse(payload["is_current"])
        self.assertEqual(self.username_of(other), "x.qeyri")  # təklif YAZMIR

    def test_suggest_needs_permission(self):
        self.login(self.teacher)
        self.assertEqual(self.suggest(self.student).status_code, 403)

    def test_panel_has_rename_dialog(self):
        self.login(self.operator)
        response = self.client.get("/accounts/profile/?section=account-password-reset")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="pwr-rename-dialog"')
        self.assertContains(response, "data-pwr-rename-form")
        self.assertContains(response, "data-rename-url=")
        self.assertContains(response, "data-pwr-rename-suggest")
        self.assertContains(response, "accounts/js/profile/account_username_change.js")
