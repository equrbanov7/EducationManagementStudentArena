"""Audit 2026-09-28 TT-1..TT-5 — cədvəl generatorunun giriş/gigiyena qapıları.

* TT-1 — pillə defoltu yalnız org-wide aktora (``test_views`` da yeniləndi);
* TT-2 — işləməni görmək: yaradan / org-wide / BÜTÜN qrupları əhatədə olan;
  dəyişmək: yalnız yaradan / org-wide;
* TT-3 — pozuq UUID 500 yox, 400;
* TT-4 — xam istisna mətni brauzerə getmir;
* TT-5 — «köhnə» növbə işləməsi də həddə sayılır + tezlik həddi.
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Membership
from apps.timetable.constants import RunStatus
from apps.timetable.models import TimetableRun
from apps.timetable.services import runs
from apps.timetable.tests.fixtures import build_world, faculty_scope
from core.rate_limit import clear_rate_limit
from core.rls import bypass_rls

FAST = {"time_limit": 5, "max_iterations": 3000, "weekdays": [1, 2, 3, 4, 5]}
RAW_ERROR = "psycopg.errors.UndefinedTable: relation secret_internal_table does not exist"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TimetableAudit20260928Test(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("ta28")
        User = get_user_model()
        org = cls.w["org"]
        with bypass_rls():
            # Fakültənin YALNIZ bir qrupunu idarə edən koordinator (ortaq qrup).
            cls.partial = User.objects.create_user("ta28_partial", "ta28_partial@x.test", "pw")
            Membership.objects.create(
                user=cls.partial,
                organization=org,
                role=org.roles.get(name="program_coordinator"),
                scope_unit=cls.w["groups"]["A-101"],
                is_primary=True,
                is_active=True,
            )
            # Eyni fakültəni tam idarə edən İKİNCİ koordinator (yaradan deyil).
            cls.peer = User.objects.create_user("ta28_peer", "ta28_peer@x.test", "pw")
            Membership.objects.create(
                user=cls.peer,
                organization=org,
                role=org.roles.get(name="program_coordinator"),
                scope_unit=cls.w["fac_a"],
                is_primary=True,
                is_active=True,
            )

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

    # ── TT-1 ────────────────────────────────────────────────────────────
    def test_unit_scoped_coordinator_cannot_change_level_policy(self):
        response = self._post(
            self.w["coordinator"], "timetable:api_policy", {"level": "bachelor", "bands": ["morning"]}
        )
        self.assertEqual(response.status_code, 403, response.content)
        page = self._client(self.w["coordinator"]).get(reverse("timetable:policies"))
        self.assertIs(page.context["can_edit_levels"], False)
        rim_page = self._client(self.w["rim"]).get(reverse("timetable:policies"))
        self.assertIs(rim_page.context["can_edit_levels"], True)

    # ── TT-2 ────────────────────────────────────────────────────────────
    def test_one_shared_group_does_not_open_someone_elses_run(self):
        run = self._done_run()
        page = self._client(self.partial).get(reverse("timetable:run_detail", args=[run.pk]))
        self.assertEqual(page.status_code, 404)
        action = self._post(self.partial, "timetable:api_run_action", {"action": "discard"}, run.pk)
        self.assertEqual(action.status_code, 404)
        listing = self._client(self.partial).get(reverse("timetable:home"))
        self.assertNotContains(listing, str(run.pk))
        with bypass_rls():
            run.refresh_from_db()
        self.assertEqual(run.status, RunStatus.DONE)

    def test_full_scope_peer_can_view_but_not_mutate(self):
        run = self._done_run()
        page = self._client(self.peer).get(reverse("timetable:run_detail", args=[run.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "data-tt-discard")
        for action in ("discard", "publish", "lock", "sync"):
            response = self._post(self.peer, "timetable:api_run_action", {"action": action, "key": "x"}, run.pk)
            self.assertEqual(response.status_code, 403, (action, response.content))
        with bypass_rls():
            run.refresh_from_db()
        self.assertEqual(run.status, RunStatus.DONE)

    def test_creator_and_org_wide_actor_can_mutate(self):
        run = self._done_run()
        response = self._post(self.w["rim"], "timetable:api_run_action", {"action": "discard"}, run.pk)
        self.assertEqual(response.status_code, 200, response.content)
        other = self._done_run()
        own = self._post(self.w["coordinator"], "timetable:api_run_action", {"action": "discard"}, other.pk)
        self.assertEqual(own.status_code, 200, own.content)

    # ── TT-3 ────────────────────────────────────────────────────────────
    def test_malformed_uuids_are_400_not_500(self):
        precheck = self._post(
            self.w["coordinator"],
            "timetable:api_precheck",
            {"scope": {"kind": "faculty", "unit_ids": ["not-a-uuid", 42]}},
        )
        self.assertEqual(precheck.status_code, 400, precheck.content)
        groups = self._post(
            self.w["coordinator"],
            "timetable:api_precheck",
            {"scope": {"kind": "groups", "group_ids": "zzz,also-bad"}},
        )
        self.assertEqual(groups.status_code, 400, groups.content)
        policy = self._post(self.w["coordinator"], "timetable:api_policy", {"group": "zzz", "bands": ["morning"]})
        self.assertEqual(policy.status_code, 400, policy.content)

    # ── TT-4 ────────────────────────────────────────────────────────────
    def test_raw_engine_error_never_reaches_the_browser(self):
        run = self._done_run()
        with bypass_rls():
            TimetableRun.objects.filter(pk=run.pk).update(status=RunStatus.FAILED, error=RAW_ERROR)
        client = self._client(self.w["coordinator"])
        status = client.get(reverse("timetable:api_run_status", args=[run.pk]))
        self.assertEqual(status.status_code, 200)
        self.assertNotIn("secret_internal_table", status.json()["error"])
        self.assertEqual(status.json()["error"], str(runs.PUBLIC_ERROR))
        page = client.get(reverse("timetable:run_detail", args=[run.pk]))
        self.assertNotContains(page, "secret_internal_table")
        listing = client.get(reverse("timetable:home"))
        self.assertNotContains(listing, "secret_internal_table")

    def test_failed_execute_keeps_the_detail_server_side(self):
        with bypass_rls():
            run = runs.create_run(
                actor=self.w["coordinator"],
                organization=self.w["org"],
                period=self.w["period"],
                scope=faculty_scope(self.w),
                params=FAST,
            )
            TimetableRun.objects.filter(pk=run.pk).update(created_by=None)
            result = runs.execute(run.pk)
        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertIn("ValueError", result.error)
        self.assertEqual(runs.status_payload(result)["error"], str(runs.PUBLIC_ERROR))

    # ── TT-5 ────────────────────────────────────────────────────────────
    def test_stale_queued_runs_still_count_toward_the_cap(self):
        old = timezone.now() - timedelta(minutes=30)
        with bypass_rls():
            for _ in range(2):
                queued = runs.create_run(
                    actor=self.w["coordinator"],
                    organization=self.w["org"],
                    period=self.w["period"],
                    scope=faculty_scope(self.w),
                    params=FAST,
                )
                TimetableRun.objects.filter(pk=queued.pk).update(status=RunStatus.QUEUED, created_at=old)
        response = self._post(
            self.w["coordinator"],
            "timetable:api_run_start",
            {"period": str(self.w["period"].pk), "scope": faculty_scope(self.w), "params": FAST},
        )
        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(response.json()["error"], "busy")

    @override_settings(TIMETABLE_RATE_LIMITS={"timetable.precheck": "1/1m"})
    def test_precheck_is_rate_limited(self):
        user = self.w["coordinator"]
        clear_rate_limit("timetable.precheck", user.pk)
        try:
            payload = {"period": str(self.w["period"].pk), "scope": faculty_scope(self.w), "params": FAST}
            first = self._post(user, "timetable:api_precheck", payload)
            self.assertEqual(first.status_code, 200, first.content)
            second = self._post(user, "timetable:api_precheck", payload)
            self.assertEqual(second.status_code, 429, second.content)
            self.assertEqual(second.json()["error"], "rate_limited")
        finally:
            clear_rate_limit("timetable.precheck", user.pk)
