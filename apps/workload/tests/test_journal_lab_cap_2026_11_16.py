"""MR-000383 (2026-11-16): çox qruplu lab sətrində hər jurnalın lab həddi qrupun REAL alt qrup sayı qədərdir.

234 BİO/SBİO Mikrobiologiya lab: sətirdə 2 qrup, 3 lab alt qrupu, qrup başına plan 30. Əvvəl hər qrupa
``ceil(3 ÷ 2) = 2`` alt qrup yazılırdı — tək alt qruplu qrupun jurnalı da 60 göstərirdi. Sahib 2026-11-08: lab həddi
qrup başına plandır, alt qrupa yalnız real say qədər vurulur.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.workload.models import TeacherAssignment
from apps.workload.services.journal_assignments import teacher_journal_plan_hours
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.constants import OrgUnitType


class MultiGroupLabCapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("lab-cap-383")
        cls.stack = make_structure(cls.org, code="LC383")
        cls.bio = cls.stack["group"]
        cls.sbio = cls._group("LC383-SBİO", "sbio")
        cls.task = make_task(cls.org, cls.stack["chair"], status="amended")
        cls.teacher = get_user_model().objects.create_user("lab-cap-383", first_name="Lab", last_name="Teacher")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)

    @classmethod
    def _group(cls, name, slug, *, parent_group=None):
        return OrgUnit.objects.create(
            organization=cls.org,
            name=name,
            slug=f"{cls.org.slug}-{slug}",
            unit_type=OrgUnitType.GROUP,
            parent=cls.stack["specialty"],
            settings={"parent_group": str(parent_group.pk)} if parent_group else {},
        )

    def _row(self, subgroups):
        row = make_row(self.task, self.stack, lecture_total=0, seminar_total=0, lab_total=30 * subgroups)
        row.lab_plan, row.subgroup_count = 30, subgroups
        row.save(update_fields=["lab_plan", "subgroup_count"])
        row.groups.set([self.bio, self.sbio])
        return row

    def _assign(self, row, hours, *, sub_number=None, group=None):
        TeacherAssignment.objects.create(
            organization=self.org,
            row=row,
            teacher=self.teacher,
            activity="lab",
            hours=hours,
            sub_number=sub_number,
            group=group,
        )

    def _lab(self, group):
        hours = teacher_journal_plan_hours(organization=self.org, teacher_id=self.teacher.pk)
        key = (self.stack["subject"].pk, self.stack["period"].pk, group.pk)
        return dict(hours.get(key, {})).get("lab")

    def test_three_subgroups_over_two_groups_never_doubles_a_journal(self):
        self._assign(self._row(3), 90)
        self.assertEqual((self._lab(self.bio), self._lab(self.sbio)), (30, 30))

    def test_registered_subgroups_give_the_real_count_and_the_rest_goes_to_the_other_group(self):
        first = self._group("LC383-BİO-1", "bio-1", parent_group=self.bio)
        second = self._group("LC383-BİO-2", "bio-2", parent_group=self.bio)
        self._assign(self._row(3), 90)
        self.assertEqual((self._lab(self.bio), self._lab(self.sbio)), (60, 30))
        self.assertEqual((self._lab(first), self._lab(second)), (30, 30), "alt qrupun öz jurnalı — bir alt qrup")

    def test_an_even_split_is_shared_equally(self):
        self._assign(self._row(4), 120)
        self.assertEqual((self._lab(self.bio), self._lab(self.sbio)), (60, 60))

    def test_row_level_numbers_without_a_group_do_not_multiply_each_journal(self):
        row = self._row(3)
        for number in (1, 2, 3):
            self._assign(row, 30, sub_number=number)
        self.assertEqual((self._lab(self.bio), self._lab(self.sbio)), (30, 30))

    def test_numbers_bound_to_a_group_count_exactly(self):
        row = self._row(3)
        self._assign(row, 30, sub_number=1, group=self.bio)
        self._assign(row, 30, sub_number=2, group=self.bio)
        self._assign(row, 30, sub_number=1, group=self.sbio)
        self.assertEqual((self._lab(self.bio), self._lab(self.sbio)), (60, 30))
