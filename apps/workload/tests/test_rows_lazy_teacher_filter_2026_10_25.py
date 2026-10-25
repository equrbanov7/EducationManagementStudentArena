"""«Yük bölgüsü» sətir siyahısı: tənbəl yükləmə (limit/offset) + sağ paneldəki müəllimə görə süzgəc (2026-10-25).

Müqavilə:
  * ``limit`` verilməsə cavab köhnə formadadır (bütün sətirlər + hazırlıq), yalnız ``total`` / ``has_more`` əlavə;
  * ``limit`` ilə dilimlər ardıcıl və təkrarsızdır, birləşməsi tam siyahıya bərabərdir; sorğu sayı sətir sayından
    asılı deyil (N+1 yoxdur);
  * müəllim paneli yalnız ilk dilimdə gəlir (``panel=0`` onu da söndürür), hazırlıq yalnız ``readiness=1`` ilə;
  * ``teacher=<id>`` / ``teacher=vacant`` — yalnız həmin müəllimə (vakanta) bölgüsü olan sətirlər, bir sətirdə iki
    təyinat olsa da təkrar yoxdur, axtarışla birlikdə işləyir, pozuq id boş nəticə verir (500 yox).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.registrar.models import Subject
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment
from core.constants import RoleScopeType

from .factories import YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class RowsLazyAndTeacherFilterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("lazy1025")
        cls.stack = make_structure(cls.org, code="LZY")
        cls.head = User.objects.create_user("lazy_head", "lazy_head@x.test", "pw")
        activate_member(
            cls.org,
            cls.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.APPROVED, created_by=cls.head)
        cls.alice = User.objects.create_user("lazy_alice", "lazy_alice@x.test", "pw", first_name="Alice", last_name="A")
        cls.bob = User.objects.create_user("lazy_bob", "lazy_bob@x.test", "pw", first_name="Bob", last_name="B")
        cls.rows = []
        for index in range(7):
            subject = Subject.objects.create(
                organization=cls.org, code=f"LZY{index:03d}", name=f"Lazy fənn {index}", ects=6
            )
            cls.rows.append(make_row(cls.task, {**cls.stack, "subject": subject}, lecture_total=30, seminar_total=15))
        # alice: sətir 0 (mühazirə + seminar — iki təyinat), 2, 4; bob: sətir 1, 2; vakant: sətir 3
        cls._assign(cls.rows[0], cls.alice, Activity.LECTURE, 30)
        cls._assign(cls.rows[0], cls.alice, Activity.SEMINAR, 15)
        cls._assign(cls.rows[2], cls.alice, Activity.LECTURE, 30)
        cls._assign(cls.rows[4], cls.alice, Activity.LECTURE, 30)
        cls._assign(cls.rows[1], cls.bob, Activity.LECTURE, 30)
        cls._assign(cls.rows[2], cls.bob, Activity.SEMINAR, 15)
        cls._assign(cls.rows[3], None, Activity.LECTURE, 30)

    @classmethod
    def _assign(cls, row, teacher, activity, hours):
        TeacherAssignment.objects.create(organization=cls.org, row=row, teacher=teacher, activity=activity, hours=hours)

    def setUp(self):
        self.client.force_login(self.head)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _get(self, **params):
        response = self.client.get(
            reverse("workload:rows"), {"chair": str(self.stack["chair"].pk), "year": YEAR, **params}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _ids(self, payload):
        return [row["id"] for row in payload["rows"]]

    # ── köhnə forma ────────────────────────────────────────────────────────
    def test_without_limit_keeps_legacy_shape(self):
        payload = self._get()
        self.assertEqual(len(payload["rows"]), 7)
        self.assertEqual(payload["total"], 7)
        self.assertFalse(payload["has_more"])
        self.assertIsNotNone(payload["readiness"])
        self.assertTrue(payload["teachers"])

    # ── səhifələmə ─────────────────────────────────────────────────────────
    def test_pages_are_sequential_and_complete(self):
        full = self._ids(self._get())
        first = self._get(limit=3, offset=0)
        second = self._get(limit=3, offset=first["next_offset"])
        third = self._get(limit=3, offset=second["next_offset"])
        self.assertEqual((first["total"], len(first["rows"]), first["has_more"]), (7, 3, True))
        self.assertEqual((len(second["rows"]), second["has_more"]), (3, True))
        self.assertEqual((len(third["rows"]), third["has_more"], third["next_offset"]), (1, False, 7))
        self.assertEqual(self._ids(first) + self._ids(second) + self._ids(third), full)

    def test_panel_only_on_first_page_and_readiness_on_request(self):
        first = self._get(limit=3)
        self.assertTrue(first["teachers"])
        self.assertNotIn("readiness", first)
        later = self._get(limit=3, offset=3)
        self.assertNotIn("teachers", later)
        self.assertNotIn("teachers", self._get(limit=3, panel=0))
        ready = self._get(limit=0, readiness=1)
        self.assertEqual(ready["rows"], [])
        self.assertEqual(ready["readiness"]["row_count"], 7)

    def test_garbage_paging_params_do_not_fail(self):
        payload = self._get(limit="abc", offset="-5")
        self.assertEqual(len(payload["rows"]), 7)  # limit oxunmadı → defolt dilim (30)
        self.assertEqual(self._get(limit=9999, offset="x")["total"], 7)

    def test_query_count_does_not_grow_with_rows(self):
        def count(**params):
            with CaptureQueriesContext(connection) as ctx:
                self._get(**params)
            return len(ctx.captured_queries)

        count(limit=2)  # isti-tut
        small = count(limit=2)
        big = count(limit=7)
        self.assertEqual(small, big, f"2 sətir: {small}, 7 sətir: {big} sorğu")
        mine = str(self.alice.pk)
        self.assertEqual(count(limit=1, teacher=mine), count(limit=3, teacher=mine))
        self.assertEqual(count(limit=1, offset=2, panel=0), count(limit=4, offset=2, panel=0))

    def test_focus_row_extends_first_page(self):
        target = self.rows[5]
        payload = self._get(limit=2, focus=str(target.pk))
        self.assertIn(str(target.pk), self._ids(payload))
        self.assertEqual(payload["next_offset"], len(payload["rows"]))
        self.assertTrue(payload["has_more"])

    # ── müəllim süzgəci ────────────────────────────────────────────────────
    def test_teacher_filter_returns_only_that_teachers_rows_without_duplicates(self):
        payload = self._get(limit=30, teacher=str(self.alice.pk))
        self.assertEqual(self._ids(payload), [str(self.rows[i].pk) for i in (0, 2, 4)])
        self.assertEqual(payload["total"], 3)
        bob = self._get(limit=30, teacher=str(self.bob.pk))
        self.assertEqual(self._ids(bob), [str(self.rows[i].pk) for i in (1, 2)])

    def test_teacher_filter_keeps_full_row_assignments(self):
        payload = self._get(limit=30, teacher=str(self.bob.pk))
        shared = next(row for row in payload["rows"] if row["id"] == str(self.rows[2].pk))
        self.assertEqual(
            sorted(a["teacher_id"] for a in shared["assignments"]), sorted([str(self.alice.pk), str(self.bob.pk)])
        )

    def test_vacant_filter(self):
        payload = self._get(limit=30, teacher="vacant")
        self.assertEqual(self._ids(payload), [str(self.rows[3].pk)])

    def test_teacher_filter_pages(self):
        first = self._get(limit=2, teacher=str(self.alice.pk))
        second = self._get(limit=2, offset=first["next_offset"], teacher=str(self.alice.pk))
        self.assertEqual((first["total"], first["has_more"], second["has_more"]), (3, True, False))
        self.assertEqual(self._ids(first) + self._ids(second), [str(self.rows[i].pk) for i in (0, 2, 4)])

    def test_teacher_filter_combines_with_search_and_season(self):
        by_search = self._get(limit=30, teacher=str(self.alice.pk), q="fənn 2")
        self.assertEqual(self._ids(by_search), [str(self.rows[2].pk)])
        self.assertEqual(self._get(limit=30, teacher=str(self.alice.pk), season="spring")["rows"], [])

    def test_unknown_or_malformed_teacher_gives_empty_result(self):
        for bad in ("abc", "999999", "00000000-0000-0000-0000-000000000000", "1; DROP TABLE x"):
            payload = self._get(limit=30, teacher=bad)
            self.assertEqual((payload["rows"], payload["total"]), ([], 0), bad)

    def test_teacher_panel_is_not_narrowed_by_filter(self):
        payload = self._get(limit=30, teacher=str(self.alice.pk))
        names = {card["teacher_id"] for card in payload["teachers"]}
        self.assertEqual(names, {str(self.alice.pk), str(self.bob.pk), ""})
