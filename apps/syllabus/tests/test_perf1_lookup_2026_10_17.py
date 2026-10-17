"""PERF-1 F-14 (2026-10-17): sillabus axtarışında pillə seçimi JOIN-suz alt-sorğuda, tam obyekt PK ilə.

Əvvəl tək sorğu 9 əlaqəli cədvəli JOIN edib Case/OR pillələri ilə sıralayırdı — planlaşdırma ~6–7 ms, icra
0,25 ms. İndi Case/OR pillələri yalnız `registrar_subject`-ə qoşulan alt-sorğudadır; xarici sorğu
`select_related`-i PK bərabərliyi ilə edir. Round-trip yenə BİRDİR, nəticə eynidir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.syllabus import services
from apps.syllabus.tests.factories import PLAN_HOURS, activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]


class SyllabusLookupShapeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("pf1-f14")
        cls.teacher = User.objects.create_user("pf1f14_teacher", "pf1f14_teacher@x.test", "pw")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS, level=60)
        cls.stack = make_academic_stack(cls.org, code="PF14")
        cls.offering = make_offering(cls.org, cls.stack, cls.teacher)
        cls.actor = services.resolve_actor(cls.teacher, cls.org)

    def _lookup(self):
        with CaptureQueriesContext(connection) as ctx:
            found = services.syllabus_for_offering(
                organization=self.org,
                offering_id=self.offering.id,
                subject_id=self.offering.subject_id,
                period_id=self.offering.period_id,
                instructor_id=self.offering.instructor_id,
            )
        return found, ctx.captured_queries

    def _draft(self, **extra):
        syllabus, _version = services.create_draft(
            organization=self.org,
            subject=self.stack["subject"],
            actor=self.actor,
            program=self.stack["program"],
            chair_unit=self.stack["chair"],
            author=self.teacher,
            plan_hours=dict(PLAN_HOURS),
            **extra,
        )
        return syllabus

    def test_tier_query_joins_only_subject(self):
        own = self._draft(period=self.stack["period"], offering=self.offering)
        self._draft(period=None)  # aşağı pillə — seçilməməlidir
        found, queries = self._lookup()
        self.assertEqual(found.pk, own.pk)
        self.assertEqual(len(queries), 1)
        sql = queries[0]["sql"]
        inner = sql[sql.index('"syllabus_syllabus"."id" = (SELECT') :]
        self.assertIn("CASE WHEN", inner)
        self.assertEqual(inner.count("JOIN"), 1, inner)
        self.assertIn('JOIN "registrar_subject"', inner)
        self.assertNotIn("CASE WHEN", sql[: sql.index('"syllabus_syllabus"."id" = (SELECT')])
        # Tam obyekt əvvəlki kimi əlaqələri ilə gəlir — əlavə sorğu yoxdur.
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(found.subject.code, "PF14")
            self.assertIsNotNone(found.current_version)
            self.assertEqual(found.author_id, self.teacher.pk)
        self.assertEqual(len(ctx.captured_queries), 0)

    def test_query_count_does_not_grow_with_candidate_files(self):
        self._draft(period=None)
        _found, few = self._lookup()
        self._draft(period=self.stack["period"])
        self._draft(period=self.stack["period"], offering=self.offering)
        _found, many = self._lookup()
        self.assertEqual(len(few), len(many))
