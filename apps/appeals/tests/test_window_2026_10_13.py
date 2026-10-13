"""2026-10-13 (gecə) — «sonra EVDƏN 3 gün ərzində apellyasiya verilə».

* son tarix = nəticə açıldığı günün üzərinə ``APPEAL_WINDOW_DAYS`` təqvim günü, son günün SONU,
  HƏMİŞƏ Bakı vaxtı (aktiv tz-dən asılı deyil); rəqəm tənzimlənəndir;
* nəticə gizlidirsə pəncərə açılmır; gizli → görünən edildikdə pəncərə AÇILMA anından sayılır;
* müddət keçəndə server qəbul etmir, düymə/kart görünmür; son tarix tələbəyə göstərilir;
* tələbə xarici şəbəkədən (evdən) apellyasiya endpoint-lərinə çatır — şəbəkə zonası açıq olsa da
  (``EXAM_FINAL_INTERNAL_ONLY`` imtahan VERMƏ endpoint-lərinə aiddir, apellyasiyaya yox).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.appeals.constants import APPEAL_TYPE_WRONG_ANSWER_KEY
from apps.appeals.models import Appeal
from apps.appeals.services import appeal_deadline, appeal_window_start, create_appeal, is_within_appeal_window
from apps.appeals.tests.test_audit_2026_09_28_a3 import _A3Setup
from apps.exams.models import ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption
from apps.exams.services.lifecycle import set_results_hidden

BAKU = ZoneInfo("Asia/Baku")
COMMENT = "Bu sualın açarı səhvdir, B variantı da düzgündür."
EXTERNAL_ZONE = {
    "NETWORK_ZONE_ENFORCED": True,
    "INTERNAL_NETWORKS": ["10.0.0.0/8"],
    "NETWORK_ZONE_STAFF_INTERNAL_ONLY": True,
    # Başqa agentin əlavə etdiyi bayraq (imtahan VERMƏ endpoint-ləri) — apellyasiyaya təsir etməməlidir.
    "EXAM_FINAL_INTERNAL_ONLY": True,
}
HOME_IP = "203.0.113.25"


class _WindowSetup(_A3Setup):
    def setUp(self):
        super().setUp()
        self.exam = self._exam(exam_type="test", title="W Final")
        self.question = ExamQuestion.objects.create(exam=self.exam, order=1, text="Q1", points=1)
        self.option = ExamQuestionOption.objects.create(question=self.question, label="A", text="a", is_correct=True)
        ExamQuestionOption.objects.create(question=self.question, label="B", text="b", is_correct=False)

    def _attempt(self, finished_at):
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="submitted", finished_at=finished_at
        )
        ExamAnswer.objects.create(attempt=attempt, question=self.question)
        return attempt

    def _items(self):
        return [{"question_id": self.question.id, "appeal_type": APPEAL_TYPE_WRONG_ANSWER_KEY, "comment": COMMENT}]

    def _student_client(self):
        client = Client()
        client.force_login(self.student)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


class AppealDeadlineTests(_WindowSetup):
    def test_deadline_is_end_of_third_day_in_baku_regardless_of_active_timezone(self):
        # Bakı vaxtı 8 oktyabr 02:00-da bitib (UTC-də hələ 7-si 22:00) → son tarix 11 oktyabr 23:59:59 Bakı.
        finished = datetime(2026, 10, 8, 2, 0, tzinfo=BAKU)
        attempt = self._attempt(finished)
        for tz in ("UTC", "America/New_York", "Asia/Baku"):
            with self.subTest(tz=tz), timezone.override(tz):
                deadline = appeal_deadline(attempt).astimezone(BAKU)
                self.assertEqual((deadline.date().isoformat(), deadline.hour, deadline.minute), ("2026-10-11", 23, 59))
        self.assertTrue(is_within_appeal_window(attempt, at_time=datetime(2026, 10, 11, 23, 59, tzinfo=BAKU)))
        self.assertFalse(is_within_appeal_window(attempt, at_time=datetime(2026, 10, 12, 0, 0, 1, tzinfo=BAKU)))

    @override_settings(APPEAL_WINDOW_DAYS=5)
    def test_window_length_is_configurable(self):
        finished = datetime(2026, 10, 7, 12, 0, tzinfo=BAKU)
        attempt = self._attempt(finished)
        self.assertEqual(appeal_deadline(attempt).astimezone(BAKU).date().isoformat(), "2026-10-12")

    def test_server_refuses_after_deadline(self):
        attempt = self._attempt(timezone.now() - timedelta(days=5))
        with self.assertRaises(ValidationError):
            create_appeal(attempt=attempt, student=self.student, items=self._items())
        self.assertFalse(Appeal.objects.exists())

    def test_hidden_results_do_not_open_window_and_publishing_restarts_it(self):
        attempt = self._attempt(timezone.now() - timedelta(days=10))
        self.exam.results_hidden_from_students = True
        self.exam.save(update_fields=["results_hidden_from_students"])
        attempt.refresh_from_db()
        self.assertIsNone(appeal_window_start(attempt))
        self.assertFalse(is_within_appeal_window(attempt))

        set_results_hidden(self.exam, False, by_user=self.teacher)
        attempt = ExamAttempt.objects.select_related("exam").get(pk=attempt.pk)
        self.assertIsNotNone(attempt.exam.results_published_at)
        # 10 gün əvvəl bitmiş cəhd — nəticə İNDİ açıldığı üçün pəncərə indi açıqdır.
        self.assertTrue(is_within_appeal_window(attempt))
        appeal = create_appeal(attempt=attempt, student=self.student, items=self._items())
        self.assertEqual(appeal.items.count(), 1)


class AppealFromHomeTests(_WindowSetup):
    @override_settings(**EXTERNAL_ZONE)
    def test_student_can_file_from_external_network_and_sees_deadline(self):
        attempt = self._attempt(timezone.now())
        client = self._student_client()
        url = reverse("appeals:appeal_create", args=[attempt.id]) + "?from_section=my-appeals"
        page = client.get(url, REMOTE_ADDR=HOME_IP)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Apellyasiya son tarixi")
        response = client.post(
            url,
            {
                f"appeal_q_{self.question.id}": "on",
                f"appeal_type_{self.question.id}": APPEAL_TYPE_WRONG_ANSWER_KEY,
                f"comment_{self.question.id}": COMMENT,
                "from_section": "my-appeals",
            },
            REMOTE_ADDR=HOME_IP,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Appeal.objects.filter(attempt=attempt).exists())
        listing = client.get(reverse("accounts:profile") + "?section=my-appeals", REMOTE_ADDR=HOME_IP)
        self.assertEqual(listing.status_code, 200)
        appeal = Appeal.objects.get(attempt=attempt)
        detail = client.get(
            reverse("appeals:appeal_detail", args=[appeal.id]) + "?fragment=1",
            REMOTE_ADDR=HOME_IP,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(detail.status_code, 200)

    @override_settings(**EXTERNAL_ZONE)
    def test_expired_window_hides_form_from_home_too(self):
        attempt = self._attempt(timezone.now() - timedelta(days=6))
        client = self._student_client()
        url = reverse("appeals:appeal_create", args=[attempt.id]) + "?from_section=my-appeals"
        page = client.get(url, REMOTE_ADDR=HOME_IP)
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["appeal_window_closed"])
        self.assertNotContains(page, f'name="appeal_q_{self.question.id}"')
        client.post(
            url,
            {
                f"appeal_q_{self.question.id}": "on",
                f"appeal_type_{self.question.id}": APPEAL_TYPE_WRONG_ANSWER_KEY,
                f"comment_{self.question.id}": COMMENT,
            },
            REMOTE_ADDR=HOME_IP,
        )
        self.assertFalse(Appeal.objects.exists())

    def test_result_page_shows_deadline_while_open(self):
        attempt = self._attempt(timezone.now())
        client = self._student_client()
        url = reverse("exams:exam_result", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        response = client.get(url + "?from_section=my-results")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["appeal_deadline"])
        self.assertContains(response, "Apellyasiya son tarixi")
