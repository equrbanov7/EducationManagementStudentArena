"""Bölgü hazırlığı və offering sinxronunun sorğu büdcəsi (audit 2026-09-10 P1-7).

Audit ``_syncable_rows``-dakı ``row.groups.exists()``-i göstərirdi; ölçmə isə
Django 5.2-də onun prefetch keşini oxuduğunu təsdiqlədi (hazırlıq: 1 sətir = 5
sətir = 4 sorğu). Həqiqi N+1 ``sync_offerings`` yolunda idi:
``_instructor_for_row`` ``row.assignments.select_related(...).order_by(...)``
ilə TƏZƏ queryset qurub prefetch keşini keçirdi — sətir başına əlavə SELECT
(1 sətir: 6 → 5 sətir: 14 sorğu; təyinat cədvəli 2 → 6 dəfə oxunurdu). Bu
testlər sətir sayını 1-dən 5-ə çoxaldıb sorğu sayının sətirdən asılı
olmadığını (hazırlıq) və təyinatın BİR dəfə oxunduğunu (sinxron) qıfıllayır.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Subject
from apps.workload.constants import Activity
from apps.workload.services import assign_teacher, distribution_readiness, resolve_actor, sync_offerings
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


def _assignment_selects(ctx) -> int:
    """Təyinat cədvəlindən oxuyan SELECT-lərin sayı (prefetch → dəqiq 1 olmalıdır)."""
    return sum(
        1
        for query in ctx.captured_queries
        if query["sql"].startswith("SELECT") and "workload_teacherassignment" in query["sql"]
    )


class DistributionQueryBudgetTest(TestCase):
    def setUp(self):
        self.org = make_org("wl-qbudget")
        self.stack = make_structure(self.org, code="WLQ")
        self.head = User.objects.create_user("wlq_head", "wlq_head@x.test", "pw")
        activate_member(
            self.org,
            self.head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=self.stack["chair"],
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        self.teacher = User.objects.create_user("wlq_teacher", "wlq_teacher@x.test", "pw")
        activate_member(
            self.org,
            self.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=self.stack["chair"],
            level=50,
            scope_type=RoleScopeType.COURSE,
        )
        self.actor = resolve_actor(self.head, self.org)
        self.task = make_task(self.org, self.stack["chair"], created_by=self.head)
        self._row_no = 0

    def _add_complete_row(self):
        """Ayrı fənn + ayrı qrup — hər sətir öz açılışını yaradır; bölgü tamdır."""
        self._row_no += 1
        number = self._row_no
        subject = Subject.objects.create(organization=self.org, code=f"WLQ{number:03d}", name=f"Fənn {number}", ects=6)
        group = OrgUnit.objects.create(
            organization=self.org,
            name=f"WLQ-{number}",
            slug=f"{self.org.slug}-wlq-g{number}",
            unit_type=OrgUnitType.GROUP,
            parent=self.stack["specialty"],
        )
        row = make_row(
            self.task, {**self.stack, "subject": subject, "group": group}, lecture_total=30, seminar_total=15
        )
        assign_teacher(row=row, actor=self.actor, activity=Activity.LECTURE, teacher_id=self.teacher.pk, hours=30)
        assign_teacher(row=row, actor=self.actor, activity=Activity.SEMINAR, teacher_id=None, hours=15)
        return row

    def test_readiness_query_count_is_independent_of_row_count(self):
        self._add_complete_row()
        distribution_readiness(self.task)  # isti-tut (proses-səviyyəli keşlər saya girməsin)
        with CaptureQueriesContext(connection) as one:
            first = distribution_readiness(self.task)
        for _ in range(4):
            self._add_complete_row()
        with CaptureQueriesContext(connection) as five:
            fifth = distribution_readiness(self.task)

        self.assertEqual(first["row_count"], 1)
        self.assertEqual(fifth["row_count"], 5)
        self.assertEqual(fifth["sync_candidates"], 5)
        self.assertTrue(fifth["is_ready"])
        self.assertEqual(fifth["vacant_hours"], 5 * 15)
        self.assertEqual(
            len(one.captured_queries),
            len(five.captured_queries),
            f"1 sətir: {len(one.captured_queries)} sorğu, 5 sətir: {len(five.captured_queries)} sorğu",
        )

    def test_sync_offerings_reads_assignments_once_regardless_of_row_count(self):
        self._add_complete_row()
        sync_offerings(self.task)  # açılışlar yaradılır
        with CaptureQueriesContext(connection) as one:
            first = sync_offerings(self.task)
        for _ in range(4):
            self._add_complete_row()
        sync_offerings(self.task)
        with CaptureQueriesContext(connection) as five:
            fifth = sync_offerings(self.task)

        # İdempotent ikinci keçid: heç nə yaradılmır/yenilənmir, hamısı «skipped».
        self.assertEqual((first["created"], first["updated"], first["skipped"]), (0, 0, 1))
        self.assertEqual((fifth["created"], fifth["updated"], fifth["skipped"]), (0, 0, 5))
        self.assertEqual(len(fifth["offering_ids"]), 5)
        self.assertEqual(CourseOffering.objects.filter(organization=self.org, instructor=self.teacher).count(), 5)

        # Təyinatlar hər iki halda BİR sorğu ilə (prefetch) oxunur — sətir başına yox.
        self.assertEqual(_assignment_selects(one), 1)
        self.assertEqual(_assignment_selects(five), 1)
        # Sətir başına yalnız açılışın özünün axtarışı (CourseOffering SELECT) qalır.
        self.assertEqual(
            len(five.captured_queries) - len(one.captured_queries),
            4,
            f"1 sətir: {len(one.captured_queries)} sorğu, 5 sətir: {len(five.captured_queries)} sorğu",
        )
