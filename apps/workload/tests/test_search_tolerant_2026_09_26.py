"""Yük bölgüsü axtarışları dözümlüdür (sahib 2026-09-26).

* müəllim hovuzu: «Aliyev» / «Shahzad» → «Şahzad Əliyev»;
* tapşırıq sətirləri: fənn adı az/ing hərfinə, qrup mətni kod rejimində («234king» → «234 K ing»).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.workload.models import TeachingTaskRow
from apps.workload.services import task_rows, teacher_pool
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


class WorkloadTolerantSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("wl-tol")
        cls.stack = make_structure(cls.org, code="WT")
        cls.teacher = User.objects.create_user(
            "wl_tol_t", "wl_tol_t@x.test", "pw", first_name="Şahzad", last_name="Əliyev"
        )
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.stack["chair"])
        cls.task = make_task(cls.org, cls.stack["chair"])
        cls.row = make_row(cls.task, cls.stack)
        TeachingTaskRow.objects.filter(pk=cls.row.pk).update(groups_text="234 K ing")

    def test_teacher_pool_folds_azerbaijani_letters(self):
        for query in ("Aliyev", "Shahzad", "sahzad eliyev"):
            with self.subTest(query=query):
                ids = {row["id"] for row in teacher_pool(self.org, self.stack["chair"], search=query)}
                self.assertEqual(ids, {str(self.teacher.pk)})
        self.assertEqual(teacher_pool(self.org, self.stack["chair"], search="Məmmədov"), [])

    def test_task_rows_search_subject_and_group_text(self):
        for query in ("alqoritmler", "234king", "234-K-ing", "WT 101"):
            with self.subTest(query=query):
                self.assertEqual(list(task_rows(self.task, search=query).values_list("pk", flat=True)), [self.row.pk])
        self.assertFalse(task_rows(self.task, search="Kimya").exists())
