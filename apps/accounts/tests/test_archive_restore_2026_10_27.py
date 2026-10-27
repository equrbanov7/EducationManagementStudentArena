"""«Arxivdən çıxar» — səhvən «məzun» (arxiv) sayılmış CARİ tələbənin girişi (sahib 2026-10-27).

Hesablar məhsul qapılarından REAL keçir: ``stage_imported_account`` → ``archive_staged_account`` (arxiv), bərpa
isə ``restore_archived_account`` (0018 funksiyası + bərpa sübutu) ilə — PostgreSQL trigger-ləri bu testlərdə
həqiqətən işləyir.
"""

from __future__ import annotations

import hashlib
import io
import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.identity_models import AccountRestoreEvidence
from apps.accounts.models import UserProfile
from apps.accounts.public import archive_staged_account, stage_imported_account
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()
URL = "/accounts/rim/archive-restore/"
RIM_BASE = ["user.search", "user.credentials", "account.password_reset"]


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _role(organization, name, level, permissions=()):
    role, _ = Role.objects.update_or_create(
        organization=organization,
        name=name,
        defaults={
            "display_name": name,
            "level": level,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": list(permissions),
            "is_active": True,
        },
    )
    return role


def _org(slug, owner):
    organization = Organization.objects.create(
        name=slug.upper(), slug=slug, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )
    _role(organization, "student", 10)
    _role(organization, "alumni", 1)
    return organization


@override_settings(RATELIMIT_ENABLE=False)
class ArchiveRestoreTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("arx_root", "arx-root@example.test", "pw-root-123")
        cls.org = _org("arx-univ", cls.root)
        cls.other_org = _org("arx-other", cls.root)
        cls.head_role = _role(cls.org, "ikt_rehber", 88, [*RIM_BASE, "member.edit"])
        cls.staff_role = _role(cls.org, "rim_staff", 60, RIM_BASE)
        cls.head = cls._staff("arx.head", cls.head_role)
        cls.staff = cls._staff("arx.staff", cls.staff_role)

        unit = OrgUnit.objects.create
        faculty = unit(organization=cls.org, name="Fakültə", slug="arx-f", unit_type=OrgUnitType.FACULTY)
        cls.group = unit(organization=cls.org, name="131 T", slug="arx-g", unit_type=OrgUnitType.GROUP, parent=faculty)
        cls.expelled = unit(
            organization=cls.org, name="Xaric 2024", slug="arx-x", unit_type=OrgUnitType.GROUP, parent=faculty
        )
        cls.program = Program.objects.create(organization=cls.org, code="AR", name="Arxiv proqramı")
        cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2023)

    @classmethod
    def _staff(cls, username, role):
        user = User.objects.create_user(username, f"{username}@example.test", "pw-staff-123")
        profile = user.profile
        profile.organization = cls.org
        profile.save(update_fields=["organization", "updated_at"])
        Membership.objects.create(user=user, organization=cls.org, role=role, is_active=True, is_primary=True)
        return user

    def archived(self, key, *, organization=None, group="group", admission_year=1950, record=True):
        organization = organization or self.org
        staged = stage_imported_account(
            organization=organization,
            role=Role.objects.get(organization=organization, name="student"),
            actor=self.root,
            username=f"arx.student.{key}",
            email=f"arx.student.{key}@example.test",
            student_identifier=f"arx-{key}",
        )
        alumni = Role.objects.get(organization=organization, name="alumni")
        Membership.objects.filter(user=staged.user, organization=organization).update(role=alumni)
        archive_staged_account(
            user=staged.user,
            organization=organization,
            expected_role=alumni,
            actor=self.root,
            email_authoritative=True,
            email_authority_evidence_digest=_digest(f"archive-{key}"),
            email_authority_reason_code="institution_registry_match",
        )
        if record and organization == self.org:
            StudentAcademicRecord.objects.create(
                organization=organization,
                student=staged.user,
                program=self.program,
                curriculum=self.curriculum,
                group=getattr(self, group),
                admission_year=admission_year,
                status="enrolled",
            )
        return staged.user

    def login(self, user):
        self.client = Client()
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def post(self, user, **data):
        return self.client.post(URL, json.dumps({"user_id": user.pk, **data}), content_type="application/json")

    def state(self, user):
        return UserProfile.objects.get(user=user).access_state


