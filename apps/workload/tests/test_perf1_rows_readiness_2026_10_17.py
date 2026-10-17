"""PERF-1 F-09 (2026-10-17): `ders-yuku/setirler/` hazırlıq xülasəsini sətirlərin İKİNCİ oxusu olmadan qurur.

Əvvəl `rows` endpoint-i sətirləri + qrupları + balansı `serialize_rows`-da oxuyub, `distribution_readiness`-də
eynisini yenidən oxuyurdu; natamam sətrin `subject_label`-i isə hər sətir üçün ayrıca fənn SELECT-i açırdı.
Testlər: (1) süzgəcsiz cavabın sorğu sayı sətir sayından asılı deyil; (2) hazırlıq bloku köhnə (tam yenidən
oxuyan) yol ilə EYNİDİR; (3) süzgəc (mövsüm) varsa hazırlıq yenə bütün tapşırıq üzrədir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.registrar.models import Subject
from apps.workload.constants import TaskStatus
from apps.workload.services import distribution_readiness
from core.constants import RoleScopeType

from .factories import YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class RowsEndpointReadinessTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("pf1-f09")
        cls.stack = make_structure(cls.org, code="PFN")
        cls.head = User.objects.create_user("pf1f09_head", "pf1f09_head@x.test", "pw")
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

    def setUp(self):
        self.client.force_login(self.head)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        self._n = 0

    def _add_incomplete_row(self):
        """Ayrı fənnli, bölünməmiş (natamam) sətir — `incomplete_rows`-a fənn adı ilə düşür."""
        self._n += 1
        subject = Subject.objects.create(
            organization=self.org, code=f"PFN{self._n:03d}", name=f"Fənn {self._n}", ects=6
        )
        return make_row(self.task, {**self.stack, "subject": subject}, lecture_total=30, seminar_total=15)

    def _get(self, **params):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                reverse("workload:rows"), {"chair": str(self.stack["chair"].pk), "year": YEAR, **params}
            )
        self.assertEqual(response.status_code, 200)
        return response.json(), len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_rows(self):
        self._add_incomplete_row()
        self._get()  # isti-tut
        one, one_count = self._get()
        for _ in range(4):
            self._add_incomplete_row()
        five, five_count = self._get()

        self.assertEqual(one["readiness"]["row_count"], 1)
        self.assertEqual(five["readiness"]["row_count"], 5)
        self.assertEqual(len(five["readiness"]["incomplete_rows"]), 5)
        self.assertEqual(one_count, five_count, f"1 sətir: {one_count}, 5 sətir: {five_count} sorğu")

    def test_readiness_matches_full_reload(self):
        for _ in range(3):
            self._add_incomplete_row()
        payload, _count = self._get()
        self.assertEqual(payload["readiness"], distribution_readiness(self.task))
        self.assertEqual(
            [row["subject"] for row in payload["readiness"]["incomplete_rows"]], ["Fənn 1", "Fənn 2", "Fənn 3"]
        )

    def test_season_filter_keeps_task_wide_readiness(self):
        for _ in range(2):
            self._add_incomplete_row()
        payload, _count = self._get(season="spring")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["readiness"]["row_count"], 2)

    def test_readiness_reload_reads_subjects_in_one_query(self):
        for _ in range(4):
            self._add_incomplete_row()
        with CaptureQueriesContext(connection) as ctx:
            distribution_readiness(self.task)
        subject_selects = [q for q in ctx.captured_queries if 'FROM "registrar_subject"' in q["sql"]]
        self.assertEqual(subject_selects, [], "fənn adı sətir sorğusunda JOIN ilə gəlməlidir")
