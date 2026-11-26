"""Yük sətrinin saatı dəyişəndə sillabusun PLAN SAATI özü yenilənir (sahib 2026-11-26).

2026-11-26 prod: ``fix_syllabus_plan_hours`` 162 versiyanı (159-u təsdiqlənmiş) düzəltdi — seminar 45 → 15 kimi
dəyişiklikdən sonra təsdiqlənmiş sillabus köhnə saatla qalırdı.  İndi açılış sinxronu
(``workload.offering_sync`` → ``registrar.refresh_offering_syllabus_plan_hours``) eyni qaydanı dərhal tətbiq edir:

* təsdiqlənmiş versiyanın YALNIZ ``plan_hours`` sütunu yenilənir — həftəlik bölgü (bölmələr) toxunulmur, audit var;
* kafedranın əl ilə düzəlişi (``plan_hours_override``) üstündür;
* arxiv versiyası və plan saatı boş olan kilidli versiya toxunulmur;
* bütöv sənəd keçidi (təsdiq/resync) və sətir keçidi (yük sətri yazılanda) eyni nəticəni verir;
* əmr (``fix_syllabus_plan_hours``) sinxrondan sonra heç nə tapmır.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.models import TeachingTaskRow
from apps.workload.services import resolve_actor
from apps.workload.services.offering_sync import sync_row_offerings, sync_task_offerings

from .factories import activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

OLD = {"lecture": 30, "seminar": 45}
NEW = {"lecture": 30, "seminar": 15}
WEEK = {"rows": [{"topic": "Giriş", "lecture": 2, "seminar": 2}]}


class SyllabusPlanHoursSyncTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("wl-sylsync")
        cls.stack = make_structure(cls.org, code="SYS")
        cls.office = User.objects.create_user("sys.office", "sys.office@x.test", "pw")
        activate_member(
            cls.org, cls.office, "teaching_office_head", permissions=["workload.view", "workload.manage"], level=85
        )
        cls.task = make_task(cls.org, cls.stack["chair"], created_by=cls.office)
        cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=45)
        sync_task_offerings(cls.task, actor=resolve_actor(cls.office, cls.org))
        cls.offering = CourseOffering.objects.get(organization=cls.org, subject=cls.stack["subject"])
        cls.syllabus = Syllabus.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            period=cls.stack["period"],
            offering=cls.offering,
            program=cls.stack["program"],
            chair_unit=cls.stack["chair"],
        )
        cls.archived = cls._version(1, "archived", OLD)
        cls.approved = cls._version(2, "approved", OLD)

    @classmethod
    def _version(cls, minor, status, hours):
        version = SyllabusVersion.objects.create(
            organization=cls.org,
            syllabus=cls.syllabus,
            major=1,
            minor=minor,
            status=status,
            approval_source="migration",
            locked_at=timezone.now(),
            plan_hours=dict(hours),
        )
        SyllabusSection.objects.create(organization=cls.org, version=version, section_id="week", data=WEEK)
        return version

    def _change_load(self, **fields):
        TeachingTaskRow.objects.filter(pk=self.row.pk).update(**fields)
        self.row.refresh_from_db()

    def _hours(self, version):
        version.refresh_from_db()
        return version.plan_hours

    def test_whole_task_sync_refreshes_the_approved_version_only(self):
        self.assertEqual(self.offering.lesson_hours, 75)
        self._change_load(seminar_plan=15, seminar_total=15, total_hours=45)
        report = sync_task_offerings(self.task, actor=resolve_actor(self.office, self.org))

        self.assertEqual(report["hours_updated"], 1)
        self.assertEqual(report["syllabus_plan_hours_updated"], 1)
        self.assertEqual(self._hours(self.approved), NEW)
        self.assertEqual(self.approved.status, "approved")
        self.assertEqual(self._hours(self.archived), OLD)  # arxiv toxunulmur
        week = SyllabusSection.objects.get(version=self.approved, section_id="week")
        self.assertEqual(week.data, WEEK)  # həftəlik bölgü dəyişmir
        audit = AuditLog.objects.get(resource_type="syllabus.version", resource_id=str(self.approved.pk))
        self.assertEqual((audit.old_values, audit.new_values), ({"plan_hours": OLD}, {"plan_hours": NEW}))
        # Təkrar keçid heç nə yazmır; əmrin quru icrası düzəldiləcək versiya tapmır.
        again = sync_task_offerings(self.task, actor=resolve_actor(self.office, self.org))
        self.assertEqual(again["syllabus_plan_hours_updated"], 0)
        out = StringIO()
        call_command("fix_syllabus_plan_hours", stdout=out)
        self.assertIn("0-i düzələcəkdi", out.getvalue())

    def test_row_sync_refreshes_even_when_the_total_is_unchanged(self):
        # Seminar 45 → 15, laboratoriya 0 → 30: cəm (75) eynidir, açılışın saatı dəyişmir — sətir keçidi yenə yeniləyir.
        self._change_load(seminar_plan=15, seminar_total=15, lab_plan=30, lab_total=30)
        report = sync_row_offerings(self.row, actor=resolve_actor(self.office, self.org), create=True)
        self.assertEqual(report["hours_updated"], 0)
        self.assertEqual(report["syllabus_plan_hours_updated"], 1)
        self.assertEqual(self._hours(self.approved), {"lecture": 30, "seminar": 15, "lab": 30})

    def test_chair_override_wins_over_the_load(self):
        override = {"lecture": 30, "seminar": 30}
        Syllabus.objects.filter(pk=self.syllabus.pk).update(plan_hours_override=override)
        self._change_load(seminar_plan=15, seminar_total=15, total_hours=45)
        sync_task_offerings(self.task, actor=resolve_actor(self.office, self.org))
        self.assertEqual(self._hours(self.approved), override)

    def test_empty_locked_version_is_not_filled(self):
        SyllabusVersion.objects.filter(pk=self.approved.pk).update(plan_hours={})
        self._change_load(seminar_plan=15, seminar_total=15, total_hours=45)
        report = sync_task_offerings(self.task, actor=resolve_actor(self.office, self.org))
        self.assertEqual(report["syllabus_plan_hours_updated"], 0)
        self.assertEqual(self._hours(self.approved), {})

    def test_no_syllabus_costs_one_query(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.registrar.public import refresh_offering_syllabus_plan_hours

        unrelated = ["00000000-0000-0000-0000-000000000000"]
        with CaptureQueriesContext(connection) as captured:
            report = refresh_offering_syllabus_plan_hours(unrelated)
        selects = [q for q in captured.captured_queries if q["sql"].lstrip().upper().startswith("SELECT")]
        self.assertEqual(len(selects), 1)
        self.assertEqual(report, {})
