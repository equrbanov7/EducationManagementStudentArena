"""PROC 2026-10-01 — İM monitorunda tələbə kimliyi (şəkil / ad / qrup / nömrə).

Sahib: «imtahan verən tələbənin şəkli görünə bilsin … ad, soyad, qrup şəkildə
olsun ki İM nəzarətçisi baxa bilsin». Təhlükəsizlik tələbi: şəkil yalnız icazəli
marşrutdan və yalnız nəzarətçiyə / tələbənin özünə; başqa tələbə görməməlidir.
"""

import shutil
import tempfile

from django.core.files.base import ContentFile
from django.test import Client, override_settings
from django.urls import reverse

from apps.exams.models import (
    ExamAnswer,
    ExamAttempt,
    ExamQuestion,
    ExamQuestionOption,
    ExamSupervisionConfig,
    SupervisionIncident,
)
from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting, start_room
from apps.exams.services.supervision.heartbeat import _cache as heartbeat_cache
from apps.exams.services.supervision.signals import log_proctoring_signal
from apps.exams.tests.test_final_center_flow import _FlowBase
from apps.organizations.models import OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrgUnitType
from core.rls import bypass_rls

# 1×1 PNG
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
)

_MEDIA = tempfile.mkdtemp(prefix="proc-media-")


