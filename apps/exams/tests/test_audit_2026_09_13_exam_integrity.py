"""Audit 2026-09-13 — imtahan bütövlüyü tapıntılarının (EX-01…EX-10) reqressiya testləri.

Hər sinif auditorun reproduksiyasından çevrilib: əvvəl «faktiki davranış»
kimi keçən sınaqlar indi İSTƏNİLƏN davranışı təsdiqləyir.

* EX-01 (P0): bitməmiş cəhdin nəticə səhifəsi cavab açarını göstərirdi;
* EX-02 (P1): `/exams/code-check/` final imtahanı zal qapısından kənarda başladırdı;
* EX-03 (P1): həmin endpoint-də PIN brute-force limiti yox idi;
* EX-04 (P2): bilet yolu deaktiv imtahana / limiti dolmuş tələbəyə cəhd yaradırdı;
* EX-05 (P2): deadline-dan 2 s sonra gələn «finish» POST-u atılırdı;
* EX-06 (P2): `/exams/final/` fərdi-PIN yolu IP limiterini yan keçirdi;
* EX-07 (P2): rədd edilən fayl yükləməsi əvvəlki faylları silirdi;
* EX-08 (P2): «draft» statusu unikal məhdudiyyətdən kənarda idi;
* EX-09 (P2): autosave kilidi `exams_exam` sətrini də tuturdu;
* EX-10 (P1): bank sualı əlavə/redaktəsi yalnız oxu görünürlüyünə söykənirdi.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.domain.final_center import ROOM_SESSION_STATE_ACTIVE, TICKET_STATUS_WAITING
from apps.exams.models import (
    BankQuestion,
    Exam,
    ExamAnswer,
    ExamAnswerFile,
    ExamAttempt,
    ExamQuestion,
    ExamQuestionOption,
    ExamRoom,
    ExamRoomComputer,
    ExamRoomSession,
    ExamStudentPin,
    FinalExamTicket,
    QuestionBank,
)
from apps.exams.services.final_center import TicketStateError, begin_attempt_for_ticket
from apps.exams.services.student_pins import provision_exam_student_pins, student_visible_pin
from apps.exams.tests.test_question_submission import _Base
from apps.exams.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
PASSWORD = "StrongPass123!"
LOCMEM_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "audit-0913-exams"}}


def _make_org(owner, name):
    return Organization.objects.create(
        name=name, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )


def _make_people(prefix):
    teacher = User.objects.create_user(f"{prefix}_teacher", f"{prefix}_teacher@test.az", PASSWORD)
    student = User.objects.create_user(f"{prefix}_student", f"{prefix}_student@test.az", PASSWORD)
    org = _make_org(teacher, f"{prefix} Org")
    _assign_user_to_org(teacher, org, ProfileRole.TEACHER)
    _assign_user_to_org(student, org, ProfileRole.STUDENT)
    return org, teacher, student


def _make_quiz(org, teacher, *, n_questions=2, duration=60, **extra):
    now = timezone.now()
    exam = Exam.objects.create(
        title=extra.pop("title", "Audit Quiz"),
        author=teacher,
        organization=org,
        exam_type="test",
        exam_type_extended="quiz",
        is_active=True,
        is_public=True,
        total_duration_minutes=duration,
        random_question_count=n_questions,
        start_datetime=now - timedelta(minutes=5),
        end_datetime=now + timedelta(hours=2),
        **extra,
    )
    for index in range(n_questions):
        question = ExamQuestion.objects.create(exam=exam, order=index + 1, text=f"Sual {index + 1}")
        ExamQuestionOption.objects.create(question=question, label="A", text=f"DÜZGÜN-{index}", is_correct=True)
        ExamQuestionOption.objects.create(question=question, label="B", text=f"səhv-{index}", is_correct=False)
    return exam


def _student_client(username, org):
    client = Client()
    assert client.login(username=username, password=PASSWORD)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


@override_settings(CACHES=LOCMEM_CACHE)
class InProgressResultPageTests(TestCase):
    """EX-01."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("ex01")
        cls.exam = _make_quiz(cls.org, cls.teacher)

    def test_result_page_of_open_attempt_redirects_to_exam_without_answer_key(self):
        client = _student_client("ex01_student", self.org)
        self.assertEqual(client.get(reverse("exams:start_exam", kwargs={"slug": self.exam.slug})).status_code, 302)
        attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(client.get(take_url).status_code, 200)

        result = client.get(reverse("exams:exam_result", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id}))
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result["Location"], take_url)
        self.assertNotIn(b"correct-option", result.content)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")

    def test_result_page_closes_attempt_whose_time_is_over(self):
        client = _student_client("ex01_student", self.org)
        client.get(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        client.get(reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id}))
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=61))

        result = client.get(reverse("exams:exam_result", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id}))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        self.assertIn(result.status_code, (200, 302))


