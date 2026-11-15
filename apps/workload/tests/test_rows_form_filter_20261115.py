"""«Yük bölgüsü»: təhsil forması süzgəci (sahib 2026-11-15) — ``form=qiyabi`` / ``form=eyani``.

Qiyabi = sətrin forması ``qiyabi`` və ya qruplarından birinin adı qiyabi kod (4 rəqəm + şəkilçi, məs. «2032P»);
köçürmədə sətirlərin çoxu defolt «əyani» qalıb. Naməlum dəyər süzgəc sayılmır.
"""

from __future__ import annotations

from django.test import TestCase

from apps.organizations.models import OrgUnit
from apps.workload.constants import TaskStatus
from apps.workload.models import TeachingTaskRow
from apps.workload.services.queries import rows_page

from .factories import make_org, make_row, make_structure, make_task


class RowFormFilterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("form1115")
        cls.stack = make_structure(cls.org, code="FRM")
        cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.APPROVED)
        qiyabi_group = OrgUnit.objects.create(
            organization=cls.org, name="2032P", slug="form1115-2032p", unit_type="group", parent=cls.stack["specialty"]
        )
        cls.eyani = make_row(cls.task, cls.stack, lecture_total=30)
        cls.by_name = make_row(cls.task, {**cls.stack, "group": qiyabi_group}, lecture_total=30)
        cls.by_form = make_row(cls.task, cls.stack, lecture_total=30)
        TeachingTaskRow.objects.filter(pk=cls.by_form.pk).update(education_form="qiyabi")

    def ids(self, form):
        return {row["id"] for row in rows_page(self.task, form=form, limit=50)["rows"]}

    def test_qiyabi_by_group_name_or_row_form(self):
        self.assertEqual(self.ids("qiyabi"), {str(self.by_name.pk), str(self.by_form.pk)})

    def test_eyani_is_the_rest(self):
        self.assertEqual(self.ids("eyani"), {str(self.eyani.pk)})

    def test_unknown_value_is_ignored(self):
        self.assertEqual(len(self.ids("bogus")), 3)
