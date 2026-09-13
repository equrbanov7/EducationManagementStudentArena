"""Perf auditi 2026-09-13 — `accounts` səthlərindəki tapıntıların reqressiya testləri.

* **F-01** `organizations:group_students` hər tələbə üçün `orgunit` SELECT-i
  atırdı (`record.group` `select_related`-də yox idi) → sorğu sayı tələbə
  sayından asılı olmamalıdır.
* **F-03** `registrar:group_individual_plan` (.docx) hər tələbə üçün dövr +
  kurikulum sətri sorğusu atırdı → eyni qrupda tələbə sayı artanda sorğu sayı
  dəyişməməlidir, sənəd məzmunu isə eyni qalmalıdır.
* **F-12** «Sillabuslar» bölməsi bütün dəsti Python-a yükləyib HAMISI üçün
  sətir qururdu → sorğu sayı sillabus sayından asılı olmamalıdır; səhifələmə,
  KPI-lar, süzgəclər (semestr / kafedra / SLA) və «sillabussuz» sətirlər
  əvvəlki kimi işləməlidir.
"""

from __future__ import annotations

import io
import zipfile

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.test_group_students_drawer import _StudentsBase
from apps.accounts.views.syllabus.section import PAGE_SIZE, build_syllabus_list_section
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import CourseOffering, StudentAcademicRecord, Subject
from apps.syllabus import services as syllabus_services
from apps.syllabus.constants import SectionKey
from apps.syllabus.models import SyllabusVersion
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import OrgUnitType

User = get_user_model()
PASSWORD = "StrongPass123!"
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]


class _GroupScaleMixin:
    """Qrupa əlavə tələbə yazır (F-01 / F-03 miqyas addımı)."""

    def _add_students(self, count: int, prefix: str):
        for index in range(count):
            user = User.objects.create_user(f"{prefix}{index}", f"{prefix}{index}@qku.edu.az", PASSWORD)
            user.first_name, user.last_name = f"Əlavə{index}", f"Soyad{index}"
            user.save(update_fields=["first_name", "last_name"])
            Membership.objects.create(
                user=user, organization=self.org, role=self.roles["teacher"], is_primary=True, is_active=True
            )
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=user,
                program=self.program,
                curriculum=self.plan,
                group=self.group,
                admission_year=2024,
            )


class GroupStudentsQueryBudgetTest(_GroupScaleMixin, _StudentsBase):
    """F-01."""

    def test_query_count_is_independent_of_student_count(self):
        client = self._client("teaching_office_head")
        url = self._students_url()
        client.get(url)  # isinmə
        with CaptureQueriesContext(connection) as small:
            small_payload = client.get(url).json()
        self.assertEqual(len(small_payload["rows"]), 3)

        self._add_students(10, "pf01_")
        with CaptureQueriesContext(connection) as large:
            large_payload = client.get(url).json()
        self.assertEqual(len(large_payload["rows"]), 13)
        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "tələbə sayı artanda sorğu sayı artdı — `record.group` yenə N+1",
        )
        self.assertTrue(all(row["group_name"] == self.group.name for row in large_payload["rows"]))


class IndividualPlanQueryBudgetTest(_GroupScaleMixin, _StudentsBase):
    """F-03."""

    def _docx_text(self, payload: bytes) -> str:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return archive.read("word/document.xml").decode("utf-8")

    def test_query_count_is_independent_of_student_count(self):
        client = self._client("teaching_office_head")
        url = reverse("registrar:group_individual_plan", kwargs={"group_id": self.group.id})
        client.get(url)  # isinmə
        with CaptureQueriesContext(connection) as small:
            small_response = client.get(url)
        self.assertEqual(small_response["X-Students"], "3")

        self._add_students(10, "pf03_")
        with CaptureQueriesContext(connection) as large:
            large_response = client.get(url)
        self.assertEqual(large_response["X-Students"], "13")
        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "tələbə sayı artanda sorğu sayı artdı — dövr/kurikulum sorğusu yenə hər tələbə üçün",
        )
        xml = self._docx_text(large_response.content)
        self.assertEqual(xml.count('<w:br w:type="page"/>'), 12)
        for record in self.students:
            self.assertIn(record.student.get_full_name(), xml)
        self.assertIn("Əlavə9 Soyad9", xml)
        self.assertIn("QA-DS2 Alqoritmlər", xml)
        self.assertIn("QA-DS2 Diskret riyaziyyat", xml)
        self.assertIn(self.users["teacher"].username, xml)
        self.assertIn("Kompüter elmləri", xml)
        self.assertIn("Mühəndislik", xml)