@override_settings(CACHES=LOCMEM_CACHE, FINAL_EXAM_ALLOWED_IPS=["10.10.10.0/24"])
class CodeCheckFinalGateTests(TestCase):
    """EX-02 + EX-03: test client 127.0.0.1 zal şəbəkəsindən KƏNARDADIR."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ex02_owner", "ex02_owner@test.az", PASSWORD)
        cls.org = _make_org(cls.owner, "EX02 Org")
        cls.center = User.objects.create_user("ex02_center", "ex02_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, membership_role_name="exam_center_head")
        cls.student = User.objects.create_user("ex02_student", "ex02_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT)
        now = timezone.now()
        cls.exam = Exam.objects.create(
            title="EX02 Final",
            author=cls.center,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            is_public=False,
            total_duration_minutes=60,
            random_question_count=1,
            start_datetime=now - timedelta(minutes=5),
            end_datetime=now + timedelta(hours=2),
        )
        cls.exam.allowed_users.add(cls.student)
        question = ExamQuestion.objects.create(exam=cls.exam, order=1, text="Final sualı")
        ExamQuestionOption.objects.create(question=question, label="A", text="Cavab", is_correct=True)
        room = ExamRoom.objects.create(
            organization=cls.org, name="Zal A", code="ZA", capacity=25, created_by=cls.center
        )
        ExamRoomComputer.objects.create(
            organization=cls.org,
            room=room,
            label="PC-1",
            seat_number=1,
            mac_address="AA:BB:CC:DD:EE:01",
            ip_address="10.10.10.5",
            created_by=cls.center,
        )
        provision_exam_student_pins(cls.exam)
        cls.pin = student_visible_pin(cls.exam, cls.student)

    def setUp(self):
        cache.clear()

    def test_cabinet_pin_cannot_start_final_outside_the_hall(self):
        self.assertIsNotNone(self.pin)
        client = _student_client("ex02_student", self.org)
        response = client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.exam.slug, "access_code": self.pin},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertFalse(ExamAttempt.objects.filter(exam=self.exam, user=self.student).exists())
        self.assertFalse(FinalExamTicket.objects.filter(exam=self.exam, student=self.student).exists())

    @override_settings(FINAL_EXAM_STUDENT_PIN_RATE_PER_MINUTE=5)
    def test_code_check_is_rate_limited_per_username(self):
        client = _student_client("ex02_student", self.org)
        statuses = []
        for index in range(8):
            response = client.post(
                reverse("exams:exam_code_check"),
                {"exam_slug": self.exam.slug, "access_code": f"{index:08d}"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            statuses.append(response.status_code)
        self.assertEqual(statuses[:5], [400] * 5)
        self.assertEqual(statuses[5:], [429] * 3)


class TicketStartPolicyTests(TestCase):
    """EX-04."""

    def setUp(self):
        self.owner = User.objects.create_user("ex04_owner", "ex04_owner@test.az", PASSWORD)
        self.org = _make_org(self.owner, "EX04 Org")
        self.center = User.objects.create_user("ex04_center", "ex04_center@test.az", PASSWORD)
        _assign_user_to_org(self.center, self.org, ProfileRole.MEMBER, membership_role_name="exam_center_head")
        self.student = User.objects.create_user("ex04_student", "ex04_student@test.az", PASSWORD)
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT)
        now = timezone.now()
        self.exam = Exam.objects.create(
            title="EX04 Final",
            author=self.center,
            organization=self.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
            random_question_count=1,
            max_attempts_per_user=1,
            start_datetime=now - timedelta(hours=1),
            end_datetime=now + timedelta(hours=2),
        )
        question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Final sualı", answer_mode="single")
        ExamQuestionOption.objects.create(question=question, label="A", text="Cavab", is_correct=True)
        room = ExamRoom.objects.create(
            organization=self.org, name="Zal T", code="ZT", capacity=10, created_by=self.center
        )
        self.session = ExamRoomSession.objects.create(
            organization=self.org,
            room=room,
            scheduled_start=now - timedelta(hours=2),
            scheduled_end=now + timedelta(hours=2),
            state=ROOM_SESSION_STATE_ACTIVE,
            started_at=now - timedelta(minutes=30),
            created_by=self.center,
        )
        self.ticket = FinalExamTicket.objects.create(
            organization=self.org,
            session=self.session,
            exam=self.exam,
            student=self.student,
            status=TICKET_STATUS_WAITING,
        )

    def test_ticket_starts_attempt_for_active_exam(self):
        attempt = begin_attempt_for_ticket(self.ticket)
        self.assertEqual(attempt.status, "in_progress")

    def test_ticket_refuses_deactivated_exam(self):
        Exam.objects.filter(pk=self.exam.pk).update(is_active=False)
        self.ticket.exam.refresh_from_db()
        with self.assertRaises(TicketStateError):
            begin_attempt_for_ticket(self.ticket)
        self.assertFalse(ExamAttempt.objects.filter(exam=self.exam, user=self.student).exists())

    def test_ticket_refuses_student_whose_attempt_limit_is_exhausted(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted", attempt_number=1)
        with self.assertRaises(TicketStateError):
            begin_attempt_for_ticket(self.ticket)
        self.assertEqual(ExamAttempt.objects.filter(exam=self.exam, user=self.student).count(), 1)


@override_settings(CACHES=LOCMEM_CACHE)
class DeadlineGraceTests(TestCase):
    """EX-05."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("ex05")
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=1, duration=30)
        cls.question = cls.exam.questions.get()
        cls.correct = cls.question.options.get(is_correct=True)

    def _open_attempt(self, client):
        client.get(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(client.get(take_url).status_code, 200)
        return attempt, take_url

    def _finish(self, client, take_url):
        return client.post(
            take_url,
            {
                "submit_action": "finish",
                f"q_{self.question.id}": str(self.correct.id),
                f"q_present_{self.question.id}": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_finish_shortly_after_deadline_saves_answers_and_expires(self):
        client = _student_client("ex05_student", self.org)
        attempt, take_url = self._open_attempt(client)
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=30, seconds=2))

        response = self._finish(client, take_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("finished"))
        self.assertFalse(data.get("already_finished"), data)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        answer = ExamAnswer.objects.get(attempt=attempt, question=self.question)
        self.assertEqual(list(answer.selected_options.values_list("id", flat=True)), [self.correct.id])
        self.assertEqual(attempt.correct_count, 1)

    def test_finish_after_grace_window_is_still_discarded(self):
        client = _student_client("ex05_student", self.org)
        attempt, take_url = self._open_attempt(client)
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=31))

        response = self._finish(client, take_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("already_finished"))
        answer = ExamAnswer.objects.get(attempt=attempt, question=self.question)
        self.assertEqual(list(answer.selected_options.values_list("id", flat=True)), [])


