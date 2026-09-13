"""Perf auditi 2026-09-13 F-04 — `syllabus_for_offering` üç pilləni üç ayrı
`.first()` ilə axtarırdı (sillabussuz açılışda hər çağırış 3 sorğu; jurnal
detalında 4 çağıran × 3 = 12 eyni SELECT) → TƏK sorğu, prioritet eyni:
açılış → (fənn, dövr) → (fənn, müəllif, dövrsüz).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.registrar.models import Subject
from apps.syllabus import services
from apps.syllabus.tests.factories import PLAN_HOURS, activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
PASSWORD = "StrongPass123!"
TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]


class SyllabusForOfferingSingleQueryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("pf04-univ")
        cls.teacher = User.objects.create_user("pf04_teacher", "pf04_teacher@x.test", PASSWORD)
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS, level=60)
        cls.stack = make_academic_stack(cls.org, code="PF04")
        cls.offering = make_offering(cls.org, cls.stack, cls.teacher)
        cls.actor = services.resolve_actor(cls.teacher, cls.org)

    def _draft(self, *, subject, period, offering=None):
        syllabus, _version = services.create_draft(
            organization=self.org,
            subject=subject,
            period=period,
            actor=self.actor,
            offering=offering,
            program=self.stack["program"],
            chair_unit=self.stack["chair"],
            author=self.teacher,
            plan_hours=dict(PLAN_HOURS),
        )
        return syllabus

    def _lookup(self):
        with CaptureQueriesContext(connection) as ctx:
            found = services.syllabus_for_offering(
                organization=self.org,
                offering_id=self.offering.id,
                subject_id=self.offering.subject_id,
                period_id=self.offering.period_id,
                instructor_id=self.offering.instructor_id,
            )
        return found, len(ctx.captured_queries)

    def test_missing_syllabus_costs_one_query(self):
        found, queries = self._lookup()
        self.assertIsNone(found)
        self.assertEqual(queries, 1)

    def test_tiers_keep_their_priority_in_one_query(self):
        subject, period = self.stack["subject"], self.stack["period"]
        base = self._draft(subject=subject, period=None)  # (fənn, müəllif) — 3-cü pillə
        found, queries = self._lookup()
        self.assertEqual((found.pk, queries), (base.pk, 1))

        semester = self._draft(subject=subject, period=period)  # (fənn, dövr) — 2-ci pillə
        found, queries = self._lookup()
        self.assertEqual((found.pk, queries), (semester.pk, 1))

        own = self._draft(subject=subject, period=period, offering=self.offering)  # 1-ci pillə
        found, queries = self._lookup()
        self.assertEqual((found.pk, queries), (own.pk, 1))
        # `select_related` qorunub: əlaqəli obyektlər əlavə sorğusuz oxunur.
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(found.subject.code, "PF04")
            self.assertEqual(found.offering_id, self.offering.id)
            self.assertIsNotNone(found.current_version)
        self.assertEqual(len(ctx.captured_queries), 0)

    def test_lower_tiers_are_skipped_when_their_keys_are_missing(self):
        subject = self.stack["subject"]
        self._draft(subject=subject, period=None)
        # Müəllif verilməyibsə 3-cü pillə axtarılmır; fənn verilməyibsə heç sorğu yoxdur.
        with CaptureQueriesContext(connection) as ctx:
            self.assertIsNone(
                services.syllabus_for_offering(
                    organization=self.org, offering_id=self.offering.id, subject_id=subject.id, period_id=None
                )
            )
        self.assertEqual(len(ctx.captured_queries), 1)
        with CaptureQueriesContext(connection) as ctx:
            self.assertIsNone(services.syllabus_for_offering(organization=self.org, offering_id=None, subject_id=None))
        self.assertEqual(len(ctx.captured_queries), 0)

    def test_other_subject_or_inactive_file_is_not_matched(self):
        other = Subject.objects.create(organization=self.org, code="PF04-X", name="Başqa")
        self._draft(subject=other, period=self.stack["period"])
        found, _queries = self._lookup()
        self.assertIsNone(found)