class SyllabusListSectionBudgetTest(TestCase):
    """F-12."""

    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("pf12-univ")
        cls.teacher = User.objects.create_user("pf12_teacher", "pf12_teacher@x.test", PASSWORD)
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS, level=60)
        cls.stack = make_academic_stack(cls.org, code="PF12")
        cls.other_chair = OrgUnit.objects.create(
            organization=cls.org, name="PF12-ikinci kafedra", slug="pf12-univ-chair-2", unit_type=OrgUnitType.DEPARTMENT
        )
        cls.actor = syllabus_services.resolve_actor(cls.teacher, cls.org)
        cls.syllabi = []
        # Sillabusu OLMAYAN açılış — «Sillabus yarat» sətri.
        cls.missing_subject = Subject.objects.create(organization=cls.org, code="PF12-MISS", name="Sillabussuz")
        cls.missing_offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.missing_subject,
            period=cls.stack["period"],
            group=cls.stack["group"],
            instructor=cls.teacher,
            lesson_hours=sum(PLAN_HOURS.values()),
        )

    def _make_syllabi(self, count: int, prefix: str, *, chair=None):
        for index in range(count):
            subject = Subject.objects.create(
                organization=self.org, code=f"{prefix}{index:03d}", name=f"Fənn {prefix}{index}"
            )
            group = OrgUnit.objects.create(
                organization=self.org,
                name=f"{prefix}{index}-qrup",
                slug=f"pf12-univ-{prefix.lower()}{index}-group",
                unit_type=OrgUnitType.GROUP,
            )
            offering = make_offering(self.org, {**self.stack, "subject": subject, "group": group}, self.teacher)
            syllabus, _version = syllabus_services.create_draft(
                organization=self.org,
                subject=subject,
                period=self.stack["period"],
                actor=self.actor,
                offering=offering,
                program=self.stack["program"],
                chair_unit=chair or self.stack["chair"],
                author=self.teacher,
                plan_hours=dict(PLAN_HOURS),
            )
            self.syllabi.append(syllabus)

    def _request(self, **params):
        request = RequestFactory().get("/accounts/profile/", params)
        request.user = self.teacher
        request.org_permissions = list(TEACHER_PERMS)
        request.organization = self.org
        return request

    def _section(self, **params):
        return build_syllabus_list_section(self._request(**params), organization=self.org)["syllabus_list_section"]

    def test_query_count_is_independent_of_syllabus_count_and_pages_in_sql(self):
        self._make_syllabi(3, "A")
        self._section()  # isinmə
        with CaptureQueriesContext(connection) as small:
            small_section = self._section()
        self.assertEqual(small_section["page"]["total"], 4)  # 3 sillabus + 1 sillabussuz
        self.assertEqual(small_section["rows"][0]["kind"], "missing")

        self._make_syllabi(2 * PAGE_SIZE + 2, "B")
        with CaptureQueriesContext(connection) as large:
            large_section = self._section()
        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "sillabus sayı artanda sorğu sayı dəyişdi — dəst yenə Python-a yüklənir",
        )
        total = 3 + 2 * PAGE_SIZE + 2 + 1
        self.assertEqual(large_section["page"]["total"], total)
        self.assertEqual(large_section["page"]["count"], 3)
        self.assertEqual(len(large_section["rows"]), PAGE_SIZE)
        self.assertEqual(large_section["rows"][0]["kind"], "missing")
        self.assertEqual(large_section["rows"][0]["code"], "PF12-MISS")
        self.assertEqual(large_section["kpis"][0]["value"], total)
        self.assertEqual(next(c for c in large_section["kpis"] if c["key"] == "missing")["value"], 1)
        self.assertFalse(large_section["empty"])
        # Səhifə sətirləri LIMIT/OFFSET ilə gəlir: sillabus SELECT-ində LIMIT var,
        # heç bir sorğu bütün dəsti (LIMIT-siz sillabus sətirləri) çəkmir.
        syllabus_row_queries = [
            q["sql"]
            for q in large.captured_queries
            if q["sql"].startswith('SELECT "syllabus_syllabus"."created_at", "syllabus_syllabus"."updated_at"')
        ]
        self.assertTrue(syllabus_row_queries, "sillabus sətir sorğusu tapılmadı")
        self.assertTrue(all("LIMIT" in sql for sql in syllabus_row_queries), syllabus_row_queries)

        # Son səhifə: yalnız qalıq sətirlər, hamısı sillabusdur (missing 1-ci səhifədədir).
        last = self._section(page=3)
        self.assertEqual(len(last["rows"]), total - 2 * PAGE_SIZE)
        self.assertTrue(all(row["kind"] == "syllabus" for row in last["rows"]))
        codes = [row["code"] for row in self._section(page=1)["rows"] + self._section(page=2)["rows"] + last["rows"]]
        self.assertEqual(len(codes), len(set(codes)), "səhifələr arasında təkrar/itmə var")

    def test_status_missing_shows_only_offering_rows(self):
        # Qeyd: «missing» çipi domen sorğusuna `statuses=["missing"]` kimi ötürülür
        # (mövcud davranış, F-12-dən əvvəl də belə idi) — sillabus dəsti boş olur,
        # ona görə bütün açılışlar «sillabussuz» görünür; burada yalnız növ və
        # səhifələmə yoxlanılır (hesabatda ayrıca qeyd edilib).
        self._make_syllabi(2, "C")
        section = self._section(status="missing")
        self.assertTrue(section["rows"])
        self.assertTrue(all(row["kind"] == "missing" for row in section["rows"]))
        self.assertEqual(section["page"]["total"], len(section["rows"]))
        self.assertIn("PF12-MISS", {row["code"] for row in section["rows"]})

    def test_chair_filter_runs_in_sql_and_lists_units_of_the_visible_set(self):
        self._make_syllabi(2, "D")
        self._make_syllabi(3, "E", chair=self.other_chair)
        section = self._section(unit=str(self.other_chair.pk))
        self.assertEqual(section["page"]["total"], 3 + 1)  # 3 sillabus + sillabussuz açılış
        self.assertEqual({row["code"][:1] for row in section["rows"] if row["kind"] == "syllabus"}, {"E"})
        self.assertEqual(
            [unit["label"] for unit in section["filter_options"]["units"]],
            sorted([self.stack["chair"].name, self.other_chair.name]),
        )
        # Yanlış UUID → boş sillabus dəsti (əvvəlki `str(chair_unit_id) == unit` ilə eyni).
        self.assertEqual(self._section(unit="yanlış")["page"]["total"], 1)

    def test_semester_filter_runs_in_sql(self):
        self._make_syllabi(2, "F")
        self.assertEqual(self._section(semester=self.stack["period"].name)["page"]["total"], 3)
        self.assertEqual(self._section(semester="Yoxdur")["page"]["total"], 0)

    def test_sla_filter_and_kpi_match_the_python_rule(self):
        self._make_syllabi(3, "G")
        actor = self.actor
        stamps = (9, 6, 1)  # SLA default 5 gün: 9 və 6 gecikib, 1 gecikməyib
        for syllabus, days in zip(self.syllabi[-3:], stamps):
            for section_id, data in complete_section_data().items():
                if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
                    continue
                syllabus_services.save_section(
                    version=syllabus.current_version, section_id=section_id, data=data, actor=actor
                )
            version = syllabus_services.submit(version=syllabus.current_version, actor=actor)
            SyllabusVersion.objects.filter(pk=version.pk).update(
                submitted_at=timezone.now() - timezone.timedelta(days=days)
            )
        sla_card = next(card for card in self._section()["kpis"] if card["key"] == "sla")
        self.assertEqual(sla_card["value"], 2)
        section = self._section(status="sla")
        self.assertEqual(section["page"]["total"], 2)
        self.assertEqual({row["code"] for row in section["rows"]}, {"G000", "G001"})
