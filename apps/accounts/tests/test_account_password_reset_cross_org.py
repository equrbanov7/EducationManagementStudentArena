"""Təhlükəsizlik baxışı 2026-09-30 (H3) — parol sıfırlama başqa təşkilatdakı səlahiyyəti də sayır.

A-da tələbə, B-də rektor (və ya B-nin sahibi / Django staff) olan hesabın parolunu
A-nın RİM rəhbəri sıfırlaya bilməməlidir — əks halda B-nin idarəçi hesabı ələ keçir.
Adi tələbə/müəllim hədəfləri əvvəlki kimi sıfırlanır.
"""

from __future__ import annotations

from apps.accounts.services.rim.credentials import set_temporary_password
from apps.accounts.services.rim.policy import PERM_CREDENTIALS, RimAccessError, RimActor
from apps.organizations.models import Membership

from .test_account_password_reset import PasswordResetTestBase, make_role


class CrossOrgAuthorityTests(PasswordResetTestBase):
    def _also_member_of_b(self, user, level, name):
        Membership.objects.create(
            user=user, organization=self.org_b, role=make_role(self.org_b, name, level), is_active=True
        )

    def test_student_who_is_rector_elsewhere_is_refused(self):
        self._also_member_of_b(self.student, 100, "rector")
        self.login(self.operator)

        response = self.reset(self.student)

        self.assertEqual(response.status_code, 403)
        self.assert_unchanged(self.student)

    def test_owner_of_another_org_is_refused(self):
        self.org_b.owner = self.student
        self.org_b.save(update_fields=["owner"])
        self.login(self.operator)

        response = self.reset(self.student)

        self.assertEqual(response.status_code, 403)
        self.assert_unchanged(self.student)

    def test_staff_account_is_refused(self):
        self.student.is_staff = True
        self.student.save(update_fields=["is_staff"])
        self.login(self.operator)

        response = self.reset(self.student)

        self.assertEqual(response.status_code, 403)
        self.assert_unchanged(self.student)

    def test_low_rank_membership_elsewhere_still_resettable(self):
        self._also_member_of_b(self.student, 10, "student")
        self.login(self.operator)

        response = self.reset(self.student)

        self.assertEqual(response.status_code, 200)

    def test_rim_credentials_path_uses_same_guard(self):
        self._also_member_of_b(self.teacher, 100, "rector")
        actor = RimActor(
            user=self.operator,
            organization=self.org,
            level=95,
            is_superadmin=False,
            permissions={PERM_CREDENTIALS},
        )

        with self.assertRaises(RimAccessError) as ctx:
            set_temporary_password(actor, self.teacher, reason="Müəllim parolu unudub")
        self.assertEqual(ctx.exception.reason_code, "target_rank_too_high")
        self.assert_unchanged(self.teacher)