@override_settings(
    CACHES=LOCMEM_CACHE,
    FINAL_EXAM_ENTRY_RATE_PER_MINUTE=3,
    FINAL_EXAM_STUDENT_PIN_RATE_PER_MINUTE=10,
    FINAL_EXAM_ALLOWED_IPS=[],
)
class FinalEntryIpLimiterTests(TestCase):
    """EX-06."""

    PIN_RAW = "12345678"
    CLIENT_IP = "203.0.113.77"

    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user("ex06_owner", "ex06_owner@test.az", PASSWORD)
        self.org = _make_org(self.owner, "EX06 Org")
        self.center = User.objects.create_user("ex06_center", "ex06_center@test.az", PASSWORD)
        _assign_user_to_org(self.center, self.org, ProfileRole.MEMBER, membership_role_name="exam_center_head")
        self.student = User.objects.create_user("ex06_student", "ex06_student@test.az", PASSWORD)
        _assign_user_to_org(self.student, self.org, ProfileRole.STUDENT)
        now = timezone.now()
        self.exam = Exam.objects.create(
            title="EX06 Final",
            author=self.center,
            organization=self.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            is_public=False,
            total_duration_minutes=60,
            random_question_count=1,
            start_datetime=now - timedelta(minutes=5),
            end_datetime=now + timedelta(hours=2),
        )
        question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Final sualı", answer_mode="single")
        ExamQuestionOption.objects.create(question=question, label="A", text="Cavab", is_correct=True)
        self.exam.allowed_users.add(self.student)
        ExamStudentPin.objects.update_or_create(
            exam=self.exam,
            student=self.student,
            defaults={"pin_hash": make_password(self.PIN_RAW), "pin_cipher": ""},
        )

    def _pin_login(self):
        return Client().post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": self.PIN_RAW},
            REMOTE_ADDR=self.CLIENT_IP,
        )

    def test_pin_login_works_when_not_limited(self):
        self.assertEqual(self._pin_login().status_code, 302)
        self.assertTrue(ExamAttempt.objects.filter(exam=self.exam, user=self.student).exists())

    def test_tripped_ip_limiter_also_stops_student_pin_login(self):
        from apps.exams.services.final_center.entry import _rate_key

        cache.set(_rate_key("ip", self.CLIENT_IP), 1000, 60)
        response = self._pin_login()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ExamAttempt.objects.filter(exam=self.exam, user=self.student).exists())


