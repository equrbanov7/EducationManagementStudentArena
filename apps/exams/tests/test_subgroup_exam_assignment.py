"""Ana qrup ↔ alt qrup imtahan təyinatı (sahib 2026-09-21).

* Sehrbaz qrup axtarışı boşluğa dözümlüdür («234k» → «234 K az») və hər ana qrup
  üçün `subgroups` verir (klient onları avtomatik seçir).
* Ana qrup seçiləndə alt qrupların tələbələri `user_search`-də «qrupla daxildir»
  kimi işarələnir.
* Ana qrupa təyin olunmuş imtahanı alt qrupun tələbəsi görür/başlaya bilir;
  `unit_assigned_student_ids` alt qrup tələbələrini də sayır.
* «Sual əlavə et»/«Redaktə» tam səhifə GET-i detal səhifəsinə yönlənir
  (`?question_modal=…`) — ayrıca səhifə yoxdur.
"""

from django.urls import reverse

from apps.exams.domain.unit_assignment import unit_assigned_student_ids
from apps.exams.models import ExamQuestion as Question
from apps.organizations.models import OrgUnit
from apps.registrar.models import StudentAcademicRecord
from apps.registrar.subgroup_rollup import parent_group_candidates, subgroup_map
from core.constants import OrgUnitType
from core.rls import bypass_rls

from .test_exam_center_policy import PASSWORD, _assign_user_to_org
from .test_w4_wizard_units import ProfileRole, User, _login, _UnitFixture


class _SubgroupFixture(_UnitFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.parent_group = OrgUnit.objects.create(
                organization=cls.org, parent=cls.faculty, name="234 K az", slug="w4u-234k", unit_type=OrgUnitType.GROUP
            )
            cls.sub1 = OrgUnit.objects.create(
                organization=cls.org, parent=cls.faculty, name="234 K-1", slug="w4u-234k1", unit_type=OrgUnitType.GROUP
            )
            cls.sub2 = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="234 K ing-2",  # sektor fərqli → ana qrupun alt qrupu DEYİL
                slug="w4u-234king2",
                unit_type=OrgUnitType.GROUP,
            )
            record = StudentAcademicRecord.objects.filter(student=cls.student).first()
            cls.sub_student = User.objects.create_user("w4u_sub_student", "w4u_sub@test.az", PASSWORD)
            _assign_user_to_org(cls.sub_student, cls.org, ProfileRole.STUDENT, "student")
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.sub_student,
                program=record.program,
                curriculum=record.curriculum,
                group=cls.sub1,
                admission_year=2024,
            )


class SubgroupHelpersTest(_SubgroupFixture):
    def test_subgroup_map_and_parent_candidates(self):
        with bypass_rls():
            mapping = subgroup_map(self.org, [self.parent_group, self.group])
            self.assertEqual([u.name for u in mapping.get(self.parent_group.pk, [])], ["234 K-1"])
            self.assertNotIn(self.group.pk, mapping)
            self.assertEqual([u.name for u in parent_group_candidates(self.org, self.sub1)], ["234 K az"])
            self.assertEqual(parent_group_candidates(self.org, self.sub2), [])


class WizardSearchTest(_SubgroupFixture):
    def test_group_search_is_space_insensitive_and_lists_subgroups(self):
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:group_search"), {"kind": "units", "q": "234k"})
        self.assertEqual(response.status_code, 200)
        results = {row["text"].split(" — ")[0]: row for row in response.json()["results"]}
        self.assertIn("234 K az", results)
        self.assertIn("234 K-1", results)
        self.assertEqual([s["text"].split(" — ")[0] for s in results["234 K az"]["subgroups"]], ["234 K-1"])
        self.assertEqual(results["234 K-1"]["subgroups"], [])

    def test_user_search_marks_subgroup_students_when_parent_selected(self):
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:user_search"), {"units": str(self.parent_group.pk), "limit": 50})
        self.assertEqual(response.status_code, 200)
        marked = {row["id"] for row in response.json()["results"] if row["group_member"]}
        self.assertIn(str(self.sub_student.pk), marked)
        self.assertNotIn(str(self.student.pk), marked)


class SubgroupAccessTest(_SubgroupFixture):
    def test_parent_assignment_admits_subgroup_student(self):
        exam = self._exam()
        exam.allowed_units.add(self.parent_group)
        self.assertTrue(exam.can_user_see(self.sub_student))
        ok, reason = exam.can_user_start(self.sub_student)
        self.assertTrue(ok, reason)
        self.assertFalse(exam.can_user_see(self.student))  # başqa qrup
        with bypass_rls():
            self.assertEqual(unit_assigned_student_ids(exam), {self.sub_student.pk})

    def test_subgroup_assignment_does_not_admit_parent_group_only_students(self):
        exam = self._exam()
        exam.allowed_units.add(self.sub1)
        self.assertTrue(exam.can_user_see(self.sub_student))
        self.assertFalse(exam.can_user_see(self.student))


class QuestionPageRedirectTest(_SubgroupFixture):
    def test_full_page_add_and_edit_redirect_to_detail_with_modal_flag(self):
        exam = self._exam()
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:add_exam_question", kwargs={"slug": exam.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/{exam.slug}/?question_modal=create", response["Location"])
        question = Question.objects.create(exam=exam, text="Q1", order=1)
        response = client.get(
            reverse("exams:edit_exam_question", kwargs={"slug": exam.slug, "question_id": question.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"question_modal=edit&question={question.pk}", response["Location"])
        # Modal sorğusu isə fraqmenti verir.
        response = client.get(reverse("exams:add_exam_question", kwargs={"slug": exam.slug}), {"modal": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("js-exam-question-form-root", response.content.decode())
        # Detal səhifəsi bayrağı data-atributa yazır.
        response = client.get(
            reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}), {"question_modal": "create"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-question-modal-autoopen-mode="create"', response.content.decode())
