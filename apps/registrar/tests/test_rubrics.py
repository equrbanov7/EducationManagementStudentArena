"""U22 — qiymətləndirmə rubrikaları testləri."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, rubrics, services
from apps.registrar.models import (
    ComponentScore,
    CriterionScore,
    Curriculum,
    CurriculumSubject,
    Program,
    Rubric,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class RubricBaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rb_owner", "rb_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RB Univ",
                slug="rb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="rb-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma", ects=6)
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("rb_teacher", "rb_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("rb_student", "rb_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=cls.record, period=cls.period, semester_number=1)
            cls.enrollment = cls.student.enrollments.get()
            cls.offering = cls.enrollment.offering
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            cls.rubric = rubrics.save_rubric(
                organization=cls.org,
                name="Layihə təqdimatı",
                criteria=[("Məzmun", 4), ("Təqdimat", 3), ("Suallara cavab", 3)],
            )
            components = gradebook.save_components(
                offering=cls.offering,
                definitions=[{"name": "Layihə", "max_score": 10, "rubric_id": str(cls.rubric.id)}],
                by_user=cls.teacher,
            )
            cls.component = components[0]

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


class RubricServiceTest(RubricBaseTest):
    def test_parse_criteria_text(self):
        rows = rubrics.parse_criteria_text("Məzmun:4\nTəqdimat:3, Suallara cavab:3")
        self.assertEqual(rows, [("Məzmun", 4), ("Təqdimat", 3), ("Suallara cavab", 3)])

    def test_parse_rejects_bad_input(self):
        for bad in ("Məzmun", "Ad:abc", "A:0", "A:101", "X:2\nX:3", ""):
            with self.assertRaises(ValueError, msg=f"qəbul edilməməli idi: {bad!r}"):
                rubrics.parse_criteria_text(bad)

    def test_component_has_rubric_attached(self):
        with bypass_rls():
            self.component.refresh_from_db()
        self.assertEqual(self.component.rubric_id, self.rubric.id)

    def test_save_rubric_upsert_preserves_scores_and_drops_removed(self):
        with bypass_rls():
            rubrics.save_criterion_scores(
                component=self.component,
                entries=[
                    {
                        "criterion_id": str(self.rubric.criteria.get(name="Məzmun").id),
                        "enrollment_id": str(self.enrollment.id),
                        "points": "4",
                    }
                ],
                by_user=self.teacher,
            )
            rubrics.save_rubric(
                organization=self.org,
                name="Layihə təqdimatı",
                criteria=[("Məzmun", 5), ("Yeni meyar", 5)],  # Təqdimat/Suallara cavab silinir
                rubric=self.rubric,
            )
            self.rubric.refresh_from_db()
            names = list(self.rubric.criteria.values_list("name", flat=True))
            kept = CriterionScore.objects.filter(criterion__rubric=self.rubric, enrollment=self.enrollment)
        self.assertEqual(set(names), {"Məzmun", "Yeni meyar"})
        self.assertEqual(kept.count(), 1)  # Məzmun balı qorunub

    def test_criterion_scores_roll_up_to_component(self):
        with bypass_rls():
            crits = {c.name: c for c in self.rubric.criteria.all()}
            rubrics.save_criterion_scores(
                component=self.component,
                entries=[
                    {"criterion_id": str(crits["Məzmun"].id), "enrollment_id": str(self.enrollment.id), "points": "4"},
                    {
                        "criterion_id": str(crits["Təqdimat"].id),
                        "enrollment_id": str(self.enrollment.id),
                        "points": "2.5",
                    },
                ],
                by_user=self.teacher,
            )
            score = ComponentScore.objects.get(component=self.component, enrollment=self.enrollment)
        self.assertEqual(score.score, Decimal("6.5"))

    def test_points_clamped_to_criterion_max(self):
        with bypass_rls():
            criterion = self.rubric.criteria.get(name="Təqdimat")  # max 3
            rubrics.save_criterion_scores(
                component=self.component,
                entries=[{"criterion_id": str(criterion.id), "enrollment_id": str(self.enrollment.id), "points": "99"}],
                by_user=self.teacher,
            )
            saved = CriterionScore.objects.get(criterion=criterion, enrollment=self.enrollment)
        self.assertEqual(saved.points, Decimal("3"))

    def test_component_total_clamped_to_component_max(self):
        with bypass_rls():
            # komponent tavanını 5-ə salaq → 4+3+3=10 cəmi 5-ə clamp olunmalıdır
            self.component.max_score = 5
            self.component.save(update_fields=["max_score"])
            entries = [
                {"criterion_id": str(c.id), "enrollment_id": str(self.enrollment.id), "points": str(c.max_points)}
                for c in self.rubric.criteria.all()
            ]
            rubrics.save_criterion_scores(component=self.component, entries=entries, by_user=self.teacher)
            score = ComponentScore.objects.get(component=self.component, enrollment=self.enrollment)
        self.assertEqual(score.score, Decimal("5"))

    def test_grid_shape(self):
        with bypass_rls():
            grid = rubrics.get_rubric_grid(self.component)
        self.assertEqual(len(grid["criteria"]), 3)
        self.assertEqual(len(grid["rows"]), 1)
        self.assertEqual(grid["criteria_max_total"], 10)


class RubricViewTest(RubricBaseTest):
    def test_rubric_grade_page_renders(self):
        resp = self._client(self.teacher).get(
            reverse("registrar:rubric_grade", args=[self.offering.id, self.component.id])
        )
        self.assertEqual(resp.status_code, 200)
        page = resp.content.decode()
        self.assertIn("Layihə təqdimatı", page)
        self.assertIn("rpoints__", page)

    def test_rubric_grade_post_saves(self):
        with bypass_rls():
            criterion = self.rubric.criteria.get(name="Məzmun")
        resp = self._client(self.teacher).post(
            reverse("registrar:rubric_grade", args=[self.offering.id, self.component.id]),
            {f"rpoints__{criterion.id}__{self.enrollment.id}": "3.5"},
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            score = ComponentScore.objects.get(component=self.component, enrollment=self.enrollment)
        self.assertEqual(score.score, Decimal("3.5"))

    def test_student_cannot_open_rubric_page(self):
        resp = self._client(self.student).get(
            reverse("registrar:rubric_grade", args=[self.offering.id, self.component.id])
        )
        self.assertEqual(resp.status_code, 404)

    def test_console_rubric_crud(self):
        client = self._client(self.owner)  # org sahibi registrar idarə edir
        resp = client.post(
            reverse("registrar:rubric_create"),
            {"name": "Esse", "description": "Yazılı işlər", "criteria_text": "Struktur:5\nDil:5"},
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            rubric = Rubric.objects.get(organization=self.org, name="Esse")
            self.assertEqual(rubric.criteria.count(), 2)
        # Pozuq giriş → xəta mesajı, yadda saxlanmır
        resp = client.post(
            reverse("registrar:rubric_create"),
            {"name": "Pozuq", "criteria_text": "meyar-bal-yox"},
        )
        self.assertEqual(resp.status_code, 200)
        with bypass_rls():
            self.assertFalse(Rubric.objects.filter(organization=self.org, name="Pozuq").exists())

    def test_journal_components_tab_shows_rubric_controls(self):
        resp = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        page = resp.content.decode()
        self.assertIn("comp_rubric__0", page)
        self.assertIn(reverse("registrar:rubric_grade", args=[self.offering.id, self.component.id]), page)