@override_settings(EXAM_SUPERVISION_ENABLED=True, MEDIA_ROOT=_MEDIA)
class _MonitorBase(_FlowBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        ExamSupervisionConfig.objects.create(exam=cls.exam, enabled=True)
        cls.exam.settings = {"proctoring": {"flag_threshold": 3}}
        cls.exam.save(update_fields=["settings"])
        with bypass_rls():
            group = OrgUnit.objects.create(
                organization=cls.org, name="634 ing", slug="proc-634", unit_type=OrgUnitType.GROUP
            )
            program = Program.objects.create(organization=cls.org, code="PR", name="Proc", absence_limit_percent=25)
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2024)
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=program,
                curriculum=curriculum,
                group=group,
                admission_year=2024,
            )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        heartbeat_cache().clear()
        profile = self.student.profile
        profile.avatar.save("proc_face.png", ContentFile(_PNG), save=True)

    def _start_attempt(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        return begin_attempt_for_ticket(self.ticket)

    def _row(self, payload, student_id):
        return next(row for row in payload["students"] if row["student_id"] == student_id)


class MonitorIdentityTests(_MonitorBase):
    def test_room_snapshot_carries_photo_group_and_flag_for_proctor(self):
        attempt = self._start_attempt()
        SupervisionIncident.objects.create(
            organization=self.org,
            exam=self.exam,
            attempt=attempt,
            student=self.student,
            event_type="tab_switched",
            severity="high",
        )
        response = self._client_for(self.center).get(reverse("exams:exam_center_room_snapshot", args=[self.room.pk]))
        self.assertEqual(response.status_code, 200)
        row = self._row(response.json(), self.student.pk)
        self.assertEqual(row["group"], "634 ing")
        self.assertTrue(row["photo_url"].startswith(reverse("exams:proctor_student_photo", args=[self.student.pk])))
        self.assertTrue(row["initials"])
        self.assertTrue(row["supervised"])
        self.assertEqual(row["risk_score"], 3)
        self.assertTrue(row["flagged"])  # hədd 3 (imtahan seçimləri)
        self.assertEqual(row["heartbeat"]["status"], "pending")

    def test_session_snapshot_uses_same_enrichment(self):
        self._start_attempt()
        response = self._client_for(self.invigilator).get(
            reverse("exams:exam_center_session_snapshot", args=[self.session.pk])
        )
        self.assertEqual(response.status_code, 200)
        row = self._row(response.json(), self.student.pk)
        for key in ("photo_url", "initials", "group", "student_number", "risk_score", "flagged", "heartbeat"):
            self.assertIn(key, row)

    def test_heartbeat_missing_is_visible(self):
        attempt = self._start_attempt()
        heartbeat_cache().set(f"procbeat:{attempt.pk}", {"ts": 1.0}, 600)
        response = self._client_for(self.center).get(reverse("exams:exam_center_room_snapshot", args=[self.room.pk]))
        self.assertEqual(self._row(response.json(), self.student.pk)["heartbeat"]["status"], "stale")

    def test_ticket_snapshot_has_identity_risk_and_timeline(self):
        attempt = self._start_attempt()
        log_proctoring_signal(attempt, "ai_extension", {"token": "monica"})
        response = self._client_for(self.invigilator).get(
            reverse("exams:exam_center_ticket_snapshot", args=[self.session.pk, self.ticket.pk])
        )
        self.assertEqual(response.status_code, 200)
        proctor = response.json()["proctor"]
        self.assertEqual(proctor["identity"]["group"], "634 ing")
        self.assertTrue(proctor["identity"]["photo_url"])
        self.assertEqual(proctor["timeline"][0]["code"], "ai_extension")
        self.assertEqual(proctor["timeline"][0]["severity"], "high")
        self.assertEqual(proctor["risk"]["signals"], 1)

    def test_room_violations_endpoint_merges_signals(self):
        attempt = ExamAttempt.objects.create(
            user=self.student2, exam=self.exam, status="in_progress", room=self.room, room_computer=self.computer
        )
        log_proctoring_signal(attempt, "multi_monitor", {"extended": True})
        response = self._client_for(self.center).get(
            reverse("exams:exam_center_attempt_violations", args=[self.room.pk, attempt.pk])
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["proctor"]["timeline"][0]["code"], "multi_monitor")
        self.assertEqual(payload["proctor"]["identity"]["username"], self.student2.username)

    def test_students_cannot_read_monitor_data(self):
        self._start_attempt()
        student = self._client_for(self.student2)
        for url in (
            reverse("exams:exam_center_room_snapshot", args=[self.room.pk]),
            reverse("exams:exam_center_session_snapshot", args=[self.session.pk]),
            reverse("exams:exam_center_ticket_snapshot", args=[self.session.pk, self.ticket.pk]),
        ):
            self.assertIn(student.get(url).status_code, (403, 404), url)


class StudentPhotoRouteTests(_MonitorBase):
    def _photo(self, user, target=None):
        client = self._client_for(user) if user is not None else Client()
        return client.get(reverse("exams:proctor_student_photo", args=[(target or self.student).pk]))

    def test_student_sees_own_photo(self):
        response = self._photo(self.student)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("private", response["Cache-Control"])

    def test_other_student_cannot_see_photo(self):
        self._start_attempt()
        self.assertEqual(self._photo(self.student2).status_code, 404)

    def test_invigilator_sees_photo_only_while_supervising(self):
        self.assertEqual(self._photo(self.teacher).status_code, 404)  # heç nəyə nəzarət etmir
        self._start_attempt()
        self.assertEqual(self._photo(self.invigilator).status_code, 200)
        self.assertEqual(self._photo(self.teacher).status_code, 404)

    def test_exam_center_sees_org_students(self):
        self.assertEqual(self._photo(self.center).status_code, 200)

    def test_anonymous_is_redirected_and_bad_version_rejected(self):
        self.assertEqual(self._photo(None).status_code, 302)
        url = reverse("exams:proctor_student_photo", args=[self.student.pk]) + "?v=../../etc"
        self.assertEqual(self._client_for(self.student).get(url).status_code, 400)

    def test_missing_avatar_is_404(self):
        self.student.profile.avatar.delete(save=True)
        self.assertEqual(self._photo(self.student).status_code, 404)


class StudentExamHeaderTests(_MonitorBase):
    def test_take_exam_header_shows_own_identity_and_proctor_script(self):
        from datetime import timedelta

        from django.utils import timezone

        exam = self.exam.__class__.objects.create(
            title="PROC header",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=True,
            start_datetime=timezone.now() - timedelta(minutes=5),
            end_datetime=timezone.now() + timedelta(hours=1),
        )
        ExamSupervisionConfig.objects.create(exam=exam, enabled=True)
        question = ExamQuestion.objects.create(exam=exam, text="Header?", order=1)
        ExamQuestionOption.objects.create(question=question, text="Yes", is_correct=True)
        ExamQuestionOption.objects.create(question=question, text="No", is_correct=False)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
        ExamAnswer.objects.create(attempt=attempt, question=question)

        response = self._client_for(self.student).get(reverse("exams:take_exam", args=[exam.slug, attempt.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-proctor-identity")
        self.assertContains(response, "634 ing")
        self.assertContains(response, reverse("exams:proctor_student_photo", args=[self.student.pk]))
        self.assertContains(response, 'id="proctor-signals-config"')
        self.assertContains(response, "proctor_signals.js")
        self.assertContains(response, reverse("exams:supervision_heartbeat", args=[attempt.id]))
        # Başqa tələbənin məlumatı səhifədə yoxdur.
        self.assertNotContains(response, self.student2.username)
