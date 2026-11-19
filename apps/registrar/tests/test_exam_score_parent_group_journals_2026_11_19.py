"""MR-580 (2026-11-19): imtahan balında alt qrup seçiləndə ana qrupun birgə jurnalları da görünür.

«536 Bi 1» seçiləndə «Xətti cəbr…» çıxmırdı — fənn «536 Bİ»-nin birgə jurnalında keçilir. İndi alt qrupun öz
jurnalı olmayan fənlər üçün ana qrupun jurnalı «536 Bİ ilə birgə» qeydi ilə siyahıya düşür; öz jurnalı olan fənn
təkrarlanmır.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.organizations.models import OrgUnit
from apps.registrar import exam_score_sheets as sheets
from apps.registrar.models import CourseOffering, Subject
from apps.registrar.tests.test_exam_score_assessment_2026_10_25 import _MEDIA, MidtermPeriodFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class ExamScoreParentGroupJournalsTest(MidtermPeriodFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.build_fixture("pgj")
            cls.specialty = OrgUnit.objects.create(
                organization=cls.org, name="PGJ ixtisas", slug="pgj-spec", unit_type=OrgUnitType.SPECIALTY
            )
            OrgUnit.objects.filter(pk=cls.group.pk).update(parent=cls.specialty)
            cls.sub = OrgUnit.objects.create(
                organization=cls.org,
                name="PGJ-101-1",
                slug="pgj-101-1",
                unit_type=OrgUnitType.GROUP,
                parent=cls.specialty,
            )
            cls.own_subject = Subject.objects.create(organization=cls.org, code="PGJ-OWN", name="Öz fənn")
            cls.own = CourseOffering.objects.create(
                organization=cls.org, subject=cls.own_subject, period=cls.offering.period, group=cls.sub
            )

    def _offerings(self):
        with bypass_rls():
            return sheets.offerings_for_group(organization=self.org, period=self.offering.period, group_id=self.sub.pk)

    def test_subgroup_sees_parent_joint_journal_for_missing_subject(self):
        offerings = self._offerings()
        self.assertEqual([o.pk for o in offerings], [self.own.pk, self.offering.pk])
        self.assertEqual(getattr(offerings[1], "joint_group_name", ""), "PGJ-101")
        self.assertEqual(getattr(offerings[0], "joint_group_name", ""), "")

    def test_parent_journal_skipped_when_subgroup_has_own_journal_of_subject(self):
        with bypass_rls():
            mine = CourseOffering.objects.create(
                organization=self.org, subject=self.offering.subject, period=self.offering.period, group=self.sub
            )
        self.assertEqual({o.pk for o in self._offerings()}, {self.own.pk, mine.pk})

    def test_parent_group_itself_is_unchanged(self):
        with bypass_rls():
            offerings = sheets.offerings_for_group(
                organization=self.org, period=self.offering.period, group_id=self.group.pk
            )
        self.assertNotIn(self.own.pk, {o.pk for o in offerings})
        self.assertIn(self.offering.pk, {o.pk for o in offerings})
