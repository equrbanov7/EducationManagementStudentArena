"""«Yük bölgüsü» sətir siyahısı: bölgü vəziyyəti (``status``) və fəaliyyət növü (``activity``) süzgəcləri (2026-10-25).

Müqavilə (bax ``services/row_filters.py``):
  * ``vacant`` — müəllimsiz saat var (vakant təyinat və ya bölünməmiş qalıq); ``full`` — hamısı real müəllimlərə
    bölünüb; ``partial`` — bölünmüş də, qalıq da var; ``unassigned`` — heç nə bölünməyib; ``hourly`` — saathesabı;
    ``intensive`` — intensiv kurs sətri;
  * ``activity`` ilə birlikdə vəziyyət YALNIZ həmin fəaliyyət üzrə hesablanır;
  * süzgəc səhifələmədən əvvəldir (``total`` / ``has_more`` düzgün), sorğu sayı sətir sayından asılı deyil;
  * naməlum dəyər süzgəc sayılmır (köhnə URL səhifəni boşaltmasın).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.registrar.models import Subject
from apps.workload.constants import Activity, RowKind, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from core.constants import RoleScopeType

from .factories import YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class RowStatusFiltersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("stat1025")
        cls.stack = make_structure(cls.org, code="STS")
        cls.head = User.objects.create_user("stat_head", "stat_head@x.test", "pw")
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
        cls.alice = User.objects.create_user("stat_alice", "stat_alice@x.test", "pw", first_name="Alice", last_name="A")
        cls.bob = User.objects.create_user("stat_bob", "stat_bob@x.test", "pw", first_name="Bob", last_name="B")

        def new_row(index, **kwargs):
            subject = Subject.objects.create(
                organization=cls.org, code=f"STS{index:03d}", name=f"Status fənn {index}", ects=6
            )
            return make_row(cls.task, {**cls.stack, "subject": subject}, lecture_total=30, seminar_total=15, **kwargs)

        cls.rows = [new_row(i) for i in range(6)]
        TeachingTaskRow.objects.filter(pk=cls.rows[5].pk).update(lab_total=20, total_hours=65)
        cls.intensive = make_row(cls.task, cls.stack, lecture_total=10, seminar_total=0)
        TeachingTaskRow.objects.filter(pk=cls.intensive.pk).update(row_kind=RowKind.INTENSIVE)
        cls.rows.append(cls.intensive)
        r = cls.rows
        # r0: tam (alice);  r1: mühazirə qismən (bob 10), seminar bölünməyib;  r2: heç nə;
        # r3: mühazirə VAKANT təyinat, seminar alice;  r4: tam + saathesabı;  r5: lab bölünməyib;  r6: intensiv, tam
        cls._a(r[0], cls.alice, Activity.LECTURE, 30)
        cls._a(r[0], cls.alice, Activity.SEMINAR, 15)
        cls._a(r[1], cls.bob, Activity.LECTURE, 10)
        cls._a(r[3], None, Activity.LECTURE, 30)
        cls._a(r[3], cls.alice, Activity.SEMINAR, 15)
        cls._a(r[4], cls.alice, Activity.LECTURE, 30, hourly=True)
        cls._a(r[4], cls.alice, Activity.SEMINAR, 15)
        cls._a(r[5], cls.alice, Activity.LECTURE, 30)
        cls._a(r[5], cls.alice, Activity.SEMINAR, 15)
        cls._a(r[6], cls.alice, Activity.LECTURE, 10)

    @classmethod
    def _a(cls, row, teacher, activity, hours, hourly=False):
        TeacherAssignment.objects.create(
            organization=cls.org, row=row, teacher=teacher, activity=activity, hours=hours, is_hourly_paid=hourly
        )

    def setUp(self):
        self.client.force_login(self.head)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _get(self, **params):
        response = self.client.get(
            reverse("workload:rows"), {"chair": str(self.stack["chair"].pk), "year": YEAR, "limit": 50, **params}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _idx(self, **params):
        payload = self._get(**params)
        by_id = {str(row.pk): index for index, row in enumerate(self.rows)}
        found = [by_id[row["id"]] for row in payload["rows"]]
        self.assertEqual(payload["total"], len(found), params)
        return found

    def test_status_filters(self):
        self.assertEqual(self._idx(status="vacant"), [1, 2, 3, 5])
        self.assertEqual(self._idx(status="full"), [0, 4, 6])
        self.assertEqual(self._idx(status="partial"), [1, 5])
        self.assertEqual(self._idx(status="unassigned"), [2])
        self.assertEqual(self._idx(status="hourly"), [4])
        self.assertEqual(self._idx(status="intensive"), [6])

    def test_activity_filter_alone(self):
        self.assertEqual(self._idx(activity="lab"), [5])
        self.assertEqual(self._idx(activity="seminar"), [0, 1, 2, 3, 4, 5])
        self.assertEqual(self._idx(activity="lecture"), [0, 1, 2, 3, 4, 5, 6])

    def test_status_is_evaluated_per_activity_when_given(self):
        self.assertEqual(self._idx(status="vacant", activity="seminar"), [1, 2])
        self.assertEqual(self._idx(status="vacant", activity="lecture"), [1, 2, 3])
        self.assertEqual(self._idx(status="full", activity="lecture"), [0, 4, 5, 6])
        self.assertEqual(self._idx(status="unassigned", activity="lab"), [5])
        self.assertEqual(self._idx(status="full", activity="lab"), [])
        self.assertEqual(self._idx(status="hourly", activity="seminar"), [])

    def test_combines_with_teacher_search_and_season(self):
        self.assertEqual(self._idx(status="full", teacher=str(self.alice.pk)), [0, 4, 6])
        self.assertEqual(self._idx(status="partial", teacher=str(self.bob.pk)), [1])
        self.assertEqual(self._idx(status="vacant", q="fənn 3"), [3])
        self.assertEqual(self._idx(status="vacant", season="spring"), [])
        self.assertEqual(self._idx(status="vacant", teacher="vacant"), [3])

    def test_unknown_values_are_not_filters(self):
        self.assertEqual(self._idx(status="zzz"), [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(self._idx(activity="zzz"), [0, 1, 2, 3, 4, 5, 6])
        self.assertEqual(self._idx(status="", activity="'; drop table"), [0, 1, 2, 3, 4, 5, 6])

    def test_filter_applies_before_paging(self):
        first = self._get(status="vacant", limit=3)
        second = self._get(status="vacant", limit=3, offset=first["next_offset"])
        self.assertEqual((first["total"], len(first["rows"]), first["has_more"]), (4, 3, True))
        self.assertEqual((len(second["rows"]), second["has_more"]), (1, False))
        by_id = {str(row.pk): index for index, row in enumerate(self.rows)}
        self.assertEqual([by_id[r["id"]] for r in first["rows"] + second["rows"]], [1, 2, 3, 5])

    def test_query_count_does_not_grow_with_rows(self):
        def count(**params):
            with CaptureQueriesContext(connection) as ctx:
                self._get(**params)
            return len(ctx.captured_queries)

        for params in ({"status": "vacant"}, {"status": "full", "activity": "lecture"}, {"status": "hourly"}):
            count(limit=1, **params)  # isti-tut
            self.assertEqual(count(limit=1, **params), count(limit=5, **params), params)
