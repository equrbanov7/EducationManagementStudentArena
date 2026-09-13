"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-01 (qalan yerlər): POST-dan
gələn qeyri-tam pk `core.http_ids.parse_int` ilə çevrilir (əvvəl `ValueError` → 500).

* `exams:exam_language_manager` `toggle_variant` (`variant_id`);
* `exams:process_question_bank` (`deleted_block_ids`);
* `accounts:superadmin_exam_rooms` (`room_id`, `computer_id`).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamRoom, ExamRoomComputer, QuestionBlock
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()
PW = "W2IdsPass123!"


class _Base(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("w2eid_teacher", "w2eid_teacher@example.com", PW)
        self.org = Organization.objects.create(
            name="W2 Ids Org",
            slug="w2-ids-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        profile = self.teacher.profile
        profile.organization = self.org
        profile.organization_type = self.org.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.create(
            user=self.teacher, organization=self.org, role=self.org.roles.get(name="teacher"), is_primary=True
        )
        self.client = Client()
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()


class LanguageVariantBadPkTest(_Base):
    def test_toggle_with_bad_variant_id_is_not_500(self):
        exam = Exam.objects.create(author=self.teacher, title="W2 Lang Exam", organization=self.org, is_active=True)
        response = self.client.post(
            reverse("exams:exam_language_manager", kwargs={"slug": exam.slug}),
            {"action": "toggle_variant", "variant_id": "abc"},
        )
        self.assertEqual(response.status_code, 302)


class QuestionBankDeletedBlocksBadPkTest(_Base):
    def test_bad_deleted_block_ids_are_skipped(self):
        exam = Exam.objects.create(
            author=self.teacher, title="W2 QB Exam", organization=self.org, exam_type="written", is_active=True
        )
        old_block = QuestionBlock.objects.create(exam=exam, name="Köhnə blok", order=1)
        response = self.client.post(
            reverse("exams:process_question_bank", args=[exam.slug]),
            {
                "deleted_block_ids": f"abc,{old_block.id}, ,7.5",
                "block_name_1": "Blok A",
                "block_content_1": "1. Birinci sual",
                "block_db_id_1": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuestionBlock.objects.filter(pk=old_block.pk).exists())
        self.assertTrue(QuestionBlock.objects.filter(exam=exam, name="Blok A").exists())


class ExamRoomsBadPkTest(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser("w2room_sa", "w2room_sa@example.com", PW)
        self.org = Organization.objects.create(
            name="W2 Rooms Org",
            slug="w2-rooms-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.superadmin,
            status="active",
            is_active=True,
        )
        self.room = ExamRoom.objects.create(organization=self.org, name="Zal 1", code="Z1")
        self.computer = ExamRoomComputer.objects.create(
            organization=self.org, room=self.room, label="PC-1", mac_address="AA:BB:CC:DD:EE:01"
        )
        self.client = Client()
        self.client.force_login(self.superadmin)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.url = reverse("accounts:superadmin_exam_rooms")

    def test_bad_room_id_is_404(self):
        response = self.client.post(self.url, {"action": "delete_room", "room_id": "abc"})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ExamRoom.objects.filter(pk=self.room.pk).exists())

    def test_bad_computer_id_is_404(self):
        response = self.client.post(
            self.url, {"action": "delete_computer", "room_id": str(self.room.pk), "computer_id": "abc"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ExamRoomComputer.objects.filter(pk=self.computer.pk).exists())

    def test_valid_computer_id_still_deletes(self):
        response = self.client.post(
            self.url, {"action": "delete_computer", "room_id": str(self.room.pk), "computer_id": str(self.computer.pk)}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamRoomComputer.objects.filter(pk=self.computer.pk).exists())
