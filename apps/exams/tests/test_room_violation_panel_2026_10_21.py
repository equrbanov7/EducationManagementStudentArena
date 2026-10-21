"""Zal monitoru «Qayda pozanlar» paneli — server aqreqasiyası + kursorlu lent (2026-10-21).

Sahib: «Sağda qayda pozuntusu edən hissədə oranı optimallaşdırmaq lazımdır — say çoxaldıqca
baxmaq çətinləşə bilər.» Yoxlanır:

* snapshot sətri növ üzrə kompakt cəm (``vio_types``), ``last_event_at`` və ``max_severity``
  daşıyır; etiketlər yuxarı səviyyədə bir dəfədir (``event_labels``);
* 300 tələbə × bir neçə hadisə: snapshot sorğu sayı tələbə sayından ASILI DEYİL, sətir başına
  növ siyahısı tavanlıdır, JSON ölçüsü tələbə sayı ilə xətti məhduddur (hadisə sayı ilə yox);
* lent: cəhd başına hadisə tavanı + cəmi tavan, sabit sorğu sayı, kursorla ikinci sorğu YALNIZ
  yeni hadisələri qaytarır, tək-cəhd rejimi, skopdan kənar cəhd görünmür, icazəsiz 403.
"""

import json

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.exams.models import Exam, ExamAttempt, ExamRoom, ProctoringLog, SupervisionIncident
from apps.exams.services.final_center.violation_feed import (
    FEED_PER_ATTEMPT,
    FEED_TOTAL_CAP,
    format_cursor,
    parse_cursor,
)
from apps.exams.services.supervision.monitor_enrich import VIO_TYPES_LIMIT
from apps.exams.tests.test_final_center_flow import _FlowBase

User = get_user_model()
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

_RULES = (
    ("tab_switched", "high"),
    ("window_blurred", "medium"),
    ("fullscreen_exited", "high"),
    ("copy_attempt", "medium"),
    ("right_click_attempt", "low"),
    ("keyboard_shortcut", "medium"),
    ("text_select_attempt", "low"),
    ("paste_attempt", "medium"),
)


class _PanelBase(_FlowBase):
    def setUp(self):
        super().setUp()
        self.center_client = self._client_for(self.center)
        self.snapshot_url = reverse("exams:exam_center_room_snapshot", kwargs={"room_id": self.room.pk})
        self.feed_url = reverse("exams:exam_center_room_violation_feed", kwargs={"room_id": self.room.pk})

    def _students(self, count, prefix):
        users = User.objects.bulk_create(
            [User(username=f"{prefix}{i:03d}", first_name="Tələbə", last_name=f"{prefix}{i:03d}") for i in range(count)]
        )
        attempts = ExamAttempt.objects.bulk_create(
            [
                ExamAttempt(user=user, exam=self.exam, status="in_progress", room=self.room, attempt_number=1)
                for user in users
            ]
        )
        return users, attempts

    def _incidents(self, attempts, rules, exam=None):
        SupervisionIncident.objects.bulk_create(
            [
                SupervisionIncident(
                    organization=self.org,
                    exam=exam or self.exam,
                    attempt=attempt,
                    student_id=attempt.user_id,
                    event_type=code,
                    severity=severity,
                )
                for attempt in attempts
                for code, severity in rules
            ]
        )

    def _signals(self, attempts, kinds):
        ProctoringLog.objects.bulk_create(
            [
                ProctoringLog(exam_attempt=attempt, event_type=event_type, details={"kind": kind, "severity": sev})
                for attempt in attempts
                for kind, event_type, sev in kinds
            ]
        )

    def _get(self, url, **params):
        with CaptureQueriesContext(connection) as ctx:
            response = self.center_client.get(url, params, **AJAX)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response, len(ctx.captured_queries)

    def _row(self, payload, attempt_id):
        return next(row for row in payload["students"] if row["attempt_id"] == attempt_id)


