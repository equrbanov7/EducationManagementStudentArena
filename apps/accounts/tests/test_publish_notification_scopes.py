"""«Bildiriş göndər» — struktur/şöbə əhatələri və əlavə fayllar (2026-09-08).

* hədəf siyahısı: org-wide aktor (Tədris şöbəsi) fakültə/kafedra/qrup və şöbə
  hədəflərini görür; dekan yalnız öz alt-ağacını, şöbə hədəfsiz; adi müəllim
  struktur hədəfi görmür;
* alıcı həlli: `unit_<fakültə>` → kafedra müəllimi + dekan + qrup tələbəsi;
  `role_exam_center_<org>` → imtahan mərkəzi heyəti; icazəsiz aktor → None;
* əlavə fayl: PDF metadata-ya `attachments` kimi düşür, icra faylı rədd edilir.
"""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, override_settings

from apps.accounts.services.profile_actions import (
    PUBLISH_NOTIFICATION_FILE_INVALID,
    PUBLISH_NOTIFICATION_SENT,
    publish_system_notification,
    resolve_notification_recipients,
)
from apps.accounts.views.profile.context_builder._helpers import _get_publish_notification_targets
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership, OrgUnit, Role
from apps.registrar.models import StudentAcademicRecord
from core.constants import OrgUnitType, RoleScopeType

from .test_teaching_office_stage2 import Stage2BaseTest

CAPS = {"is_superadmin": False, "is_org_admin": False, "is_teacher": False}


class _ScopesBase(Stage2BaseTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other_faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Hüquq fakültəsi", slug="pn-huquq", code="HF"
        )
        # Müəllim üzvlüyü kafedraya bağlanır; tələbənin qrupda aktiv qeydi olur.
        Membership.objects.filter(organization=cls.org, user=cls.users["teacher"], role=cls.roles["teacher"]).update(
            scope_unit=cls.chair
        )
        cls.exam_role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="exam_center_head",
            defaults={
                "display_name": "Exam Center Head",
                "level": 70,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": ["exam.view"],
                "is_system": True,
                "is_active": True,
            },
        )
        cls.exam_membership = Membership.objects.create(
            user=cls.users["student"] if False else cls.users["chair_head"],
            organization=cls.org,
            role=cls.exam_role,
            is_active=True,
        )

    def setUp(self):
        super().setUp()
        self.plan = self._plan()
        self.record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.users["student"],
            program=self.program,
            curriculum=self.plan,
            group=self.group,
            admission_year=2024,
        )

    def _targets(self, role):
        return _get_publish_notification_targets(self.users[role], CAPS, organization=self.org)


class TargetListTest(_ScopesBase):
    def test_org_wide_actor_sees_units_and_departments(self):
        targets = self._targets("teaching_office_head")
        values = {t["value"] for t in targets}
        self.assertIn(f"unit_{self.faculty.id}", values)
        self.assertIn(f"unit_{self.chair.id}", values)
        self.assertIn(f"unit_{self.group.id}", values)
        self.assertIn(f"role_exam_center_{self.org.id}", values)
        self.assertIn(f"role_teaching_office_{self.org.id}", values)
        categories = [t["category"] for t in targets]
        self.assertEqual(
            categories, sorted(categories, key=["org", "roles", "faculty", "chair", "group", "exam_group"].index)
        )
        self.assertTrue(all(t.get("category_label") for t in targets))

    def test_dean_sees_only_own_subtree_without_departments(self):
        values = {t["value"] for t in self._targets("dean")}
        self.assertIn(f"unit_{self.faculty.id}", values)
        self.assertIn(f"unit_{self.chair.id}", values)
        self.assertNotIn(f"unit_{self.other_faculty.id}", values)
        self.assertFalse(any(v.startswith("role_") for v in values))

    def test_plain_teacher_sees_no_structure_targets(self):
        values = {t["value"] for t in self._targets("teacher")}
        self.assertFalse(any(v.startswith("unit_") or v.startswith("role_") for v in values))


