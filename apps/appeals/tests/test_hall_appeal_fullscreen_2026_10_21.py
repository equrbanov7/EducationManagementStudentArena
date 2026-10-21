"""2026-10-21 (sahib): «Appelyasiya zamanı da full screen açılsın».

Zal sessiyasındakı apellyasiya səhifəsi tam ekran qapısını (örtük + «Tam ekranda davam et» + xarici JS) verir; kabinetdən /
zaldan çıxdıqdan sonra açılan adi apellyasiya səhifəsi tam ekran tələb ETMİR. Səhifə imtahan nəzarəti skriptini və
incident endpoint-ini yükləmir — imtahan bitib, tam ekrandan çıxış pozuntu deyil (JS tərəfi: tests/js/hall_fullscreen.test.js).
"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse

from apps.appeals.tests.test_final_midterm_appeals_2026_10_20 import INTERNAL_IP
from apps.appeals.tests.test_hall_appeal_flow_2026_10_21 import _HallSetup
from apps.exams.tests.hall_helpers import leave_hall

FULLSCREEN_SCRIPT = "exams/js/hall_fullscreen/hall_fullscreen.js"
FULLSCREEN_CSS = "exams/css/hall/hall_fullscreen.css"
GATE_MARKERS = (
    FULLSCREEN_SCRIPT,
    FULLSCREEN_CSS,
    'data-hall-fullscreen="1"',
    "data-hall-fullscreen-overlay",
    "data-hall-fullscreen-enter",
)


class HallAppealFullscreenTests(_HallSetup):
    def assertGate(self, response):
        for marker in GATE_MARKERS:
            self.assertContains(response, marker, html=False)
        self.assertContains(response, "Tam ekranda davam et")
        self.assertTrue(response.context["hall_fullscreen"])
        self._assertNoSupervision(response)

    def assertNoGate(self, response):
        for marker in GATE_MARKERS + ("data-hall-fullscreen",):
            self.assertNotContains(response, marker, html=False)
        self.assertFalse(response.context["hall_fullscreen"])
        self._assertNoSupervision(response)

    def _assertNoSupervision(self, response):
        attempt = response.context["attempt"]
        self.assertNotContains(response, "exam_supervision", html=False)
        for name in ("supervision_log_incident", "supervision_log_signal", "supervision_heartbeat"):
            self.assertNotContains(response, reverse(f"exams:{name}", args=[attempt.id]), html=False)

    def test_hall_appeal_page_has_fullscreen_gate(self):
        attempt = self._hall_attempt()
        self._result(attempt, REMOTE_ADDR=INTERNAL_IP)
        response = self._form(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertGate(response)
        # Örtük server tərəfdə gizlidir — JS tam ekran deyilsə açır (JS yüklənməsə səhifə kilidlənmir).
        self.assertContains(response, "data-hall-fullscreen-overlay hidden", html=False)

    def test_hall_final_appeal_page_has_fullscreen_gate(self):
        attempt = self._hall_attempt("final")
        self.assertGate(self._form(attempt, REMOTE_ADDR=INTERNAL_IP))

    def test_hall_read_only_page_has_fullscreen_gate(self):
        attempt = self._hall_attempt(finished_ago=timedelta(days=30))
        response = self._form(attempt, REMOTE_ADDR=INTERNAL_IP)
        self.assertTrue(response.context["appeal_window_closed"])
        self.assertGate(response)

    def test_cabinet_appeal_page_has_no_fullscreen_gate(self):
        attempt = self._attempt("midterm")
        self.assertNoGate(self._form(attempt, {"from_section": "my-appeals"}))

    def test_cabinet_read_only_page_has_no_fullscreen_gate(self):
        attempt = self._attempt("midterm", finished_ago=timedelta(days=30))
        response = self._form(attempt, {"from_section": "my-appeals"})
        self.assertTrue(response.context["appeal_window_closed"])
        self.assertNoGate(response)

    def test_after_leaving_hall_no_fullscreen_gate(self):
        attempt = self._hall_attempt()
        leave_hall(self.client)
        self.assertNoGate(self._form(attempt, {"from_section": "my-appeals"}, REMOTE_ADDR=INTERNAL_IP))

    def test_other_attempts_hall_session_does_not_force_fullscreen(self):
        hall_attempt = self._hall_attempt()
        other = self._attempt("final")
        self.assertNotEqual(hall_attempt.id, other.id)
        self.assertNoGate(self._form(other, {"from_section": "my-appeals"}, REMOTE_ADDR=INTERNAL_IP))

    def test_failed_hall_submit_rerender_keeps_gate(self):
        attempt = self._hall_attempt()
        qid = self.question.id
        response = self.client.post(
            reverse("appeals:appeal_create", args=[attempt.id]),
            {f"appeal_q_{qid}": "1", f"comment_{qid}": "qısa"},
            REMOTE_ADDR=INTERNAL_IP,
        )
        self.assertEqual(response.status_code, 200)
        self.assertGate(response)
