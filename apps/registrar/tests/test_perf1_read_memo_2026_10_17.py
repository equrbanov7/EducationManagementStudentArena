"""PERF-1 (2026-10-17): request-ömürlü oxu memo-su (F-05/F-06) və «Cədvəlim» toplu giriş balı (F-04).

Nəyi qoruyur
------------
* ``read_memo.per_id`` — sahə yoxdursa funksiya OLDUĞU KİMİ çağırılır; sahədə yalnız görülməmiş id-lər
  sorğuya gedir; nəticənin forması eynidir; komponent yazısı sahəni təmizləyir;
* «Fənlərim»: donma (sxem statusu), dərs saatı cəmi və komponent dəsti bölmədə BİR dəfə oxunur;
* «Cədvəlim»: sorğu sayı fənn sayından asılı deyil (əvvəl fənn başına 2 sorğu idi);
* jurnal «Yekun» tabı: siyahı (roster), komponent dəsti və donma bir dəfə oxunur; səhifə məzmunu memo ilə
  və memo-suz EYNİDİR.
"""

from __future__ import annotations

from unittest import mock

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.registrar import exam_eligibility, read_memo
from apps.registrar.models import AssessmentComponent, ComponentKind
from apps.registrar.tests.test_student_sections_redesign import _build_tenant, _client_for
from core.rls import bypass_rls

_SCHEME_STATUS = '"registrar_assessmentscheme"."is_published" AS "is_published"'
_HOURS_SUM = 'SUM("registrar_lesson"."hours")'
_COMPONENTS = "midterm_from_year"
_ROSTER = 'ORDER BY "auth_user"."last_name" ASC, "auth_user"."username" ASC'


def _count(ctx, needle) -> int:
    return sum(1 for q in ctx.captured_queries if needle in q["sql"])


class PerIdMemoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = _build_tenant(slug="rmemo", subject_count=3)
        cls.offering_ids = [e.offering_id for e in cls.tenant["enrollments"]]

    def test_without_scope_every_call_queries(self):
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            first = exam_eligibility.lesson_hours_map(self.offering_ids)
            second = exam_eligibility.lesson_hours_map(self.offering_ids)
        self.assertEqual(first, second)
        self.assertEqual(_count(ctx, _HOURS_SUM), 2)

    def test_scope_loads_only_missing_ids_and_keeps_the_shape(self):
        with bypass_rls():
            expected_all = exam_eligibility.lesson_hours_map(self.offering_ids)
            expected_frozen = exam_eligibility.frozen_offering_ids(self.offering_ids)
            with read_memo.scope(), CaptureQueriesContext(connection) as ctx:
                part = exam_eligibility.lesson_hours_map(self.offering_ids[:1])
                whole = exam_eligibility.lesson_hours_map(self.offering_ids)
                again = exam_eligibility.lesson_hours_map(list(reversed(self.offering_ids)))
                frozen = exam_eligibility.frozen_offering_ids(self.offering_ids)
                frozen_again = exam_eligibility.frozen_offering_ids(self.offering_ids[1:])
        self.assertEqual(part, {k: v for k, v in expected_all.items() if k == self.offering_ids[0]})
        self.assertEqual(whole, expected_all)
        self.assertEqual(again, expected_all)
        self.assertEqual(frozen, expected_frozen)
        self.assertEqual(frozen_again, frozenset(expected_frozen) & set(self.offering_ids[1:]))
        self.assertIsInstance(frozen, frozenset)
        # 1 + 1 (yalnız qalan id-lər) + 0; donma — sxem statusu bir dəfə.
        self.assertEqual(_count(ctx, _HOURS_SUM), 2)
        self.assertEqual(_count(ctx, _SCHEME_STATUS), 1)

    def test_querysets_and_odd_ids_pass_through(self):
        from apps.registrar.models import CourseOffering

        with bypass_rls(), read_memo.scope(), CaptureQueriesContext(connection) as ctx:
            qs = CourseOffering.objects.filter(pk__in=self.offering_ids).values("id")
            exam_eligibility.lesson_hours_map(qs)
            exam_eligibility.lesson_hours_map(qs)
            exam_eligibility.lesson_hours_map([str(pk) for pk in self.offering_ids])
            exam_eligibility.lesson_hours_map([str(pk) for pk in self.offering_ids])
        self.assertEqual(_count(ctx, _HOURS_SUM), 4)

    def test_component_write_clears_the_scope(self):
        from apps.registrar import finals_batch

        offering = self.tenant["enrollments"][0].offering
        with bypass_rls(), read_memo.scope():
            before, _carried, _bits = finals_batch._components_with_period([offering.id])
            AssessmentComponent.objects.create(
                organization=offering.organization,
                offering=offering,
                name="PERF1 komponent",
                kind=ComponentKind.GENERIC,
                max_score=10,
                order=99,
            )
            after, _carried, _bits = finals_batch._components_with_period([offering.id])
        self.assertEqual(len(after.get(offering.id, [])), len(before.get(offering.id, [])) + 1)

    def test_scope_is_reset_after_the_block(self):
        with read_memo.scope():
            self.assertTrue(read_memo.active())
            with read_memo.scope():
                self.assertTrue(read_memo.active())
            self.assertTrue(read_memo.active())
        self.assertFalse(read_memo.active())


