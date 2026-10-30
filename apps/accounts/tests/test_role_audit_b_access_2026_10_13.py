"""Rol auditi 2026-10-13, B hissəsi — «access» paketi (B3, B7, B14, B21).

Hesabat: ``docs/audits/2026-10-13-claude/ROL_AUDITI.md``. Hər test KÖHNƏ kodda qırılır:

* **B3** — «Müəllim idxalı» və RİM-in tək müəllim hesabı ``user.import_staff`` tələb edir; tələbə qəbulunun
  ``user.import`` açarı (Tələbə xidmətləri) artıq müəllim hesabı YARATMIR, HR isə tələbə hesabı yaratmır.
* **B7** — universitetdə ``member`` (xəritələnməmiş ofis heyəti) tələbə / imtahan verən səthlərini ALMIR,
  elan və sorğu auditoriyasında heyət sayılır; məktəb tenantında ``member`` öyrənən olaraq qalır.
* **B14** — «Bildiriş göndər» rol bayrağı ilə yox, ``notification.publish`` açarı ilə açılır (menyu + POST);
  şablonlar və miqrasiya ``organizations/0062`` bu gün bölməni görən rollara açarı verir.
* **B21** — menyu icazə yığımı deaktiv ROLU süzür (panel qapısı ilə eyni).
"""

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.services import intake
from apps.accounts.services.rim import RimAccessError
from apps.accounts.services.rim import create as rim_create
from apps.accounts.views._helpers.rbac import _collect_actor_permissions
from apps.accounts.views._helpers.rbac_member_sections import MEMBER_LEARNER_SECTIONS
from apps.notifications.models import InAppNotification
from apps.organizations.default_roles import DEFAULT_ROLES
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.permissions import PERMISSION_LABELS, get_all_permissions
from core.constants import OrganizationType, RoleScopeType
from core.permissions import has_permission
from core.rls import bypass_rls

from .test_rim_account_create import RimCreateBase, base_payload

PROFILE = "accounts:profile"


def _sections(client):
    response = client.get(reverse(PROFILE))
    assert response.status_code == 200, response.status_code
    return set(response.context["allowed_sections"])