class SnapshotAggregationTests(_PanelBase):
    def test_row_carries_per_type_counts_latest_and_labels(self):
        _users, (attempt,) = self._students(1, "agg")
        self._incidents([attempt], [("tab_switched", "high")] * 3 + [("window_blurred", "medium")])
        self._signals([attempt], [("devtools_open", "browser_console", "high")])
        ProctoringLog.objects.create(
            exam_attempt=attempt, event_type="other", details={"kind": "invigilator_note", "severity": "info"}
        )

        payload = self._get(self.snapshot_url)[0].json()
        row = self._row(payload, attempt.pk)
        self.assertEqual(row["vio_types"][0], ["tab_switched", 3, "high"])
        self.assertIn(["window_blurred", 1, "medium"], row["vio_types"])
        self.assertIn(["devtools_open", 1, "high"], row["vio_types"])
        # Nəzarətçi qeydi pozuntu növü deyil.
        self.assertNotIn("invigilator_note", [entry[0] for entry in row["vio_types"]])
        self.assertEqual(row["vio_types_more"], 0)
        self.assertEqual(row["max_severity"], "high")
        latest = SupervisionIncident.objects.filter(attempt=attempt).order_by("-timestamp").first().timestamp
        self.assertGreaterEqual(row["last_event_at"], latest.isoformat()[:19])
        labels = payload["event_labels"]
        self.assertEqual(set(labels), {"tab_switched", "window_blurred", "devtools_open"})
        self.assertTrue(all(isinstance(value, str) and value for value in labels.values()))

    def test_row_without_events_is_compact(self):
        _users, (attempt,) = self._students(1, "calm")
        row = self._row(self._get(self.snapshot_url)[0].json(), attempt.pk)
        self.assertEqual((row["vio_types"], row["vio_types_more"], row["last_event_at"]), ([], 0, None))

    def test_many_students_bounded_queries_and_payload(self):
        """300 tələbə × 8 qayda növü × 2 + 2 siqnal: sorğu sayı 20 tələbə ilə eynidir, payload tavanlıdır."""
        _u, small = self._students(20, "sm")
        self._incidents(small, _RULES * 2)
        self._signals(small, [("devtools_open", "browser_console", "high"), ("paste_input", "copy_paste", "medium")])
        self._get(self.snapshot_url)  # isinmə
        _r, queries_small = self._get(self.snapshot_url)

        _u, big = self._students(280, "bg")
        self._incidents(big, _RULES * 2)
        self._signals(big, [("devtools_open", "browser_console", "high"), ("paste_input", "copy_paste", "medium")])
        response, queries_big = self._get(self.snapshot_url)

        self.assertEqual(queries_small, queries_big)
        payload = response.json()
        rows = [row for row in payload["students"] if row["attempt_id"] in {a.pk for a in big}]
        self.assertEqual(len(rows), 280)
        for row in rows:
            self.assertLessEqual(len(row["vio_types"]), VIO_TYPES_LIMIT)
            self.assertEqual(row["vio_types_more"], 10 - VIO_TYPES_LIMIT)  # 8 qayda + 2 siqnal növü
        # 300 × 18 hadisə = 5 400 hadisə, amma JSON tələbə başına sabit ölçüdədir (hadisə yox, cəm).
        per_row = len(response.content) / len(payload["students"])
        self.assertLess(per_row, 1400, per_row)
        self.assertNotIn("events", payload)


