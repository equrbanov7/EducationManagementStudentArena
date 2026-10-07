"""Müəllim rəyi 2026-10-08 — imtahan sehrbazı.

E1: tarix-saat sahəsi brauzer dilinə tabe idi (native ``datetime-local``: en-US
mm/dd/yyyy + AM/PM; «06/10» iyun 10; yazılan dəyər boş gedirdi → «Başlama
vaxtını seçin»). İndi HƏMİŞƏ ``gg.aa.iiii ss:dd`` (24 saat) + seçici; server ISO-nu
da qəbul edir; vaxt Asia/Baku-da saxlanır.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.urls import reverse
from django.utils import timezone

from apps.exams.forms import ExamForm
from apps.exams.models import Exam
from apps.exams.tests import test_w4_wizard_units as w4
from apps.exams.tests.test_w4_wizard_units import _login, _UnitFixture

BAKU = ZoneInfo("Asia/Baku")


class _Base(_UnitFixture):
    # Sinfi modul adına idxal etmirik — pytest onu burada da toplayıb təkrar işlədərdi.
    _payload = w4.WizardViewUnitTests._payload
    _post = w4.WizardViewUnitTests._post


class WizardDayFirstDateTimeTests(_Base):
    def test_typed_day_first_value_creates_exam_in_baku_time(self):
        client = _login(self.teacher, self.org)
        year = timezone.localtime().year + 1
        response = self._post(
            client,
            start_datetime=f"06.10.{year} 09:30",
            end_datetime=f"06/10/{year} 12:05",
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        exam = Exam.objects.get(title="W4U Wizard Exam")
        # «06.10» = 6 OKTYABR (iyun 10 deyil), 24 saat, Bakı vaxtı.
        self.assertEqual(
            timezone.localtime(exam.start_datetime, BAKU).replace(tzinfo=None), datetime(year, 10, 6, 9, 30)
        )
        self.assertEqual(timezone.localtime(exam.end_datetime, BAKU).replace(tzinfo=None), datetime(year, 10, 6, 12, 5))
        self.assertEqual(exam.start_datetime.astimezone(ZoneInfo("UTC")).hour, 5)

    def test_iso_is_still_accepted(self):
        client = _login(self.teacher, self.org)
        start = timezone.localtime() + timedelta(days=2)
        response = self._post(
            client,
            start_datetime=start.strftime("%Y-%m-%dT%H:%M"),
            end_datetime=(start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        exam = Exam.objects.get(title="W4U Wizard Exam")
        self.assertEqual(
            timezone.localtime(exam.start_datetime).strftime("%d.%m.%Y %H:%M"), start.strftime("%d.%m.%Y %H:%M")
        )

    def test_unreadable_value_returns_clear_message_on_timing_step(self):
        client = _login(self.teacher, self.org)
        response = self._post(client, start_datetime="10/06/2026 9:30 AM")
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["step"], 1)
        self.assertEqual(payload["field"], "start_datetime")
        self.assertIn("gg.aa.iiii ss:dd", payload["html"])
        self.assertFalse(Exam.objects.filter(title="W4U Wizard Exam").exists())

    def test_missing_time_is_explained(self):
        client = _login(self.teacher, self.org)
        response = self._post(client, end_datetime="06.10.2030")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "end_datetime")

    def test_create_form_renders_locale_free_text_inputs(self):
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:create_exam") + "?modal=1", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn("datetime-local", html)
        self.assertIn('name="start_datetime"', html)
        self.assertIn("data-ems-dt-input", html)
        self.assertIn("data-ems-dt-toggle", html)

    def test_edit_form_shows_existing_window_day_first(self):
        exam = self._exam(is_active=False)
        exam.start_datetime = datetime(2030, 10, 6, 9, 30, tzinfo=BAKU)
        exam.end_datetime = datetime(2030, 10, 6, 11, 0, tzinfo=BAKU)
        exam.save(update_fields=["start_datetime", "end_datetime"])
        form = ExamForm(instance=exam, user=self.teacher, organization=self.org)
        html = str(form["start_datetime"])
        self.assertIn('value="06.10.2030 09:30"', html)
        self.assertIn('type="text"', html)