@override_settings(RATELIMIT_ENABLE=False)
class _Base(RimCreateBase):
    """Real universitet şablonu (təşkilat yaradılarkən siqnal rolları əkir) + əlavə aktorlar."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        User = get_user_model()
        with bypass_rls():
            cls.services = User.objects.create_user("six_services", "six_services@qku.edu.az", "pw")
            cls.member = User.objects.create_user("six_member", "six_member@qku.edu.az", "pw")
            for user, role_name in ((cls.services, "student_services"), (cls.member, "member")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role_name),
                    is_primary=True,
                    is_active=True,
                )
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])


class TeacherIntakeGateTest(_Base):
    """B3 — müəllim idxalı (menyu + hər endpoint) `user.import_staff`-dır."""

    def test_template_keys(self):
        services = self.org.roles.get(name="student_services").permissions
        self.assertIn("user.import", services)
        self.assertNotIn("user.import_staff", services)
        self.assertIn("user.import_staff", self.org.roles.get(name="hr").permissions)
        self.assertIn("user.import_staff", get_all_permissions())
        self.assertFalse(intake.can_import_staff(self.services, self.org))
        self.assertTrue(intake.can_import_staff(self.hr, self.org))

    def test_student_services_loses_teacher_intake_but_keeps_student_intake(self):
        sections = _sections(self.client_for(self.services))
        self.assertIn("student-intake", sections)
        self.assertNotIn("teacher-intake", sections)

    def test_hr_sees_teacher_intake_only(self):
        sections = _sections(self.client_for(self.hr))
        self.assertIn("teacher-intake", sections)
        self.assertNotIn("student-intake", sections)

    def test_every_endpoint_denies_the_student_import_key(self):
        client = self.client_for(self.services)
        self.assertEqual(client.get(reverse("accounts:teacher_intake_template")).status_code, 403)
        for name in ("teacher_intake_preview", "teacher_intake_apply"):
            response = client.post(reverse("accounts:%s" % name), {})
            self.assertEqual(response.status_code, 403, name)
            self.assertEqual(response.json()["error"], "permission_denied")

    def test_staff_import_key_reaches_the_endpoints(self):
        response = self.client_for(self.hr).get(reverse("accounts:teacher_intake_template"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_section_context_is_gated_on_the_staff_key(self):
        response = self.client_for(self.hr).get(reverse(PROFILE), {"section": "teacher-intake"})
        self.assertTrue(response.context["teacher_intake_section"]["has_access"])


class RimCreatePerKindTest(_Base):
    """B3 — RİM-in tək hesab yaratması növə görə: tələbə `user.import`, müəllim `user.import_staff`."""

    def test_kind_keys(self):
        self.assertEqual(
            rim_create.KIND_PERMISSIONS,
            {"student": "user.import", "teacher": "user.import_staff", "staff": "user.import_staff"},
        )

    def test_student_import_key_cannot_create_a_teacher(self):
        actor = self.actor_for(self.services)
        self.assertEqual(rim_create.creatable_kinds(actor), ("student",))
        with self.assertRaises(RimAccessError) as caught:
            rim_create.create_account(actor, kind="teacher", data=base_payload(unit=str(self.chair.pk)))
        self.assertEqual(caught.exception.reason_code, "permission_denied")
        self.assertEqual(caught.exception.status, 403)

    def test_staff_import_key_cannot_create_a_student(self):
        with self.assertRaises(RimAccessError) as caught:
            rim_create.create_account(
                self.actor_for(self.hr), kind="student", data=base_payload(group=str(self.group.pk))
            )
        self.assertEqual(caught.exception.reason_code, "permission_denied")

    def test_staff_import_key_creates_a_teacher(self):
        result = rim_create.create_account(
            self.actor_for(self.hr), kind="teacher", data=base_payload(fin="2BBBBB2", unit=str(self.chair.pk))
        )
        self.assertEqual(result["kind"], "teacher")

    def test_catalogs_follow_the_form_kind(self):
        url = reverse("accounts:rim_create_catalog")
        self.assertEqual(self.client_for(self.hr).get(url, {"catalog": "group"}).status_code, 403)
        self.assertEqual(self.client_for(self.hr).get(url, {"catalog": "unit"}).status_code, 200)
        self.assertEqual(self.client_for(self.services).get(url, {"catalog": "unit"}).status_code, 403)
        self.assertEqual(self.client_for(self.services).get(url, {"catalog": "group"}).status_code, 200)

    def _create_block(self, user, kind):
        from apps.accounts.views.people.section import _create_block

        request = RequestFactory().get("/accounts/profile/")
        request.user = user
        request.organization = self.org
        return _create_block(request, kind)

    def test_directory_and_intake_offer_only_the_permitted_kind(self):
        self.assertTrue(self._create_block(self.services, "students")["can_create"])
        self.assertFalse(self._create_block(self.services, "teachers")["can_create"])
        self.assertTrue(self._create_block(self.hr, "teachers")["can_create"])
        self.assertFalse(self._create_block(self.hr, "students")["can_create"])
        chooser = self._create_block(self.hr, "teachers")["rim_create"]
        self.assertTrue(chooser["can_create_teacher"])
        self.assertFalse(chooser["can_create_student"])


class MemberIsOfficeStaffTest(_Base):
    """B7 — universitetdə `member` heyətdir: tələbə səthləri yox, heyət elan/sorğusu var."""

    def test_university_member_has_no_learner_sections(self):
        sections = _sections(self.client_for(self.member))
        self.assertEqual(sections & MEMBER_LEARNER_SECTIONS, set())

    def test_student_keeps_learner_sections(self):
        sections = _sections(self.client_for(self.student))
        self.assertTrue({"assigned-exams", "assigned-courses", "my-results", "pending-answers"} <= sections)

    def test_school_member_is_still_a_learner(self):
        User = get_user_model()
        with bypass_rls():
            school = Organization.objects.create(
                name="B7 School",
                slug="b7-school",
                org_type=OrganizationType.SCHOOL,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            user = User.objects.create_user("b7_school_member", "b7_member@example.com", "pw")
            Membership.objects.create(
                user=user, organization=school, role=school.roles.get(name="member"), is_primary=True, is_active=True
            )
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = school.slug
        session.save()
        sections = _sections(client)
        self.assertTrue({"courses", "assigned-exams", "assigned-courses", "my-results"} <= sections)

    def test_member_counts_as_staff_in_both_audiences(self):
        from apps.announcements.services import audience as announcement_audience
        from apps.surveys.services import audience as survey_audience

        self.assertEqual(announcement_audience.family_of("member"), "staff")
        self.assertEqual(survey_audience.family_of("member"), "staff")
        # Neytral ailə yerində qalır.
        self.assertIsNone(announcement_audience.family_of("alumni"))
        self.assertIsNone(survey_audience.family_of("alumni"))


class NotificationPublishKeyTest(_Base):
    """B14 — «Bildiriş göndər» açarla (menyu + POST); şablonlar bu gün görən rollara açarı verir."""

    #: Bu gün bölməni rol bayrağı ilə görən universitet rolları (`*` rolları açarı onsuz da əhatə edir).
    UNIVERSITY_HOLDERS = (
        "vice_rector",
        "dean",
        "vice_dean",
        "chair_head",
        "exam_center_head",
        "exam_center_staff",
        "rim_staff",
        "hr",
        "teacher",
        "assistant",
        "lab_assistant",
    )

    def _org_role(self, name, permissions, level=30):
        with bypass_rls():
            role, _ = Role.objects.update_or_create(
                organization=self.org,
                name=name,
                defaults={
                    "display_name": name,
                    "level": level,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": permissions,
                    "is_system": False,
                    "is_active": True,
                },
            )
        return role

    def _user_with(self, username, role):
        User = get_user_model()
        with bypass_rls():
            user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
            Membership.objects.create(user=user, organization=self.org, role=role, is_primary=True, is_active=True)
        return user

    def test_catalog_has_the_key(self):
        self.assertIn("notification.publish", get_all_permissions())
        self.assertTrue(str(PERMISSION_LABELS["notification.publish"]))

    def test_university_templates_grant_the_key(self):
        for name in self.UNIVERSITY_HOLDERS:
            with self.subTest(role=name):
                self.assertTrue(has_permission(self.org.roles.get(name=name).permissions, "notification.publish"))
        for name in ("student", "member", "student_services", "teaching_office_head"):
            with self.subTest(role=name):
                self.assertFalse(has_permission(self.org.roles.get(name=name).permissions, "notification.publish"))

    def test_non_university_templates_grant_the_key(self):
        expected = {
            OrganizationType.SCHOOL: {"director", "deputy_director", "section_head", "teacher"},
            OrganizationType.COURSE_CENTER: {"manager", "branch_manager", "instructor"},
            OrganizationType.INDIVIDUAL: {"owner"},
        }
        for org_type, names in expected.items():
            holders = {
                role["name"]
                for role in DEFAULT_ROLES[org_type]
                if has_permission(role["permissions"], "notification.publish")
            }
            self.assertEqual(holders, names, org_type)

    def test_key_opens_the_section_without_any_role_flag(self):
        user = self._user_with("b14_office", self._org_role("b14_office", ["notification.publish"]))
        self.assertIn("publish-notification", _sections(self.client_for(user)))

    def test_teacher_flag_without_the_key_no_longer_opens_it(self):
        user = self._user_with("b14_teacher", self._org_role("instructor", ["course.view"], level=50))
        sections = _sections(self.client_for(user))
        self.assertIn("my-exams", sections)  # müəllim bayrağı yerindədir
        self.assertNotIn("publish-notification", sections)

    def test_post_without_the_key_is_refused(self):
        user = self._user_with("b14_teacher_post", self._org_role("instructor", ["course.view"], level=50))
        response = self.client_for(user).post(
            reverse(PROFILE) + "?section=publish-notification",
            data={"profile_form": "publish-notification", "notif_title": "Salam", "notif_targets": ["all"]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("section=profile-info", response.url)
        self.assertFalse(InAppNotification.objects.filter(title="Salam").exists())

    def test_template_teacher_keeps_the_section(self):
        self.assertIn("publish-notification", _sections(self.client_for(self.teacher)))


class NotificationPublishMigrationTest(TestCase):
    """B14 — miqrasiya 0062: idempotent forward, `*`/wildcard rollara toxunmur, backward geri alır."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("b14_mig_owner", "b14_mig_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="B14 Mig",
                slug="b14-mig",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )

    def _role(self, name, permissions, level=30):
        with bypass_rls():
            role, _ = Role.objects.update_or_create(
                organization=self.org,
                name=name,
                defaults={
                    "display_name": name,
                    "level": level,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": permissions,
                    "is_active": True,
                },
            )
        return role

    def test_forward_backward(self):
        migration = importlib.import_module("apps.organizations.migrations.0062_notification_publish_key")
        teacher = self._role("teacher", ["course.view"])
        custom_high = self._role("b14_custom_head", ["unit.view"], level=85)
        exempt_high = self._role("teaching_office_head", ["unit.view"], level=85)
        star = self._role("rector", ["*"], level=100)
        plain = self._role("student", ["course.view"], level=10)
        with bypass_rls():
            migration.forward(django_apps, None)
            migration.forward(django_apps, None)  # idempotent
            for role in (teacher, custom_high, exempt_high, star, plain):
                role.refresh_from_db()
        self.assertEqual(teacher.permissions.count("notification.publish"), 1)
        self.assertIn("notification.publish", custom_high.permissions)
        self.assertNotIn("notification.publish", exempt_high.permissions)
        self.assertEqual(star.permissions, ["*"])
        self.assertNotIn("notification.publish", plain.permissions)
        with bypass_rls():
            migration.backward(django_apps, None)
            teacher.refresh_from_db()
        self.assertNotIn("notification.publish", teacher.permissions)


class InactiveRoleMenuPermissionsTest(_Base):
    """B21 — deaktiv rolun açarları menyu icazə yığımına düşmür."""

    def test_inactive_role_contributes_nothing(self):
        with bypass_rls():
            role = Role.objects.create(
                organization=self.org,
                name="b21_disabled",
                display_name="Disabled",
                level=30,
                scope_type=RoleScopeType.ORGANIZATION,
                permissions=["audit.view", "notification.publish"],
                is_active=False,
            )
            User = get_user_model()
            user = User.objects.create_user("b21_user", "b21_user@qku.edu.az", "pw")
            Membership.objects.create(user=user, organization=self.org, role=role, is_primary=True, is_active=True)
        effective, _grantable = _collect_actor_permissions(user, self.org)
        self.assertEqual(effective, set())

    def test_inactive_role_opens_no_menu_section(self):
        with bypass_rls():
            Role.objects.filter(organization=self.org, name="hr").update(is_active=False)
        sections = _sections(self.client_for(self.hr))
        self.assertNotIn("teacher-intake", sections)
        self.assertNotIn("audit-log", sections)
