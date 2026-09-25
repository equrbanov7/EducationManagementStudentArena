"""Səhifələr və JSON səthi — icazə (schedule.manage + əhatə), validasiya, sorğu büdcəsi."""

from __future__ import annotations

import json

from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.timetable.constants import RunStatus
from apps.timetable.models import GroupTimePolicy, TeacherAvailability, TimetableDraftSlot, TimetableRun
from apps.timetable.services import runs
from apps.timetable.tests.fixtures import build_world, faculty_scope
from core.rls import bypass_rls

FAST = {"time_limit": 5, "max_iterations": 3000, "weekdays": [1, 2, 3, 4, 5]}


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TimetableViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("vw")

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.w["org"].slug
        session.save()
        return client

    def _post(self, user, name, data, *args):
        return self._client(user).post(reverse(name, args=args), data=json.dumps(data), content_type="application/json")

    def _done_run(self):
        with bypass_rls():
            run = runs.create_run(
                actor=self.w["coordinator"],
                organization=self.w["org"],
                period=self.w["period"],
                scope=faculty_scope(self.w),
                params=FAST,
            )
            return runs.start(run)

    # ── İcazə ───────────────────────────────────────────────────────────
    def test_pages_open_for_coordinator(self):
        client = self._client(self.w["coordinator"])
        for name in ("timetable:home", "timetable:availability", "timetable:policies", "timetable:new_run"):
            response = client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_plain_teacher_and_student_are_denied(self):
        for user in (self.w["teachers"][0], self.w["students"][0]):
            client = self._client(user)
            self.assertEqual(client.get(reverse("timetable:home")).status_code, 403)
            response = self._post(user, "timetable:api_precheck", {"scope": faculty_scope(self.w)})
            self.assertEqual(response.status_code, 403)

    def test_anonymous_is_redirected_to_login(self):
        response = Client().get(reverse("timetable:home"))
        self.assertEqual(response.status_code, 302)

    # ── Əlçatanlıq ──────────────────────────────────────────────────────
    def test_availability_save_and_scope(self):
        teacher = self.w["teachers"][0]
        payload = {
            "period": str(self.w["period"].pk),
            "teacher": teacher.pk,
            "grid": {"1": "uuuuuuuu", "3": "pd"},
            "max_pairs_per_day": 4,
            "priority": 2,
            "subject_priorities": {str(self.w["subjects"]["ALQ"].pk): 4},
        }
        response = self._post(self.w["coordinator"], "timetable:api_availability", payload)
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            row = TeacherAvailability.objects.get(teacher=teacher)
        self.assertEqual(row.grid["1"], "uuuuuuuu")
        self.assertEqual(row.grid["3"], "pdnnnnnn")
        self.assertEqual(row.priority, 2)
        page = self._client(self.w["coordinator"]).get(reverse("timetable:availability"), {"teacher": teacher.pk})
        self.assertContains(page, "data-tt-cell", count=48)
        bad = self._post(self.w["coordinator"], "timetable:api_availability", {**payload, "grid": {"1": "zz"}})
        self.assertEqual(bad.status_code, 400)

    def test_availability_for_teacher_outside_scope_is_404(self):
        with bypass_rls():
            from django.contrib.auth import get_user_model

            stranger = get_user_model().objects.create_user("vw_stranger", "vw_stranger@x.test", "pw")
        response = self._post(self.w["coordinator"], "timetable:api_availability", {"teacher": stranger.pk, "grid": {}})
        self.assertEqual(response.status_code, 404)

    # ── Növbə siyasəti ──────────────────────────────────────────────────
    def test_policy_save_for_level_and_group(self):
        response = self._post(
            self.w["coordinator"], "timetable:api_policy", {"level": "master", "bands": ["afternoon", "evening"]}
        )
        self.assertEqual(response.status_code, 200, response.content)
        group = self.w["groups"]["A-101"]
        response = self._post(
            self.w["coordinator"],
            "timetable:api_policy",
            {"group": str(group.pk), "bands": ["morning"], "max_pairs_per_day": 3},
        )
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            self.assertEqual(GroupTimePolicy.objects.get(level="master").bands, ["afternoon", "evening"])
            self.assertEqual(GroupTimePolicy.objects.get(group=group).max_pairs_per_day, 3)
        outside = self._post(
            self.w["coordinator"],
            "timetable:api_policy",
            {"group": str(self.w["groups"]["B-101"].pk), "bands": ["morning"]},
        )
        self.assertEqual(outside.status_code, 404)
        empty = self._post(self.w["coordinator"], "timetable:api_policy", {"level": "bachelor", "bands": []})
        self.assertEqual(empty.status_code, 400)

    # ── Yoxlama + işləmə ────────────────────────────────────────────────
    def test_precheck_reports_summary(self):
        response = self._post(
            self.w["coordinator"],
            "timetable:api_precheck",
            {"period": str(self.w["period"].pk), "scope": faculty_scope(self.w), "params": FAST},
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertGreater(body["report"]["summary"]["events"], 0)
        self.assertTrue(body["teachers"])
        empty = self._post(self.w["coordinator"], "timetable:api_precheck", {"scope": faculty_scope(self.w, "fac_b")})
        self.assertEqual(empty.status_code, 400)

    def test_run_start_creates_done_run(self):
        response = self._post(
            self.w["coordinator"],
            "timetable:api_run_start",
            {"period": str(self.w["period"].pk), "scope": faculty_scope(self.w), "params": FAST, "seed": 3},
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        with bypass_rls():
            run = TimetableRun.objects.get(pk=body["run_id"])
        self.assertEqual(run.status, RunStatus.DONE, run.error)
        status = self._client(self.w["coordinator"]).get(reverse("timetable:api_run_status", args=[run.pk]))
        self.assertEqual(status.json()["status"], RunStatus.DONE)

    def test_run_detail_and_move_validation(self):
        run = self._done_run()
        client = self._client(self.w["coordinator"])
        page = client.get(reverse("timetable:run_detail", args=[run.pk]), {"view": "teacher"})
        self.assertEqual(page.status_code, 200)
        with bypass_rls():
            slot = TimetableDraftSlot.objects.filter(run=run, offering__group__name="M-601").first()
        # Magistr dərsi səhərə köçürülə bilməz (növbə).
        response = self._post(
            self.w["coordinator"],
            "timetable:api_run_action",
            {"action": "move", "key": slot.event_key, "weekday": slot.weekday, "pair": 1, "week_type": slot.week_type},
            run.pk,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "outside_domain")
        lock = self._post(
            self.w["coordinator"], "timetable:api_run_action", {"action": "lock", "key": slot.event_key}, run.pk
        )
        self.assertEqual(lock.status_code, 200)
        locked = self._post(
            self.w["coordinator"],
            "timetable:api_run_action",
            {"action": "move", "key": slot.event_key, "weekday": slot.weekday, "pair": 8, "week_type": slot.week_type},
            run.pk,
        )
        self.assertEqual(locked.status_code, 409)
        self.assertEqual(locked.json()["error"], "locked")

    def test_move_into_teacher_clash_is_rejected_and_same_cell_move_succeeds(self):
        run = self._done_run()
        with bypass_rls():
            rows = list(
                TimetableDraftSlot.objects.filter(
                    run=run, teacher=self.w["teachers"][1], kind="lecture", weekday__isnull=False
                ).order_by("event_key")
            )
        first, second = rows[0], next(r for r in rows if r.event_key != rows[0].event_key)
        clash = self._post(
            self.w["coordinator"],
            "timetable:api_run_action",
            {
                "action": "move",
                "key": first.event_key,
                "weekday": second.weekday,
                "pair": second.pair,
                "week_type": "all",
            },
            run.pk,
        )
        self.assertEqual(clash.status_code, 409, clash.content)
        self.assertTrue(clash.json()["conflicts"])
        same = self._post(
            self.w["coordinator"],
            "timetable:api_run_action",
            {
                "action": "move",
                "key": first.event_key,
                "weekday": first.weekday,
                "pair": first.pair,
                "week_type": "all",
            },
            run.pk,
        )
        self.assertEqual(same.status_code, 200, same.content)
        with bypass_rls():
            run.refresh_from_db()
            moved = TimetableDraftSlot.objects.filter(run=run, event_key=first.event_key).first()
        self.assertEqual(run.kpis["hard_total"], 0)
        self.assertTrue(moved.is_manual)

    def test_outsider_cannot_see_foreign_run(self):
        run = self._done_run()
        response = self._client(self.w["outsider"]).get(reverse("timetable:run_detail", args=[run.pk]))
        self.assertEqual(response.status_code, 404)
        action = self._post(self.w["outsider"], "timetable:api_run_action", {"action": "publish"}, run.pk)
        self.assertEqual(action.status_code, 404)

    # ── Sorğu büdcəsi ───────────────────────────────────────────────────
    def test_page_query_budgets(self):
        run = self._done_run()
        client = self._client(self.w["coordinator"])
        budgets = (
            (reverse("timetable:home"), {}, 40),
            (reverse("timetable:availability"), {"teacher": self.w["teachers"][0].pk}, 55),
            (reverse("timetable:policies"), {}, 45),
            (reverse("timetable:run_detail", args=[run.pk]), {}, 45),
        )
        for url, params, budget in budgets:
            with CaptureQueriesContext(connection) as ctx:
                response = client.get(url, params)
            self.assertEqual(response.status_code, 200, url)
            self.assertLessEqual(len(ctx.captured_queries), budget, (url, len(ctx.captured_queries)))

    def test_schedule_manage_section_links_to_generator(self):
        client = self._client(self.w["coordinator"])
        response = client.get(reverse("accounts:profile") + "?section=schedule-manage")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("timetable:home"))
