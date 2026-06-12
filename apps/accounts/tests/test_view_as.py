"""
"View as" (istifadəçi profilinə baxış) testləri.

Təhlükəsizlik fokusu:
- tenant izolyasiyası (başqa org-un istifadəçisinə keçid QADAĞANDIR),
- rol iyerarxiyası (aşağı səviyyə yuxarını görə bilməz),
- readonly rejimdə unsafe metodların bloklanması,
- FULL rejimdə belə həssas əməliyyatların (şifrə/hesab) bloklanması,
- superuser hədəf ola bilməz, nested view-as yoxdur.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.accounts.services.view_as import (
    MODE_FULL,
    MODE_READONLY,
    VIEW_AS_SESSION_KEY,
    resolve_actor_access,
    validate_target,
)
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"


def _make_role(organization, name, level, permissions=None):
    role, _ = Role.objects.update_or_create(
        organization=organization,
        name=name,
        defaults={
            "display_name": name.replace("_", " ").title(),
            "level": level,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": permissions or [],
            "is_system": False,
            "is_active": True,
        },
    )
    return role


def _add_member(user, organization, role):
    return Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": role, "is_active": True, "is_primary": True},
    )[0]


class ViewAsTestBase(TestCase):
    def setUp(self):
        self.client = Client()

        self.owner = User.objects.create_user("org_owner", "owner@example.com", PASSWORD)
        self.org = Organization.objects.create(
            name="Test Univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.other_owner = User.objects.create_user("other_owner", "other@example.com", PASSWORD)
        self.other_org = Organization.objects.create(
            name="Other Univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.other_owner,
            status="active",
            is_active=True,
        )

        self.admin_role = _make_role(self.org, ProfileRole.ORG_ADMIN, 80)
        self.teacher_role = _make_role(self.org, ProfileRole.TEACHER, 60)
        self.student_role = _make_role(self.org, ProfileRole.STUDENT, 10)
        self.tutor_role = _make_role(self.org, "tutor", 40)

        self.admin = User.objects.create_user("org_admin", "admin@example.com", PASSWORD)
        self.teacher = User.objects.create_user("teacher1", "teacher@example.com", PASSWORD)
        self.student = User.objects.create_user("student1", "student@example.com", PASSWORD)
        self.tutor = User.objects.create_user("tutor1", "tutor@example.com", PASSWORD)
        _add_member(self.admin, self.org, self.admin_role)
        _add_member(self.teacher, self.org, self.teacher_role)
        self.student_membership = _add_member(self.student, self.org, self.student_role)
        self.tutor_membership = _add_member(self.tutor, self.org, self.tutor_role)

        # Tyutor unit-scoped roldur: tələbə ilə eyni unitə bağlanır.
        self.unit = OrgUnit.objects.create(
            organization=self.org,
            unit_type=OrgUnitType.FACULTY,
            name="Test Faculty",
            slug="test-faculty",
            is_active=True,
        )
        self.tutor_membership.scope_unit = self.unit
        self.tutor_membership.save(update_fields=["scope_unit"])
        self.student_membership.scope_unit = self.unit
        self.student_membership.save(update_fields=["scope_unit"])

        other_student_role = _make_role(self.other_org, ProfileRole.STUDENT, 10)
        self.other_student = User.objects.create_user("student2", "student2@example.com", PASSWORD)
        _add_member(self.other_student, self.other_org, other_student_role)

        self.superadmin = User.objects.create_superuser("root", "root@example.com", PASSWORD)

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _start(self, target, org=None):
        data = {"user_id": target.pk}
        if org is not None:
            data["org"] = org.pk
        return self.client.post(reverse("accounts:view_as_start"), data)


class ViewAsPermissionTests(ViewAsTestBase):
    def test_org_admin_gets_full_mode(self):
        mode, level, _m = resolve_actor_access(self.admin, self.org)
        self.assertEqual(mode, MODE_FULL)
        self.assertGreaterEqual(level, 80)

    def test_tutor_gets_readonly_mode(self):
        mode, _level, _m = resolve_actor_access(self.tutor, self.org)
        self.assertEqual(mode, MODE_READONLY)

    def test_student_has_no_access(self):
        mode, _level, _m = resolve_actor_access(self.student, self.org)
        self.assertIsNone(mode)

    def test_cross_org_target_rejected(self):
        """Tenant izolyasiyası: başqa org-un istifadəçisi hədəf ola bilməz."""
        target, mode = validate_target(self.admin, self.org, self.other_student.pk)
        self.assertIsNone(target)
        self.assertIsNone(mode)

    def test_superuser_cannot_be_target(self):
        _add_member(self.superadmin, self.org, self.student_role)
        target, _mode = validate_target(self.admin, self.org, self.superadmin.pk)
        self.assertIsNone(target)

    def test_hierarchy_lower_cannot_view_higher(self):
        """Tyutor (40) müəllimi (60) görə bilməz."""
        target, _mode = validate_target(self.tutor, self.org, self.teacher.pk)
        self.assertIsNone(target)

    def test_tutor_can_view_student_in_own_unit(self):
        target, mode = validate_target(self.tutor, self.org, self.student.pk)
        self.assertIsNotNone(target)
        self.assertEqual(mode, MODE_READONLY)

    def test_tutor_cannot_view_student_outside_unit(self):
        """Unit scoping: tələbə tyutorun alt-ağacından çıxarılırsa görünmür."""
        self.student_membership.scope_unit = None
        self.student_membership.save(update_fields=["scope_unit"])
        target, _mode = validate_target(self.tutor, self.org, self.student.pk)
        self.assertIsNone(target)


class ViewAsFlowTests(ViewAsTestBase):
    def test_admin_starts_and_profile_shows_target(self):
        self._login(self.admin)
        response = self._start(self.teacher)
        self.assertEqual(response.status_code, 302)
        self.assertIn(VIEW_AS_SESSION_KEY, self.client.session)

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        # request.user hədəflə əvəzlənir → kontekstdəki user müəllimdir.
        self.assertEqual(response.context["user"].pk, self.teacher.pk)
        view_as = response.context["view_as"]
        self.assertTrue(view_as["active"])
        self.assertEqual(view_as["mode"], MODE_FULL)
        self.assertEqual(view_as["real_user"].pk, self.admin.pk)

    def test_readonly_blocks_unsafe_methods(self):
        self._login(self.tutor)
        self._start(self.student)
        self.assertIn(VIEW_AS_SESSION_KEY, self.client.session)

        response = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "edit-profile", "first_name": "Hack"},
        )
        # Bloklanır və redirect (HTML) qaytarılır.
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertNotEqual(self.student.first_name, "Hack")

        json_response = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "edit-profile"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(json_response.status_code, 403)

    def test_full_mode_blocks_sensitive_forms(self):
        self._login(self.admin)
        self._start(self.teacher)

        response = self.client.post(
            reverse("accounts:profile"),
            {"profile_form": "change-password", "new_password1": "x", "new_password2": "x"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("accounts:delete_account"),
            {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)

    def test_student_cannot_start(self):
        self._login(self.student)
        self._start(self.teacher)
        self.assertNotIn(VIEW_AS_SESSION_KEY, self.client.session)

    def test_cross_org_start_rejected(self):
        self._login(self.admin)
        self._start(self.other_student)
        self.assertNotIn(VIEW_AS_SESSION_KEY, self.client.session)

    def test_stop_returns_to_self(self):
        self._login(self.admin)
        self._start(self.teacher)
        response = self.client.post(reverse("accounts:view_as_stop"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(VIEW_AS_SESSION_KEY, self.client.session)

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.context["user"].pk, self.admin.pk)

    def test_nested_view_as_rejected(self):
        self._login(self.admin)
        self._start(self.teacher)
        state_before = dict(self.client.session[VIEW_AS_SESSION_KEY])
        # Aktiv sessiya içində yenidən start → middleware unsafe POST-u
        # icazəli sayır (full), amma view nested keçidi rədd edir.
        self._start(self.student)
        self.assertEqual(self.client.session[VIEW_AS_SESSION_KEY]["target_id"], state_before["target_id"])

    def test_search_api_excludes_cross_org_and_superuser(self):
        self._login(self.admin)
        response = self.client.get(reverse("accounts:view_as_search"), {"type": "users"})
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(self.teacher.pk, ids)
        self.assertIn(self.student.pk, ids)
        self.assertNotIn(self.other_student.pk, ids)
        self.assertNotIn(self.superadmin.pk, ids)
        self.assertNotIn(self.admin.pk, ids)

    def test_search_api_forbidden_for_student(self):
        self._login(self.student)
        response = self.client.get(reverse("accounts:view_as_search"), {"type": "users"})
        self.assertEqual(response.status_code, 403)

    def test_org_search_superadmin_only(self):
        self._login(self.admin)
        response = self.client.get(reverse("accounts:view_as_search"), {"type": "orgs"})
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.superadmin)
        response = self.client.get(reverse("accounts:view_as_search"), {"type": "orgs"})
        self.assertEqual(response.status_code, 200)
        names = {row["name"] for row in response.json()["results"]}
        self.assertIn("Test Univ", names)

    def test_superadmin_cross_org_start(self):
        self.client.force_login(self.superadmin)
        response = self._start(self.other_student, org=self.other_org)
        self.assertEqual(response.status_code, 302)
        self.assertIn(VIEW_AS_SESSION_KEY, self.client.session)

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.context["user"].pk, self.other_student.pk)
        # Org konteksti hədəfin org-una keçir.
        self.assertEqual(self.client.session["active_organization"], self.other_org.slug)
