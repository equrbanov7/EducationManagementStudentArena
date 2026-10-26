"""«Dəyərləndirilmiş nəticələr» — imtahan mərkəzi org-un bütün midterm/final nəticələrini görür (sahib 2026-10-26).

Sahib: «dəyərləndirilmiş nəticələrdə imtahan mərkəzi işçisi və s. o da görsün». Qayda «İmtahanlarım» ilə eynidir
(``manageable_exams_q``): mərkəz üzvü başqasının yaratdığı midterm/final nəticəsini görür, quiz-i yox; müəllimin
öz görünüşü dəyişmir; qrup süzgəci (reyestr qrupu) mərkəz sətirlərində də işləyir; sətirdə «Yaradan».
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.accounts.tests.test_review_queue_query_budget import _assign, _build_teacher_world
from apps.accounts.tests.test_review_results_redesign import _check_written

User = get_user_model()
FRAGMENT = "accounts:profile_section_fragment"


class ReviewResultsCenterScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.world = _build_teacher_world("rcs26", 3)
        cls.org = cls.world["org"]
        cls.midterm = cls.world["exams"]["test"]
        cls.midterm.exam_type_extended = "midterm"
        cls.midterm.save(update_fields=["exam_type_extended"])
        cls.quiz = cls.world["exams"]["written"]
        cls.quiz.exam_type_extended = "quiz"
        cls.quiz.save(update_fields=["exam_type_extended"])
        _check_written(cls.world)
        cls.center_staff = User.objects.create_user("rcs26_center", "rcs26_center@example.com", "pw")
        _assign(cls.center_staff, cls.org, ProfileRole.MEMBER, "exam_center_staff")
        cls.other_teacher = User.objects.create_user("rcs26_t2", "rcs26_t2@example.com", "pw")
        _assign(cls.other_teacher, cls.org, ProfileRole.TEACHER, "teacher")

    def _items(self, user, **params):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        url = reverse(FRAGMENT, kwargs={"section": "review-results"})
        response = self.client.get(url, params, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        return response, list(response.context["evaluated_review_page_obj"].paginator.object_list)

    def test_center_staff_sees_other_creators_midterm_but_not_quiz(self):
        response, items = self._items(self.center_staff)
        self.assertEqual({item["title"] for item in items}, {self.midterm.title})
        self.assertEqual(len(items), 3)
        teacher_name = self.world["teacher"].get_full_name() or self.world["teacher"].username
        self.assertTrue(all(item["creator_display"] == teacher_name for item in items))
        self.assertIn("Yaradan", response.json()["html"])

    def test_teacher_view_is_unchanged(self):
        _, own = self._items(self.world["teacher"])
        self.assertEqual({item["title"] for item in own}, {self.midterm.title, self.quiz.title})
        self.assertTrue(all(item.get("creator_display", "") == "" for item in own))
        _, other = self._items(self.other_teacher)
        self.assertEqual(other, [])

    def test_group_filter_works_for_center_rows(self):
        students = self.world["students"]
        names = {students[0].pk: "RCS G1", students[1].pk: "RCS G2", students[2].pk: "RCS G1"}
        with mock.patch("apps.registrar.student_group_names.current_group_names", return_value=names):
            response, items = self._items(self.center_staff, evaluated_group="RCS G1")
        self.assertEqual(len(items), 2)
        self.assertEqual({item["group_name"] for item in items}, {"RCS G1"})
        self.assertIn("RCS G2", response.context["evaluated_review_available_groups"])