class RejectedUploadKeepsFilesTests(TestCase):
    """EX-07."""

    def setUp(self):
        self.org, self.teacher, self.student = _make_people("ex07")
        self.exam = Exam.objects.create(
            author=self.teacher,
            organization=self.org,
            title="EX07 Written",
            exam_type="written",
            is_active=True,
            is_public=False,
            total_duration_minutes=60,
        )
        self.exam.allowed_users.add(self.student)
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Fayl yüklə", points=1)
        self.attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="in_progress", attempt_number=1
        )
        self.answer = ExamAnswer.objects.create(attempt=self.attempt, question=self.question, text_answer="ilk")
        ExamAnswerFile.objects.create(
            answer=self.answer, file=SimpleUploadedFile("keep.pdf", b"%PDF-1.4\n", content_type="application/pdf")
        )

    def test_rejected_upload_keeps_previous_answer_files(self):
        _login_with_org(self.client, self.student, self.org)
        bad = SimpleUploadedFile("evil.exe", b"MZ\x90\x00garbage", content_type="application/octet-stream")
        response = self.client.post(
            reverse("exams:take_exam", args=[self.exam.slug, self.attempt.id]),
            {"submit_action": "save_draft", f"q_{self.question.id}": "yeni", f"file_{self.question.id}[]": bad},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ExamAnswerFile.objects.filter(answer=self.answer).count(), 1)


