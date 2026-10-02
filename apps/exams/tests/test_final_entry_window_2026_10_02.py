"""EXAMQA R5 (2026-10-02): final girişi modalında imtahanın ÖZ pəncərəsi (zal sessiyasının 6 saatı yox)."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings

BAKU = ZoneInfo("Asia/Baku")


@override_settings(TIME_ZONE="Asia/Baku", USE_TZ=True)
class FinalEntryWindowTests(SimpleTestCase):
    def _render(self, exam_start, exam_end):
        request = RequestFactory().get("/exams/final/")
        request.user = AnonymousUser()
        request.session = SessionStore()
        session = SimpleNamespace(
            scheduled_start=datetime(2026, 10, 5, 3, 19, tzinfo=BAKU),
            scheduled_end=datetime(2026, 10, 5, 9, 19, tzinfo=BAKU),
            invigilator=None,
        )
        context = {
            "show_gate_modal": True,
            "ticket": SimpleNamespace(
                student=SimpleNamespace(get_full_name="Test Tələbə", username="t.t"), seat_number=None
            ),
            "session": session,
            "exam": SimpleNamespace(
                title="Final", start_datetime=exam_start, end_datetime=exam_end, total_duration_minutes=60
            ),
            "room": SimpleNamespace(name="03/2", building="Korpus B"),
            "language_options": [],
        }
        return render_to_string("exams/student/final_entry.html", context, request=request)

    def test_exam_window_wins_over_hall_session(self):
        html = self._render(datetime(2026, 10, 5, 10, 0, tzinfo=BAKU), datetime(2026, 10, 5, 12, 0, tzinfo=BAKU))
        self.assertIn("10:00 – 12:00", html)
        self.assertNotIn("03:19", html)

    def test_falls_back_to_session_when_exam_has_no_window(self):
        html = self._render(None, None)
        self.assertIn("03:19 – 09:19", html)

    def test_multi_day_window_shows_date_range(self):
        html = self._render(datetime(2026, 10, 5, 9, 0, tzinfo=BAKU), datetime(2026, 10, 7, 18, 0, tzinfo=BAKU))
        self.assertIn("05.10.2026 – 07.10.2026", html)
