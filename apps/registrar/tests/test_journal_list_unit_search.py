"""Məktəb/qrup seçicisi akademik qeydlər deyil, jurnal əhatəsi ilə işləyir."""

from django.test import TestCase
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.registrar.models import Subject
from core.constants import OrgUnitType
from core.rls import bypass_rls

from . import test_journal_list_teacher_search as fixtures


class JournalListUnitSearchTest(TestCase):
    setUpTestData = classmethod(fixtures.JournalListTeacherSearchTest.setUpTestData.__func__)

    def _units(self, kind, user=None, **query):
        self.client.force_login(user or self.coordinator)
        response = self.client.get(reverse(f"registrar:journal_list_{kind}"), query)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_faculty_scoped_coordinator_sees_only_visible_units(self):
        self.assertEqual([r["text"] for r in self._units("faculties")["results"]], ["Fak A"])
        self.assertEqual([r["text"] for r in self._units("groups")["results"]], ["A1"])
        self.assertEqual(self._units("groups", faculty=str(self.fac_b.pk))["results"], [])

    def test_chair_comes_from_subject_not_group_ancestors(self):
        with bypass_rls():
            chair = OrgUnit.objects.create(
                organization=self.org,
                name="Tarix kafedrası",
                slug="jlu-chair",
                unit_type=OrgUnitType.CHAIR,
                parent=self.fac_a,
            )
            Subject.objects.filter(organization=self.org, code="JLT0").update(chair_unit=chair)
        self.assertEqual([r["text"] for r in self._units("departments", q="tarix")["results"]], [chair.name])

    def test_non_broad_teacher_gets_no_unit_directory(self):
        for kind in ("faculties", "departments", "groups"):
            self.assertEqual(self._units(kind, user=self.teachers["jlt_firuze"])["results"], [])

    def test_group_search_pagination_and_invalid_faculty(self):
        result = self._units("groups", user=self.corrector, limit=1)
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["has_more"])
        self.assertEqual(self._units("groups", faculty="bad-id")["results"], [])
        self.assertEqual([r["text"] for r in self._units("groups", q="A 1")["results"]], ["A1"])