class OpenAttemptUniqueIncludesDraftTests(TestCase):
    """EX-08."""

    def setUp(self):
        self.org, self.teacher, self.student = _make_people("ex08")
        self.exam = _make_quiz(self.org, self.teacher)

    def test_db_rejects_second_open_attempt_when_first_is_draft(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="draft", attempt_number=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress", attempt_number=2)

    def test_finished_attempt_does_not_block_a_new_one(self):
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted", attempt_number=1)
        ExamAttempt.objects.create(user=self.student, exam=self.exam, status="draft", attempt_number=2)
        self.assertEqual(self.exam.attempts.filter(user=self.student).count(), 2)


class AutosaveLockShapeTests(TestCase):
    """EX-09."""

    def setUp(self):
        self.org, self.teacher, self.student = _make_people("ex09")
        self.exam = Exam.objects.create(
            author=self.teacher,
            organization=self.org,
            title="EX09 Written",
            exam_type="written",
            is_active=True,
            is_public=False,
            total_duration_minutes=60,
        )
        self.exam.allowed_users.add(self.student)
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Yaz", points=1)
        self.attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="in_progress", attempt_number=1
        )
        ExamAnswer.objects.create(attempt=self.attempt, question=self.question)

    def test_autosave_locks_only_the_attempt_row(self):
        if connection.vendor != "postgresql":
            self.skipTest("FOR UPDATE OF yalnız PostgreSQL")
        _login_with_org(self.client, self.student, self.org)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.post(
                reverse("exams:take_exam", args=[self.exam.slug, self.attempt.id]),
                {
                    "submit_action": "autosave",
                    "changed_questions[]": [str(self.question.id)],
                    f"q_{self.question.id}": "cavab",
                    "autosave_revision": "0",
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(response.status_code, 200, response.content[:200])
        attempt_locks = [
            q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"] and '"exams_examattempt"' in q["sql"]
        ]
        self.assertTrue(attempt_locks)
        self.assertIn('FOR UPDATE OF "exams_examattempt"', attempt_locks[0])


class BankQuestionWriteOwnershipTests(_Base, TestCase):
    """EX-10."""

    def setUp(self):
        super().setUp()
        self.teacher_b = User.objects.create_user("ex10_teacher_b", "ex10_teacher_b@test.az", PASSWORD)
        _assign_user_to_org(self.teacher_b, self.org, ProfileRole.TEACHER, membership_role_name="teacher")
        self.private_bank = QuestionBank.objects.create(
            name="EX10 Private", organization=self.org, created_by=self.teacher, is_shared=False
        )
        self.shared_bank = QuestionBank.objects.create(
            name="EX10 Shared", organization=self.org, created_by=self.teacher, is_shared=True
        )
        self.q_private = BankQuestion.objects.create(bank=self.private_bank, text="ORİJİNAL-P", question_type="written")
        self.q_shared = BankQuestion.objects.create(bank=self.shared_bank, text="ORİJİNAL-S", question_type="written")

    def _edit(self, user, bank, question, text):
        url = reverse("exams:bank_question_edit", kwargs={"bank_id": bank.id, "question_id": question.id})
        return self._client_for(user).post(
            url,
            {"text": text, "correct_answer": "x", "difficulty": "medium", "language": "az", "points": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_owner_still_edits_own_question(self):
        response = self._edit(self.teacher, self.private_bank, self.q_private, "SAHİB DƏYİŞDİ")
        self.assertEqual(response.status_code, 200)
        self.q_private.refresh_from_db()
        self.assertEqual(self.q_private.text, "SAHİB DƏYİŞDİ")

    def test_exam_center_cannot_edit_foreign_private_bank_question(self):
        response = self._edit(self.exam_center, self.private_bank, self.q_private, "MƏRKƏZ DƏYİŞDİ")
        self.assertEqual(response.status_code, 403)
        self.q_private.refresh_from_db()
        self.assertEqual(self.q_private.text, "ORİJİNAL-P")

    def test_other_teacher_cannot_edit_shared_bank_question(self):
        response = self._edit(self.teacher_b, self.shared_bank, self.q_shared, "B DƏYİŞDİ")
        self.assertEqual(response.status_code, 403)
        self.q_shared.refresh_from_db()
        self.assertEqual(self.q_shared.text, "ORİJİNAL-S")

    def test_other_teacher_cannot_add_question_to_shared_bank(self):
        before = self.shared_bank.library_questions.count()
        response = self._client_for(self.teacher_b).post(
            reverse("exams:bank_question_add", kwargs={"bank_id": self.shared_bank.id}),
            {
                "q_format": "written",
                "text": "B ƏLAVƏ ETDİ",
                "correct_answer": "x",
                "difficulty": "medium",
                "language": "az",
                "points": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.shared_bank.library_questions.count(), before)
