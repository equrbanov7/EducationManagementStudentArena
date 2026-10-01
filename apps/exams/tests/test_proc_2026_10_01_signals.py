"""PROC 2026-10-01 — proktorinq siqnal / heartbeat endpoint-ləri, risk xalı, seçimlər.

Sahib: «test yaradarkən nəzarət sistemi … tələbənin extension qoşa bilmə
ehtimalı … hər cür cheat-ə qarşı». Brauzerdən gələn hər şey etibarsızdır:
* yalnız ağ siyahıdakı ``kind``; ciddilik SERVERDƏ (klient üstələyə bilməz);
* yalnız cəhdin sahibi, yalnız davam edən, yalnız nəzarətli cəhd;
* cəhd başına axın limiti (429) + növ başına təkrar tavanı (səssiz);
* heartbeat DB-yə yazılmır; uzun fasilədən sonra bir ``heartbeat_gap`` qeydi;
* risk xalı həddə çatanda cəhd «şübhəli» — status/bal DƏYİŞMİR.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt, ExamSupervisionConfig, ProctoringLog, SupervisionIncident
from apps.exams.services.supervision import save_supervision_config_from_form
from apps.exams.services.supervision.heartbeat import (
    HEARTBEAT_STALE_SECONDS,
)
from apps.exams.services.supervision.heartbeat import _cache as heartbeat_cache
from apps.exams.services.supervision.heartbeat import heartbeat_map, heartbeat_state, record_heartbeat
from apps.exams.services.supervision.proctoring_options import (
    DEFAULT_FLAG_THRESHOLD,
    normalize_proctoring_options,
    proctoring_options,
    save_proctoring_options_from_form,
)
from apps.exams.services.supervision.risk import attempt_timeline, attempts_risk
from apps.exams.services.supervision.signals import log_proctoring_signal
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _clear_caches():
    from core.rate_limit import _rate_limit_cache

    _rate_limit_cache().clear()
    heartbeat_cache().clear()


@override_settings(EXAM_SUPERVISION_ENABLED=True, RATELIMIT_ENABLE=True)
class _ProcBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("proc_owner", "proc_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="PROC University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.teacher = User.objects.create_user("proc_teacher", "proc_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.student = User.objects.create_user("proc_student", "proc_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.other = User.objects.create_user("proc_other", "proc_other@test.az", PASSWORD)
        _assign_user_to_org(cls.other, cls.org, ProfileRole.STUDENT, "student")
        cls.exam = Exam.objects.create(
            title="PROC Exam", author=cls.teacher, organization=cls.org, exam_type="test", is_active=True
        )
        ExamSupervisionConfig.objects.create(exam=cls.exam, enabled=True)
        cls.plain_exam = Exam.objects.create(
            title="PROC Plain", author=cls.teacher, organization=cls.org, exam_type="test", is_active=True
        )

    def setUp(self):
        _clear_caches()
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        self.client = Client()
        self.client.force_login(self.student)

    def _signal(self, payload, attempt=None, client=None):
        url = reverse("exams:supervision_log_signal", args=[(attempt or self.attempt).id])
        return (client or self.client).post(url, data=json.dumps(payload), content_type="application/json")

    def _beat(self, state=None, attempt=None):
        url = reverse("exams:supervision_heartbeat", args=[(attempt or self.attempt).id])
        return self.client.post(url, data=json.dumps({"state": state or {}}), content_type="application/json")


class SignalEndpointValidationTests(_ProcBase):
    def test_valid_signal_is_logged_with_server_side_severity(self):
        response = self._signal(
            {"kind": "ai_extension", "detail": {"token": "monica", "severity": "info", "kind": "x"}}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["logged"])
        log = ProctoringLog.objects.get(exam_attempt=self.attempt)
        self.assertEqual(log.event_type, "suspicious_activity")
        self.assertEqual(log.details["kind"], "ai_extension")
        self.assertEqual(log.details["severity"], "high")  # klientin «info»-su atıldı
        self.assertEqual(log.details["token"], "monica")
        # Evristik siqnal pozuntu sayğacına TOXUNMUR.
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.supervision_violation_count, 0)
        self.assertEqual(SupervisionIncident.objects.count(), 0)

    def test_unknown_and_server_only_kinds_are_rejected(self):
        for kind in ("definitely_not_real", "heartbeat_gap", "", 5):
            self.assertEqual(self._signal({"kind": kind}).status_code, 400)
        self.assertEqual(ProctoringLog.objects.count(), 0)

    def test_schema_is_strict(self):
        self.assertEqual(self._signal({"kind": "print_attempt", "score": 99}).status_code, 400)
        self.assertEqual(self._signal({"kind": "print_attempt", "detail": "str"}).status_code, 400)
        url = reverse("exams:supervision_log_signal", args=[self.attempt.id])
        self.assertEqual(self.client.post(url, data="[]", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(url, data="{bad", content_type="application/json").status_code, 400)
        big = json.dumps({"kind": "print_attempt", "detail": {"x": "y" * 9000}})
        self.assertEqual(self.client.post(url, data=big, content_type="application/json").status_code, 413)
        self.assertEqual(ProctoringLog.objects.count(), 0)

    def test_detail_is_flattened_and_truncated(self):
        self._signal({"kind": "bulk_insert", "detail": {"nested": {"a": [1]}, "long": "z" * 900, "n": 7}})
        details = ProctoringLog.objects.get().details
        self.assertIsInstance(details["nested"], str)
        self.assertLessEqual(len(details["long"]), 200)
        self.assertEqual(details["n"], 7)

    def test_other_students_attempt_is_404(self):
        other = Client()
        other.force_login(self.other)
        self.assertEqual(self._signal({"kind": "print_attempt"}, client=other).status_code, 404)
        self.assertEqual(ProctoringLog.objects.count(), 0)

    def test_unsupervised_exam_logs_nothing(self):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.plain_exam, status="in_progress")
        response = self._signal({"kind": "print_attempt"}, attempt=attempt)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["supervised"])
        self.assertEqual(ProctoringLog.objects.count(), 0)

    def test_finished_attempt_is_rejected(self):
        self.attempt.status = "submitted"
        self.attempt.save(update_fields=["status"])
        self.assertEqual(self._signal({"kind": "print_attempt"}).status_code, 409)
        self.assertEqual(ProctoringLog.objects.count(), 0)

    def test_get_is_not_allowed(self):
        url = reverse("exams:supervision_log_signal", args=[self.attempt.id])
        self.assertEqual(self.client.get(url).status_code, 405)


class SignalRateLimitTests(_ProcBase):
    def test_same_kind_is_capped_silently(self):
        statuses = [self._signal({"kind": "print_attempt"}).json()["logged"] for _ in range(14)]
        self.assertEqual(statuses.count(True), 10)
        self.assertEqual(ProctoringLog.objects.filter(exam_attempt=self.attempt).count(), 10)

    def test_per_attempt_flood_gets_429(self):
        kinds = ["print_attempt", "paste_input", "bulk_insert", "fast_input", "dom_injection"]
        last = 200
        for index in range(40):
            last = self._signal({"kind": kinds[index % len(kinds)]}).status_code
            if last == 429:
                break
        self.assertEqual(last, 429)
        self.assertLessEqual(ProctoringLog.objects.count(), 30)


class HeartbeatTests(_ProcBase):
    def test_heartbeat_is_cached_not_written(self):
        response = self._beat({"fs": True, "vis": True, "ext": False, "w": 1280, "evil": {"x": 1}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProctoringLog.objects.count(), 0)
        state = heartbeat_map([self.attempt.id])[self.attempt.id]
        self.assertTrue(state["fs"])
        self.assertEqual(state["w"], 1280)
        self.assertNotIn("evil", state)
        self.assertEqual(heartbeat_state(state)["status"], "ok")

    def test_gap_after_silence_is_recorded_once(self):
        record_heartbeat(self.attempt.id, {}, now=1000.0)
        result = record_heartbeat(self.attempt.id, {}, now=1000.0 + HEARTBEAT_STALE_SECONDS + 30)
        self.assertGreater(result["gap_seconds"], HEARTBEAT_STALE_SECONDS)
        # Endpoint səviyyəsində: köhnə heartbeat → növbəti POST gap siqnalı yazır.
        heartbeat_cache().set(f"procbeat:{self.attempt.id}", {"ts": 1.0}, 600)
        self.assertEqual(self._beat({}).status_code, 200)
        log = ProctoringLog.objects.get(exam_attempt=self.attempt)
        self.assertEqual(log.details["kind"], "heartbeat_gap")
        self.assertEqual(log.event_type, "network_disconnect")

    def test_heartbeat_rate_limit(self):
        codes = [self._beat({}).status_code for _ in range(14)]
        self.assertIn(429, codes)

    def test_missing_and_stale_states(self):
        from datetime import timedelta

        from django.utils import timezone

        old_start = timezone.now() - timedelta(minutes=10)
        self.assertEqual(heartbeat_state(None, started_at=old_start)["status"], "missing")
        self.assertEqual(heartbeat_state(None, started_at=timezone.now())["status"], "pending")
        self.assertEqual(heartbeat_state({"ts": 1.0}, now=1.0 + HEARTBEAT_STALE_SECONDS + 1)["status"], "stale")

    def test_unsupervised_heartbeat_is_ignored(self):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.plain_exam, status="in_progress")
        response = self._beat({}, attempt=attempt)
        self.assertFalse(response.json()["supervised"])
        self.assertEqual(heartbeat_map([attempt.id]), {})


class RiskAndThresholdTests(_ProcBase):
    def _incident(self, event_type, severity):
        SupervisionIncident.objects.create(
            organization=self.org,
            exam=self.exam,
            attempt=self.attempt,
            student=self.student,
            event_type=event_type,
            severity=severity,
        )

    def test_score_sums_rules_and_signals_and_flags_at_threshold(self):
        self._incident("tab_switched", "high")  # 3
        self._incident("copy_attempt", "medium")  # 2 (bloklanmış cəhd də xala düşür)
        self._incident("auto_locked", "critical")  # nəticə hadisəsi — sayılmır
        log_proctoring_signal(self.attempt, "ai_extension", {})  # 3
        log_proctoring_signal(self.attempt, "dom_injection", {})  # 1
        risk = attempts_risk([self.attempt.id], {self.attempt.id: 9})[self.attempt.id]
        self.assertEqual(risk["score"], 9)
        self.assertTrue(risk["flagged"])
        self.assertEqual(risk["signals"], 2)
        self.assertEqual(risk["max_severity"], "high")
        higher = attempts_risk([self.attempt.id], {self.attempt.id: 10})[self.attempt.id]
        self.assertFalse(higher["flagged"])
        # «Şübhəli» yalnız görüntüdür — cəhdin statusu/sayğacı dəyişmir.
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "in_progress")
        self.assertEqual(self.attempt.supervision_status, "active")

    def test_default_threshold_applies(self):
        risk = attempts_risk([self.attempt.id])[self.attempt.id]
        self.assertEqual(risk["threshold"], DEFAULT_FLAG_THRESHOLD)
        self.assertFalse(risk["flagged"])

    def test_timeline_merges_both_sources_newest_first(self):
        self._incident("fullscreen_exited", "high")
        log_proctoring_signal(self.attempt, "multi_monitor", {"extended": True})
        rows = attempt_timeline(self.attempt)
        self.assertEqual([row["source"] for row in rows], ["signal", "rule"])
        self.assertTrue(rows[1]["counts"])
        self.assertFalse(rows[0]["counts"])
        self.assertTrue(rows[0]["label"])


class ProctoringOptionsTests(_ProcBase):
    def test_defaults_are_safe_and_normalized(self):
        options = normalize_proctoring_options({"anti_ai": 0, "flag_threshold": "9999", "junk": 1})
        self.assertFalse(options["anti_ai"])
        self.assertTrue(options["detect_devtools"])
        self.assertEqual(options["flag_threshold"], 100)
        self.assertNotIn("junk", options)
        self.assertEqual(normalize_proctoring_options("broken")["flag_threshold"], DEFAULT_FLAG_THRESHOLD)

    def test_form_without_marker_leaves_settings_untouched(self):
        self.exam.settings = {"pass_threshold": 50}
        self.exam.save(update_fields=["settings"])
        self.assertIsNone(save_proctoring_options_from_form(self.exam, {"proctoring_flag_threshold": "3"}))
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.settings, {"pass_threshold": 50})

    def test_supervision_form_saves_advanced_options(self):
        self.exam.settings = {"pass_threshold": 50}
        self.exam.save(update_fields=["settings"])
        form = {
            "supervision_enabled": "on",
            "supervision_template": "medium",
            "proctoring_advanced_present": "1",
            "proctoring_anti_ai": "on",
            "proctoring_detect_devtools": "on",
            "proctoring_flag_threshold": "1",
        }
        save_supervision_config_from_form(self.exam, form)
        self.exam.refresh_from_db()
        options = proctoring_options(self.exam)
        self.assertTrue(options["anti_ai"])
        self.assertTrue(options["detect_devtools"])
        self.assertFalse(options["detect_multi_monitor"])
        self.assertFalse(options["detect_text_injection"])
        self.assertEqual(options["flag_threshold"], 3)  # sıxılıb (min 3)
        self.assertEqual(self.exam.settings["pass_threshold"], 50)  # digər açarlar qorunur


class TeacherSurfacesRenderTests(_ProcBase):
    def test_attempt_summary_partial_shows_risk_and_timeline_without_identity(self):
        from django.template.loader import render_to_string

        self.exam.settings = {"proctoring": {"flag_threshold": 3}}
        self.exam.save(update_fields=["settings"])
        log_proctoring_signal(self.attempt, "ai_extension", {"token": "monica"})
        html = render_to_string("exams/teacher/partials/_attempt_proctoring_summary.html", {"attempt": self.attempt})
        self.assertIn("data-proctor-summary", html)
        self.assertIn("proctor-summary--flagged", html)
        self.assertIn("proctor-tl__item--high", html)
        self.assertNotIn(self.student.username, html)  # anonim yoxlama pozulmur

    def test_attempt_summary_hidden_for_unsupervised_attempt_without_events(self):
        from django.template.loader import render_to_string

        attempt = ExamAttempt.objects.create(user=self.student, exam=self.plain_exam, status="in_progress")
        html = render_to_string("exams/teacher/partials/_attempt_proctoring_summary.html", {"attempt": attempt})
        self.assertNotIn("data-proctor-summary", html)

    def test_form_partial_defaults_for_new_exam_and_saved_values_for_edit(self):
        from types import SimpleNamespace

        from django.template.loader import render_to_string

        new_html = render_to_string(
            "exams/teacher/partials/_create_exam_supervision_advanced.html",
            {"form": SimpleNamespace(instance=Exam())},
        )
        self.assertIn('name="proctoring_advanced_present" value="1"', new_html)
        self.assertEqual(new_html.count("checked"), 4)
        self.assertIn(f'value="{DEFAULT_FLAG_THRESHOLD}"', new_html)

        self.exam.settings = {"proctoring": {"anti_ai": False, "flag_threshold": 20}}
        self.exam.save(update_fields=["settings"])
        edit_html = render_to_string(
            "exams/teacher/partials/_create_exam_supervision_advanced.html",
            {"form": SimpleNamespace(instance=self.exam)},
        )
        self.assertEqual(edit_html.count("checked"), 3)
        self.assertIn('value="20"', edit_html)
