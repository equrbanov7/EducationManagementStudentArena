"""Dərs yükü giriş qapıları — QA 2026-09-05 WORKLOAD-SCHEDULE-01/02 reqressiya qapısı."""

from __future__ import annotations

from django.apps import apps as django_apps
from django.test import SimpleTestCase, TestCase

from apps.workload.services.people import parse_uuid, resolve_chair
from apps.workload.services.scoping import WorkloadDenied
from apps.workload.services.tasks import normalize_academic_year


class AcademicYearGuardTest(SimpleTestCase):
    def test_valid_forms_normalise(self):
        self.assertEqual(normalize_academic_year("2026/2027"), "2026/2027")
        self.assertEqual(normalize_academic_year("2026-2027"), "2026/2027")

    def test_garbage_and_out_of_range_years_are_rejected(self):
        # `format_year` ilk 4 rəqəmli ili götürüb Y/Y+1 qurur ("2026/2029" → "2026/2027" — qəsdli);
        # burada yalnız il TAPILMAYAN və ya diapazondan kənar dəyərlər rədd edilir.
        for raw in ("abc", "", "1800/1801", "iki min", "9999"):
            self.assertEqual(normalize_academic_year(raw), "", raw)


class ChairIdGuardTest(SimpleTestCase):
    def test_non_uuid_chair_is_denied_not_500(self):
        self.assertIsNone(parse_uuid("x"))
        self.assertIsNone(parse_uuid(""))
        with self.assertRaises(WorkloadDenied):
            resolve_chair(None, "x")


class CurrentAcademicYearSourceTest(TestCase):
    """Cari tədris ili tək mənbədən gəlir — QA 2026-09-05 UX-09."""

    def test_period_wins_over_a_newer_task_year(self):
        from apps.workload.center_registry import current_academic_year
        from apps.workload.models import TeachingTask

        from .factories import make_org, make_structure, make_task

        org = make_org("yearsrc")
        stack = make_structure(org, code="YS")
        task = make_task(org, stack["chair"])
        TeachingTask.objects.filter(pk=task.pk).update(academic_year="2030/2031")
        # `is_current` dövr yoxdur; ən son BAŞLAYAN dövr qazanmalıdır (tapşırıq ili yox).
        AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
        AcademicPeriod.objects.filter(organization=org).update(is_current=False)
        self.assertEqual(
            current_academic_year(org),
            AcademicPeriod.objects.filter(organization=org)
            .order_by("-start_date")
            .values_list("academic_year", flat=True)
            .first(),
        )