class ViolationFeedTests(_PanelBase):
    def test_cursor_round_trip(self):
        self.assertEqual(parse_cursor(format_cursor(12, 34)), (12, 34))
        for raw in ("", "abc", "1", "1.2.3", "-1.2", "1." + "9" * 30):
            self.assertIsNone(parse_cursor(raw))

    def test_initial_feed_caps_per_attempt_and_queries_are_constant(self):
        _u, small = self._students(10, "fs")
        self._incidents(small, _RULES)
        self._signals(small, [("devtools_open", "browser_console", "high")] * 3)
        self._get(self.feed_url)
        _r, queries_small = self._get(self.feed_url)

        _u, big = self._students(290, "fb")
        self._incidents(big, _RULES)
        self._signals(big, [("devtools_open", "browser_console", "high")] * 3)
        response, queries_big = self._get(self.feed_url)
        self.assertEqual(queries_small, queries_big)

        payload = response.json()
        per_attempt = {}
        for event in payload["events"]:
            key = (event["attempt"], event["source"])
            per_attempt[key] = per_attempt.get(key, 0) + 1
        self.assertTrue(per_attempt)
        self.assertLessEqual(max(per_attempt.values()), FEED_PER_ATTEMPT)
        # Cəmi tavan: 300 × (8 + 3) = 3 300 hadisə bazada, cavabda ən çox FEED_TOTAL_CAP.
        self.assertEqual(len(payload["events"]), FEED_TOTAL_CAP)
        self.assertTrue(payload["truncated"])
        self.assertLess(len(response.content), FEED_TOTAL_CAP * 160, len(response.content))
        self.assertFalse(payload["delta"])
        self.assertEqual(set(payload["labels"]), {event["code"] for event in payload["events"]})

    def test_second_poll_with_cursor_returns_only_new_events(self):
        _u, attempts = self._students(3, "cur")
        self._incidents(attempts, [("tab_switched", "high")])
        self._signals(attempts, [("devtools_open", "browser_console", "high")])
        first = self._get(self.feed_url)[0].json()
        self.assertEqual(len(first["events"]), 6)

        again = self._get(self.feed_url, cursor=first["cursor"])[0].json()
        self.assertEqual(again["events"], [])
        self.assertTrue(again["delta"])
        self.assertEqual(again["cursor"], first["cursor"])

        fresh = SupervisionIncident.objects.create(
            organization=self.org,
            exam=self.exam,
            attempt=attempts[1],
            student_id=attempts[1].user_id,
            event_type="window_blurred",
            severity="medium",
        )
        delta = self._get(self.feed_url, cursor=first["cursor"])[0].json()
        self.assertEqual([event["id"] for event in delta["events"]], [f"r{fresh.pk}"])
        self.assertEqual(delta["events"][0]["attempt"], attempts[1].pk)
        self.assertNotEqual(delta["cursor"], first["cursor"])
        self.assertEqual(self._get(self.feed_url, cursor=delta["cursor"])[0].json()["events"], [])

    def test_single_attempt_mode_and_room_scope(self):
        _u, attempts = self._students(2, "one")
        self._incidents(attempts, [("tab_switched", "high")] * 2)
        other_room = ExamRoom.objects.create(organization=self.org, name="Zal B", code="ZB", capacity=5)
        stranger = User.objects.create(username="fcf_stranger")
        other_exam = Exam.objects.create(title="Other", author=self.center, organization=self.org, exam_type="test")
        outside = ExamAttempt.objects.create(user=stranger, exam=other_exam, status="in_progress", room=other_room)
        self._incidents([outside], [("tab_switched", "high")], exam=other_exam)

        payload = self._get(self.feed_url, attempt=attempts[0].pk)[0].json()
        self.assertEqual({event["attempt"] for event in payload["events"]}, {attempts[0].pk})
        self.assertEqual(payload["cursor"], "0.0")  # tək-cəhd sorğusu ümumi kursoru irəli çəkmir
        everything = self._get(self.feed_url)[0].json()
        self.assertNotIn(outside.pk, {event["attempt"] for event in everything["events"]})
        self.assertEqual(self._get(self.feed_url, attempt=outside.pk)[0].json()["events"], [])

    def test_feed_events_carry_no_metadata(self):
        _u, (attempt,) = self._students(1, "meta")
        SupervisionIncident.objects.create(
            organization=self.org,
            exam=self.exam,
            attempt=attempt,
            student_id=attempt.user_id,
            event_type="tab_switched",
            severity="high",
            metadata={"secret": "x" * 50},
        )
        event = self._get(self.feed_url)[0].json()["events"][0]
        self.assertEqual(set(event), {"id", "attempt", "code", "severity", "at", "source"})
        self.assertNotIn("secret", json.dumps(event))

    def test_feed_requires_room_access(self):
        response = self._client_for(self.student).get(self.feed_url, **AJAX)
        self.assertIn(response.status_code, (302, 403))
