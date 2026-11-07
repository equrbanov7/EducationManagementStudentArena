"""Sahib 2026-11-07: kafedra müdiri «Təşkilat Admini» deyil.

* ``chair_head`` (→ ``department_head``) üzvlüyü ``org_admin`` aliası ALMIR (üzv/rol/təşkilat paneli yoxdur);
  dekan və açıq ``org_admin`` rolu dəyişmir;
* profil nişanında rolun öz adı — «Kafedra müdiri» — görünür, «Təşkilat Admini» yox;
* standart ``chair_head`` rolu ``journal.view`` daşıyır (öz kafedrasının jurnallarına baxış — siyahı/detal əhatəsi
  ``test_journal_view_kafedra_scope_2026_10_24``-dədir).
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.accounts.views.profile.context_builder._helpers import _build_effective_user_roles
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import bypass_rls
from core.roles import ProfileRole

User = get_user_model()


class ChairHeadAliasTest(SimpleTestCase):
    def test_chair_head_gets_no_org_admin_alias(self):
        for name in ("chair_head", "department_head", "section_head"):
            aliases = ProfileRole.aliases_for_membership_role(name, level=70)
            self.assertIn("department_head", aliases)
            self.assertNotIn(ProfileRole.ORG_ADMIN, aliases)

    def test_dean_and_explicit_admin_unchanged(self):
        self.assertIn(ProfileRole.ORG_ADMIN, ProfileRole.aliases_for_membership_role("dean", level=75))
        self.assertIn(ProfileRole.ORG_ADMIN, ProfileRole.aliases_for_membership_role(ProfileRole.ORG_ADMIN, level=80))


class ChairHeadProfileBadgeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("chb_owner", "chb_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="CHB Univ",
                slug="chb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            cls.user = User.objects.create_user("chb_head", "chb_head@qku.edu.az", "pw")
            for name, primary in (("chair_head", False), ("teacher", True)):
                Membership.objects.create(
                    user=cls.user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=name),
                    is_primary=primary,
                    is_active=True,
                )

    def test_badge_shows_chair_head_not_org_admin(self):
        self.user._active_organization = self.org  # sorğu middleware-i kimi
        with bypass_rls():
            labels = [str(row["label"]) for row in _build_effective_user_roles(self.user, None)]
        self.assertEqual(labels[0], "Kafedra müdiri")
        self.assertIn("Müəllim", labels)
        self.assertNotIn("Təşkilat Admini", labels)

    def test_default_chair_head_role_can_view_journals(self):
        with bypass_rls():
            self.assertIn("journal.view", self.org.roles.get(name="chair_head").permissions)