class ArchiveRestoreEndpointTest(ArchiveRestoreTestBase):
    def test_permission_denied_without_member_edit(self):
        student = self.archived("perm")
        self.login(self.staff)
        response = self.post(student, reason="Tələbə oxuyur")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "permission_denied")
        self.assertEqual(self.state(student), "archived")

    def test_cross_tenant_target_is_not_found(self):
        foreign = self.archived("foreign", organization=self.other_org)
        self.login(self.head)
        response = self.post(foreign, reason="Tələbə oxuyur")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.state(foreign), "archived")

    def test_expelled_group_is_refused(self):
        student = self.archived("xaric", group="expelled")
        self.login(self.head)
        response = self.post(student, reason="Tələbə oxuyur")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "expelled_group")
        self.assertEqual(self.state(student), "archived")

    def test_without_active_record_is_refused(self):
        student = self.archived("norecord", record=False)
        self.login(self.head)
        response = self.post(student, reason="Tələbə oxuyur")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "no_active_record")
        self.assertEqual(self.state(student), "archived")

    def test_reason_is_required(self):
        student = self.archived("noreason")
        self.login(self.head)
        response = self.post(student, reason=" ")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "reason_required")
        self.assertEqual(self.state(student), "archived")

    def test_success_activates_account_with_audit_and_evidence(self):
        student = self.archived("ok", admission_year=2022)
        self.login(self.head)
        response = self.post(student, reason="131 T qrupunda oxuyur, səhv arxiv")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"] and body["restored"])
        self.assertEqual(body["user"]["status"], "active")
        self.assertEqual(self.state(student), "active")
        membership = Membership.objects.get(user=student, organization=self.org)
        self.assertEqual(membership.role.name, "student")
        self.assertTrue(AccountRestoreEvidence.objects.filter(user_ref=str(student.pk)).exists())
        log = AuditLog.objects.filter(object_id=str(student.pk), reason__startswith="archive_restore:").get()
        self.assertEqual(log.changes["reason_text"], "131 T qrupunda oxuyur, səhv arxiv")
        self.assertEqual(log.user, self.head)

    def test_admission_year_fixed_only_from_sentinel(self):
        sentinel = self.archived("sentinel", admission_year=1950)
        real = self.archived("real", admission_year=2022)
        self.login(self.head)
        self.assertEqual(self.post(sentinel, reason="Səhv arxiv", admission_year="2023").status_code, 200)
        self.assertEqual(self.post(real, reason="Səhv arxiv", admission_year="2023").status_code, 200)
        self.assertEqual(StudentAcademicRecord.objects.get(student=sentinel).admission_year, 2023)
        self.assertEqual(StudentAcademicRecord.objects.get(student=real).admission_year, 2022)

    def test_admission_year_out_of_range_is_refused(self):
        student = self.archived("badyear")
        self.login(self.head)
        response = self.post(student, reason="Səhv arxiv", admission_year="1999")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "admission_year_invalid")
        self.assertEqual(self.state(student), "archived")
        self.assertEqual(StudentAcademicRecord.objects.get(student=student).admission_year, 1950)

    def test_get_is_not_allowed(self):
        self.login(self.head)
        self.assertEqual(self.client.get(URL).status_code, 405)


class ArchiveRestoreSurfacesTest(ArchiveRestoreTestBase):
    def detail(self, user):
        return self.client.get(reverse("accounts:rim_user_detail", kwargs={"user_id": user.pk})).json()["user"]

    def test_rim_detail_offers_action_only_when_eligible(self):
        eligible = self.archived("d1")
        expelled = self.archived("d2", group="expelled")
        self.login(self.head)
        card = self.detail(eligible)
        self.assertTrue(card["actions"]["archive_restore"])
        self.assertTrue(card["archive_restore"]["needs_admission_year"])
        self.assertIn("131 T", card["archive_restore"]["note"])
        self.assertFalse(self.detail(expelled)["actions"]["archive_restore"])
        self.login(self.staff)
        self.assertFalse(self.detail(eligible)["actions"]["archive_restore"])

    def test_password_reset_lookup_points_to_the_action(self):
        student = self.archived("pwr")
        self.login(self.head)
        response = self.client.post(
            reverse("accounts:account_password_reset_lookup"), {"q": student.username}, content_type="application/json"
        )
        person = response.json()["results"][0]
        self.assertFalse(person["can_reset"])
        self.assertTrue(person["archive_restore"]["can_restore"])
        self.assertIn("Arxivdən çıxar", person["reason"])

    def test_dialog_renders_only_for_member_edit(self):
        self.login(self.head)
        page = self.client.get("/accounts/profile/?section=account-password-reset")
        self.assertContains(page, "data-archive-restore-form")
        self.assertContains(page, "accounts/js/profile/archive_restore.js")
        self.login(self.staff)
        page = self.client.get("/accounts/profile/?section=account-password-reset")
        self.assertContains(page, "data-pwr-root")
        self.assertNotContains(page, "data-archive-restore-form")


class RestoreArchivedStudentsCommandTest(ArchiveRestoreTestBase):
    def test_command_uses_the_shared_rule(self):
        student = self.archived("cmd")
        expelled = self.archived("cmdx", group="expelled")
        out = io.StringIO()
        call_command(
            "restore_archived_students",
            "--org",
            self.org.slug,
            "--actor",
            self.root.username,
            "--usernames",
            f"{student.username},{expelled.username}",
            "--admission-year",
            "2021",
            "--apply",
            stdout=out,
        )
        counts = dict(line.split(" ", 1)[1].split("=") for line in out.getvalue().splitlines())
        self.assertEqual(counts, {"restored": "1", "admission_year_fixed": "1", "skip_expelled_group": "1"})
        self.assertEqual(self.state(student), "active")
        self.assertEqual(StudentAcademicRecord.objects.get(student=student).admission_year, 2021)