@override_settings(UNIVERSITY_MODE=True)
class StudentSectionsBudgetTest(TestCase):
    def _get(self, tenant, section):
        client = _client_for(tenant["org"], tenant["student"])
        url = reverse("accounts:profile") + f"?section={section}"
        client.get(url)  # isinmə
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(url)
        self.assertEqual(resp.status_code, 200)
        return ctx, resp

    def test_my_subjects_reads_shared_inputs_once(self):
        tenant = _build_tenant(slug="rmsub", subject_count=4)
        ctx, _resp = self._get(tenant, "my-subjects")
        # Əvvəl: sxem statusu 3×, saat cəmi 3×, komponent dəsti 2× (services → analytics → finals_batch).
        self.assertEqual(_count(ctx, _SCHEME_STATUS), 1)
        self.assertEqual(_count(ctx, _HOURS_SUM), 1)
        self.assertEqual(_count(ctx, _COMPONENTS), 1)

    def test_my_schedule_query_count_does_not_grow_with_subjects(self):
        one = _build_tenant(slug="rmsch1", subject_count=1)
        three = _build_tenant(slug="rmsch3", subject_count=3)
        q1 = len(self._get(one, "my-schedule")[0].captured_queries)
        q3 = len(self._get(three, "my-schedule")[0].captured_queries)
        self.assertEqual(q3, q1, "«Cədvəlim»: fənn sayı sorğu sayını artırdı")


@override_settings(UNIVERSITY_MODE=True)
class JournalYekunMemoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = _build_tenant(slug="rmyek", subject_count=1)
        cls.offering = cls.tenant["enrollments"][0].offering

    def _get(self):
        client = _client_for(self.tenant["org"], self.tenant["teacher"])
        url = reverse("registrar:journal_detail", args=[self.offering.pk])
        client.get(url, {"jt": "yekun"})  # isinmə
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(url, {"jt": "yekun"})
        self.assertEqual(resp.status_code, 200)
        return ctx, resp

    def test_yekun_reads_roster_components_and_eligibility_once(self):
        ctx, _resp = self._get()
        self.assertEqual(_count(ctx, _COMPONENTS), 1)  # əvvəl 3× (qrid, nəticələr, bölgü)
        self.assertEqual(_count(ctx, _SCHEME_STATUS), 1)  # əvvəl 2×
        self.assertEqual(_count(ctx, _ROSTER), 1)  # əvvəl 5–6×

    def test_yekun_output_is_identical_without_the_memo(self):
        ctx, resp = self._get()
        with mock.patch.object(read_memo, "_SCOPE") as scope_var:
            scope_var.get.return_value = None
            plain_ctx, plain = self._get()
        self.assertLess(len(ctx.captured_queries), len(plain_ctx.captured_queries))
        strip = lambda html: "\n".join(  # noqa: E731
            line for line in html.decode().splitlines() if "csrf" not in line.lower() and "nonce" not in line
        )
        self.assertEqual(strip(resp.content), strip(plain.content))
