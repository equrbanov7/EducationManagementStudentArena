"""
2026-09-14 (audit 2026-09-13, `findings/tests.md` §1 · F-T11) —
`apps/accounts/services/view_as.py::actor_can_use_view_as` 0 % coverage idi.

Bu, «view-as» panelinin GÖRÜNÜRLÜK qapısıdır (ucuz yoxlama): rol × təşkilat
matrisi `resolve_actor_access` ilə eyni cavabı verməli, superadmin isə
təşkilatsız da keçməlidir. Girişi bağlı (`staged`/`archived`) aktor rolu nə
olursa olsun paneli görmür — RLS view-as düzəlişindən (2026-09-12) sonra bu
qapı testsiz qalmışdı.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.accounts.models import ProfileRole, UserProfile
from apps.accounts.services.view_as import actor_can_use_view_as, resolve_actor_access
from apps.accounts.tests.test_view_as import PASSWORD, ViewAsTestBase, _add_member, _make_role
from apps.organizations.models import Membership

User = get_user_model()


class ActorCanUseViewAsTests(ViewAsTestBase):
    def setUp(self):
        super().setUp()
        self.exam_center = User.objects.create_user("w2v_exam_center", "w2v_ec@example.com", PASSWORD)
        _add_member(self.exam_center, self.org, _make_role(self.org, ProfileRole.EXAM_CENTER, 85))
        # Xəritədə OLMAYAN yüksək səviyyəli rol — səviyyə tək başına səlahiyyət vermir.
        self.unmapped = User.objects.create_user("w2v_unmapped", "w2v_unmapped@example.com", PASSWORD)
        _add_member(self.unmapped, self.org, _make_role(self.org, "vice_rector_unmapped", 95))

    def test_role_matrix_matches_resolve_actor_access(self):
        expectations = {
            "org_admin": (self.admin, True),
            "tutor_readonly": (self.tutor, True),
            "exam_center_limited": (self.exam_center, True),
            "owner_without_membership": (self.owner, True),
            "teacher": (self.teacher, False),
            "student": (self.student, False),
            "unmapped_high_level": (self.unmapped, False),
        }
        for label, (user, expected) in expectations.items():
            with self.subTest(actor=label):
                self.assertIs(actor_can_use_view_as(user, self.org), expected)
                mode, _level, _memberships = resolve_actor_access(user, self.org)
                self.assertIs(mode is not None, expected)

    def test_cross_tenant_role_does_not_carry_over(self):
        """A-nın org_admin-i B-də paneli görmür; B-nin sahibi A-da görmür."""
        self.assertFalse(actor_can_use_view_as(self.admin, self.other_org))
        self.assertFalse(actor_can_use_view_as(self.other_owner, self.org))
        self.assertTrue(actor_can_use_view_as(self.other_owner, self.other_org))

    def test_superadmin_passes_even_without_organization(self):
        self.assertTrue(actor_can_use_view_as(self.superadmin, self.org))
        self.assertTrue(actor_can_use_view_as(self.superadmin, None))
        # Profil rolu superadmin olan (superuser olmayan) da eyni.
        staff = User.objects.create_user("w2v_profile_super", "w2v_ps@example.com", PASSWORD)
        UserProfile.objects.filter(user=staff).update(role=ProfileRole.SUPERADMIN)
        staff.refresh_from_db()
        self.assertTrue(actor_can_use_view_as(staff, None))

    def test_missing_organization_denies_regular_actor(self):
        self.assertFalse(actor_can_use_view_as(self.admin, None))

    def test_none_and_anonymous_are_denied(self):
        self.assertFalse(actor_can_use_view_as(None, self.org))
        self.assertFalse(actor_can_use_view_as(AnonymousUser(), self.org))

    def test_inactive_membership_revokes_panel(self):
        Membership.objects.filter(user=self.admin, organization=self.org).update(is_active=False)
        self.assertFalse(actor_can_use_view_as(self.admin, self.org))

    def test_login_blocked_actor_is_denied_regardless_of_role(self):
        """Arxiv/staged hesab — org_admin olsa da, hətta superadmin olsa da panel yoxdur."""
        with mock.patch("apps.accounts.services.view_as.request_user_login_blocked", return_value=True):
            self.assertFalse(actor_can_use_view_as(self.admin, self.org))
            self.assertFalse(actor_can_use_view_as(self.superadmin, self.org))

    def test_login_block_is_read_from_current_access_state(self):
        """Real `access_state` (keş yox): `staged` hesab paneli itirir.

        DB trigger-i (`accounts_reject_active_staged_profile`) staged profilin
        `auth_user.is_active=False` olmasını tələb edir — əvvəl o, sonra vəziyyət.
        """
        self.assertTrue(actor_can_use_view_as(self.admin, self.org))
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        UserProfile.objects.filter(user=self.admin).update(access_state=UserProfile.AccessState.STAGED)
        # Yaddaşdakı obyekt köhnədir (is_active=True, profil keşi) — qapı DB-dən oxumalıdır.
        self.assertFalse(actor_can_use_view_as(self.admin, self.org))
