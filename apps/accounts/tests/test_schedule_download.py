import datetime
from io import BytesIO
from uuid import uuid4

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from openpyxl import load_workbook

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import schedule, schedule_exports
from apps.registrar.models import ScheduleSlot
from apps.registrar.tests.journal_load_fixtures import seed_current_journal_load
from core.constants import OrgUnitType
from core.rls import bypass_rls

from .test_schedule_teacher_view_2026_10_14 import TeacherViewBase


class ScheduleDownloadTest(TeacherViewBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kompüter kafedrası", slug="test-export-cs", unit_type=OrgUnitType.CHAIR
            )
            cls.subject.chair_unit = cls.chair
            cls.subject.save(update_fields=["chair_unit"])
            cls.catalog_chair = cls.chair
            load = seed_current_journal_load(cls.offering, kinds=("lecture", "seminar"))
            cls.chair = load.task.chair
            seed_current_journal_load(cls.outside_offering, kinds=("lab",))
            cls.week = schedule.build_week_context(cls.period)
            opposite = "odd" if cls.week["parity"] == "even" else "even"
            for weekday, room, parity, parked in [
                (1, "=123", "all", False),
                (2, "201", opposite, False),
                (4, "PARK", "all", True),
            ]:
                ScheduleSlot.objects.create(
                    organization=cls.org,
                    offering=cls.offering,
                    weekday=weekday,
                    start_time=datetime.time(10, 10),
                    end_time=datetime.time(11, 40),
                    kind="lecture",
                    room=room,
                    week_type=parity,
                    is_parked=parked,
                )

    def fetch(self, user, personal=False, **params):
        name = "accounts:my_schedule_export" if personal else "accounts:schedule_manage_export"
        return self._client(user).get(reverse(name), {"period": str(self.period.pk), **params})

    def sheets(self, response):
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        return load_workbook(BytesIO(response.content))

    def test_own_week_and_recurring_plan_have_real_dates_times_parity(self):
        wb = self.sheets(self.fetch(self.teacher, personal=True))
        self.assertEqual(wb.sheetnames, ["Seçilmiş həftə", "Semestr planı"])
        dated = list(wb.worksheets[0].values)[3:]
        plan = list(wb.worksheets[1].values)[3:]
        self.assertEqual({row[-1] for row in dated}, {"'=123", "GIZLI-7"})
        self.assertEqual({row[-1] for row in plan}, {"'=123", "201", "GIZLI-7"})
        row = next(row for row in dated if row[-1] == "'=123")
        self.assertEqual(row[0].date(), self.week["monday"])
        self.assertEqual(row[2], datetime.time(10, 10))
        self.assertEqual(row[3], datetime.time(11, 40))
        self.assertIn(self.chair.name, row)
        self.assertEqual(wb.worksheets[0].freeze_panes, "B4")
        self.assertEqual(wb.worksheets[1].cell(4, 11).data_type, "s")

    def test_manager_combines_all_filters_and_cannot_export_other_faculty(self):
        resp = self.fetch(
            self.coordinator,
            faculty=str(self.faculty.pk),
            chair=str(self.chair.pk),
            group=str(self.group.pk),
            teacher=str(self.teacher.pk),
        )
        sheet = self.sheets(resp).worksheets[1]
        self.assertEqual({row[-1] for row in list(sheet.values)[3:]}, {"'=123", "201"})
        for filters in (
            {"faculty": self.other_faculty.pk},
            {"group": self.outside_group.pk},
            {"chair": uuid4()},
            {"teacher": "invalid"},
        ):
            with self.subTest(filters=filters):
                self.assertEqual(self.fetch(self.coordinator, **filters).status_code, 403)

    def test_personal_target_is_fixed_and_read_only_manager_can_export(self):
        self.assertEqual(self.fetch(self.teacher, personal=True, teacher=self.owner.pk).status_code, 403)
        self.assertEqual(self.fetch(self.student, personal=True).status_code, 403)
        self.assertEqual(self.fetch(self.coordinator, personal=True).status_code, 403)
        self.assertEqual(self.fetch(self.teacher).status_code, 403)
        self.assertEqual(self.fetch(self.viewer).status_code, 200)
        self.assertEqual(self.fetch(self.coordinator, period=uuid4()).status_code, 404)
        self.assertEqual(self.fetch(self.coordinator, period="bad").status_code, 404)

    def test_foreign_tenant_period_and_group_are_not_exported(self):
        with bypass_rls():
            foreign = Organization.objects.create(
                name="Başqa universitet", slug="foreign-export-test", owner=self.owner, org_type=self.org.org_type
            )
            period = AcademicPeriod.objects.create(
                organization=foreign,
                name="Başqa semestr",
                period_type=self.period.period_type,
                academic_year=self.period.academic_year,
                start_date=self.period.start_date,
                end_date=self.period.end_date,
            )
            group = OrgUnit.objects.create(
                organization=foreign, name=self.group.name, slug="duplicate-label", unit_type=OrgUnitType.GROUP
            )
        self.assertEqual(self.fetch(self.owner, period=period.pk).status_code, 404)
        self.assertEqual(self.fetch(self.owner, group=group.pk).status_code, 403)
        self.assertEqual(self._client(self.viewer).post(reverse("accounts:schedule_manage_export")).status_code, 405)

    def test_selected_week_and_semester_edges(self):
        next_week = self.sheets(self.fetch(self.teacher, personal=True, w=1)).worksheets[0]
        rows = list(next_week.values)[3:]
        self.assertIn("201", {r[-1] for r in rows})
        self.assertEqual(
            next(r[0].date() for r in rows if r[-1] == "201"), self.week["monday"] + datetime.timedelta(days=8)
        )
        past = self.sheets(self.fetch(self.teacher, personal=True, w=-8))
        self.assertEqual(past.worksheets[0]["A4"].value, "Seçimə uyğun dərs yoxdur.")
        self.assertGreater(past.worksheets[1].max_row, 4)

    def test_buttons_follow_view_and_hidden_selected_week(self):
        teacher = self._section(self.teacher, "my-schedule")
        self.assertContains(teacher, reverse("accounts:my_schedule_export"))
        manager = self._section(self.coordinator, sm_group=self.group.pk, w=1)
        self.assertContains(manager, reverse("accounts:schedule_manage_export"))
        self.assertContains(manager, 'name="w" value="1"')
        self.assertContains(manager, self.chair.name)

    def test_official_chair_beats_catalog_and_student_family_cannot_export(self):
        catalog = self.sheets(self.fetch(self.coordinator, chair=self.catalog_chair.pk, group=self.group.pk))
        self.assertEqual(catalog.worksheets[1]["A4"].value, "Seçimə uyğun dərs yoxdur.")
        plan = self.sheets(self.fetch(self.coordinator, chair=self.chair.pk)).worksheets[1]
        self.assertEqual({row[5] for row in list(plan.values)[3:]}, {self.chair.name})
        with bypass_rls():
            membership = Membership.objects.get(organization=self.org, user=self.student)
            membership.role = self.org.roles.get(name="alumni")
            membership.save(update_fields=["role"])
        self.assertEqual(self.fetch(self.student, personal=True).status_code, 403)

    def test_large_practical_group_has_constant_queries_and_plain_excel_text(self):
        with bypass_rls():
            self.chair.name = "Dizayn kafedrası"
            self.chair.save(update_fields=["name"])
            self.subject.chair_unit = None
            self.subject.save(update_fields=["chair_unit"])
            self.offering.seminar_is_practical = True
            self.offering.save(update_fields=["seminar_is_practical"])

            def measure():
                with CaptureQueriesContext(connection) as queries:
                    slots, labels, teacher = schedule_exports.management_slots(
                        self.owner, self.org, self.period, {"group": str(self.group.pk)}
                    )
                    content = schedule_exports.workbook_bytes(self.org, self.period, self.week, slots, labels, teacher)
                return len(queries), content

            # Unikal otaqlar bir açılışın paralel praktiki məşğələlərini fərqləndirir.
            inputs = ["#N/A", "+12", "@test", "  =2", "A\x0bB", "-12"]
            extra = [
                ScheduleSlot(
                    organization=self.org,
                    offering=self.offering,
                    weekday=1,
                    start_time=datetime.time(12),
                    end_time=datetime.time(13),
                    kind="seminar",
                    room=inputs[i] if i < len(inputs) else f"D-{i}",
                )
                for i in range(240)
            ]
            ScheduleSlot.objects.bulk_create(extra[:1])
            small_queries, _ = measure()
            ScheduleSlot.objects.bulk_create(extra[1:])
            large_queries, data = measure()
        self.assertEqual(large_queries, small_queries)
        self.assertLess(len(data), 100_000)
        workbook = load_workbook(BytesIO(data))
        plan = workbook.worksheets[1]
        self.assertEqual(plan.max_row, 3 + 2 + len(extra))
        rooms = {row[-1].value: row[-1].data_type for row in plan.iter_rows(min_row=4)}
        self.assertTrue(all(rooms[text] == "s" for text in ("#N/A", "'+12", "'@test", "'  =2", "AB", "'-12")))
        self.assertTrue(all(c.data_type != "f" for sheet in workbook for row in sheet for c in row))