class RecipientResolutionTest(_ScopesBase):
    def test_faculty_target_reaches_teachers_head_and_students(self):
        recipients = resolve_notification_recipients(
            self.users["teaching_office_head"], CAPS, f"unit_{self.faculty.id}"
        )
        self.assertIsNotNone(recipients)
        ids = set(recipients.values_list("pk", flat=True))
        self.assertIn(self.users["teacher"].pk, ids)  # kafedra müəllimi (alt-ağac)
        self.assertIn(self.users["dean"].pk, ids)  # fakültəyə əhatəli üzvlük
        self.assertIn(self.users["student"].pk, ids)  # qrupda aktiv qeyd
        self.assertNotIn(self.users["teaching_office_head"].pk, ids)

    def test_group_target_reaches_only_group_students(self):
        recipients = resolve_notification_recipients(self.users["dean"], CAPS, f"unit_{self.group.id}")
        self.assertEqual(set(recipients.values_list("pk", flat=True)), {self.users["student"].pk})

    def test_role_target_reaches_department_staff(self):
        recipients = resolve_notification_recipients(
            self.users["teaching_office_head"], CAPS, f"role_exam_center_{self.org.id}"
        )
        self.assertEqual(set(recipients.values_list("pk", flat=True)), {self.users["chair_head"].pk})

    def test_unauthorised_actors_get_none(self):
        self.assertIsNone(resolve_notification_recipients(self.users["teacher"], CAPS, f"unit_{self.faculty.id}"))
        self.assertIsNone(resolve_notification_recipients(self.users["dean"], CAPS, f"unit_{self.other_faculty.id}"))
        self.assertIsNone(resolve_notification_recipients(self.users["dean"], CAPS, f"role_exam_center_{self.org.id}"))
        self.assertIsNone(resolve_notification_recipients(self.users["teaching_office_head"], CAPS, "unit_not-a-uuid"))
        self.assertIsNone(
            resolve_notification_recipients(self.users["teaching_office_head"], CAPS, f"role_nope_{self.org.id}")
        )


class AttachmentTest(_ScopesBase):
    def setUp(self):
        super().setUp()
        self.media_root = tempfile.mkdtemp(prefix="pn-media-")
        self.addCleanup(shutil.rmtree, self.media_root, True)

    def _publish(self, files):
        request = RequestFactory().post(
            "/accounts/profile/",
            {
                "profile_form": "publish-notification",
                "notif_title": "Sərəncam",
                "notif_message": "Əlavədə sənəd var",
                "notif_targets": [f"unit_{self.chair.id}"],
                "notif_files": files,
            },
        )
        request.user = self.users["teaching_office_head"]
        with override_settings(MEDIA_ROOT=self.media_root):
            return publish_system_notification(request=request, capabilities=CAPS)

    def test_pdf_attachment_is_stored_in_metadata(self):
        ok, key = self._publish(
            [SimpleUploadedFile("serencam.pdf", b"%PDF-1.4\n%test\n", content_type="application/pdf")]
        )
        self.assertTrue(ok, key)
        self.assertEqual(key, PUBLISH_NOTIFICATION_SENT)
        notification = InAppNotification.objects.get(recipient=self.users["teacher"], title="Sərəncam")
        attachments = notification.metadata.get("attachments")
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["name"], "serencam.pdf")
        self.assertTrue(attachments[0]["url"].endswith(".pdf"))
        self.assertGreater(attachments[0]["size"], 0)

    def test_executable_attachment_is_rejected(self):
        ok, key = self._publish(
            [SimpleUploadedFile("virus.exe", b"MZ\x90\x00", content_type="application/octet-stream")]
        )
        self.assertFalse(ok)
        self.assertEqual(key, PUBLISH_NOTIFICATION_FILE_INVALID)
        self.assertFalse(InAppNotification.objects.filter(title="Sərəncam").exists())
