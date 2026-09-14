"""W4 `w4wizard` (2026-09-14): imtahan sehrbazı — reyestr qrupu təyinatı (R2),
addım-hədəfli validasiya (R1), «Aktiv et» yönləndirməsi (R4), dublikat (R6).

R2: «İcazəli qruplar» seçicisi yalnız köhnə kohortları (`exams.StudentGroup`)
tanıyırdı; real akademik qruplar («634 ing», `OrgUnit` GROUP) təyin oluna
bilmirdi. İndi `Exam.allowed_units` + tələbənin cari aktiv
`StudentAcademicRecord.group`-u ilə üzvlük — giriş siyasəti, tələbə siyahıları,
kabinet sorğusu, PIN provizionu, bildiriş alıcıları, dublikat eyni qapıdan keçir.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.accounts.queries.assignments import get_assigned_exams_for_user
from apps.exams.models import Exam, ExamStudentPin
from apps.exams.services.duplication import duplicate_exam
from apps.exams.services.student_list_batch import StudentExamListBatch
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.notifications.public import get_exam_assigned_user_ids
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _login(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


class _UnitFixture(TestCase):
    """İki tenant: A (faktültə → iki qrup) və B (bir qrup); A-da müəllim, dekan, tələbələr."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("w4u_owner", "w4u_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="W4U Uni", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active", is_active=True
        )
        cls.owner_b = User.objects.create_user("w4u_owner_b", "w4u_owner_b@test.az", PASSWORD)
        cls.org_b = Organization.objects.create(
            name="W4U Uni B", org_type=OrganizationType.UNIVERSITY, owner=cls.owner_b, status="active", is_active=True
        )
        cls.teacher = User.objects.create_user("w4u_teacher", "w4u_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.student = User.objects.create_user("w4u_student", "w4u_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.student_other_group = User.objects.create_user("w4u_student2", "w4u_student2@test.az", PASSWORD)
        _assign_user_to_org(cls.student_other_group, cls.org, ProfileRole.STUDENT, "student")
        cls.student_expelled = User.objects.create_user("w4u_student3", "w4u_student3@test.az", PASSWORD)
        _assign_user_to_org(cls.student_expelled, cls.org, ProfileRole.STUDENT, "student")
        cls.student_b = User.objects.create_user("w4u_student_b", "w4u_student_b@test.az", PASSWORD)
        _assign_user_to_org(cls.student_b, cls.org_b, ProfileRole.STUDENT, "student")

        with bypass_rls():
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Dizayn", slug="w4u-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.faculty_other = OrgUnit.objects.create(
                organization=cls.org, name="Biznes", slug="w4u-fac2", unit_type=OrgUnitType.FACULTY
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, parent=cls.faculty, name="634 ing", slug="w4u-634", unit_type=OrgUnitType.GROUP
            )
            cls.group_other = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty_other,
                name="701 biz",
                slug="w4u-701",
                unit_type=OrgUnitType.GROUP,
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org_b, name="B-1", slug="w4u-b1", unit_type=OrgUnitType.GROUP
            )
            program = Program.objects.create(organization=cls.org, code="DZ", name="Dizayn", absence_limit_percent=25)
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2024)
            program_b = Program.objects.create(organization=cls.org_b, code="BB", name="B", absence_limit_percent=25)
            curriculum_b = Curriculum.objects.create(organization=cls.org_b, program=program_b, admission_year=2024)

            def record(student, org, unit, prog, curr, **extra):
                return StudentAcademicRecord.objects.create(
                    organization=org,
                    student=student,
                    program=prog,
                    curriculum=curr,
                    group=unit,
                    admission_year=2024,
                    **extra,
                )

            record(cls.student, cls.org, cls.group, program, curriculum)
            record(cls.student_other_group, cls.org, cls.group_other, program, curriculum)
            record(cls.student_expelled, cls.org, cls.group, program, curriculum, status="expelled")
            record(cls.student_b, cls.org_b, cls.group_b, program_b, curriculum_b)

    def _exam(self, **kwargs):
        defaults = {
            "title": "W4U Exam",
            "author": self.teacher,
            "organization": self.org,
            "exam_type": "test",
            "exam_type_extended": "quiz",
            "is_active": True,
            "is_public": False,
            "start_datetime": timezone.now() - timedelta(hours=1),
            "end_datetime": timezone.now() + timedelta(days=2),
        }
        defaults.update(kwargs)
        return Exam.objects.create(**defaults)


class AccessPolicyUnitTests(_UnitFixture):
    def test_student_in_allowed_unit_can_see_and_start(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        self.assertTrue(exam.can_user_see(self.student))
        ok, reason = exam.can_user_start(self.student)
        self.assertTrue(ok, reason)

    def test_student_of_other_group_or_expelled_or_other_tenant_is_denied(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        for user in (self.student_other_group, self.student_expelled, self.student_b):
            with self.subTest(user=user.username):
                self.assertFalse(exam.can_user_see(user))
                ok, _ = exam.can_user_start(user)
                self.assertFalse(ok)

    def test_inactive_record_does_not_grant_access(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        with bypass_rls():
            StudentAcademicRecord.objects.filter(student=self.student).update(is_active=False)
        self.assertFalse(exam.can_user_see(self.student))

    def test_service_can_user_access_exam_mirrors_units(self):
        from apps.exams.services.access_policy import can_user_access_exam

        exam = self._exam()
        exam.allowed_units.add(self.group)
        self.assertTrue(can_user_access_exam(exam, self.student))
        self.assertFalse(can_user_access_exam(exam, self.student_other_group))


class AssignedListsUnitTests(_UnitFixture):
    def test_accounts_assigned_query_includes_unit_exam(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        self.assertIn(exam, list(get_assigned_exams_for_user(self.student, include_public=False)))
        self.assertNotIn(exam, list(get_assigned_exams_for_user(self.student_other_group, include_public=False)))

    def test_assigned_student_exam_list_view_includes_unit_exam(self):
        exam = self._exam(title="W4U Unit Assigned")
        exam.allowed_units.add(self.group)
        client = _login(self.student, self.org)
        response = client.get(reverse("exams:assigned_exam_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "W4U Unit Assigned")
        response = _login(self.student_other_group, self.org).get(reverse("exams:assigned_exam_list"))
        self.assertNotContains(response, "W4U Unit Assigned")

    def test_batch_group_ids_include_units_with_constant_query_count(self):
        exams = [self._exam(title=f"W4U {i}") for i in range(3)]
        for exam in exams:
            exam.allowed_units.add(self.group)
        with CaptureQueriesContext(connection) as one:
            batch = StudentExamListBatch(exams[:1], self.student)
        with CaptureQueriesContext(connection) as three:
            batch3 = StudentExamListBatch(exams, self.student)
        self.assertEqual(len(one), len(three))
        self.assertEqual(batch._group_ids, {exams[0].id})
        self.assertEqual(batch3._group_ids, {e.id for e in exams})


class RecipientsAndPinsUnitTests(_UnitFixture):
    def test_assigned_user_ids_include_unit_students_only_enrolled(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        ids = get_exam_assigned_user_ids(exam)
        self.assertIn(self.student.id, ids)
        self.assertNotIn(self.student_expelled.id, ids)
        self.assertNotIn(self.student_other_group.id, ids)

    def test_final_exam_pins_provisioned_for_unit_students(self):
        exam = self._exam(exam_type_extended="final")
        exam.allowed_units.add(self.group)  # m2m_changed → provision_exam_student_pins
        self.assertTrue(ExamStudentPin.objects.filter(exam=exam, student=self.student).exists())
        self.assertFalse(ExamStudentPin.objects.filter(exam=exam, student=self.student_expelled).exists())

    def test_duplicate_copies_allowed_units(self):
        exam = self._exam()
        exam.allowed_units.add(self.group)
        copy = duplicate_exam(exam=exam, user=self.teacher)
        self.assertEqual(list(copy.allowed_units.values_list("pk", flat=True)), [self.group.pk])


class WizardViewUnitTests(_UnitFixture):
    def _payload(self, **extra):
        start = timezone.localtime() + timedelta(days=1)
        payload = {
            "modal": "1",
            "title": "W4U Wizard Exam",
            "description": "",
            "exam_type": "test",
            "exam_type_extended": "quiz",
            "random_question_count": "10",
            "start_datetime": start.strftime("%Y-%m-%dT%H:%M"),
            "end_datetime": (start + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
            "total_duration_minutes": "60",
        }
        payload.update(extra)
        return payload

    def _post(self, client, **extra):
        return client.post(
            reverse("exams:create_exam") + "?modal=1",
            self._payload(**extra),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_create_with_registry_group_assigns_unit(self):
        client = _login(self.teacher, self.org)
        response = self._post(client, allowed_units=[str(self.group.pk)])
        self.assertEqual(response.status_code, 200, response.content[:300])
        exam = Exam.objects.get(title="W4U Wizard Exam")
        self.assertEqual(list(exam.allowed_units.values_list("pk", flat=True)), [self.group.pk])
        self.assertTrue(exam.can_user_see(self.student) or not exam.is_active)

    def test_unit_of_other_tenant_is_rejected_with_step_and_field(self):
        client = _login(self.teacher, self.org)
        response = self._post(client, allowed_units=[str(self.group_b.pk)])
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["step"], 2)
        self.assertEqual(payload["field"], "allowed_units")
        self.assertIn('data-ew-error-step="2"', payload["html"])
        self.assertFalse(Exam.objects.filter(title="W4U Wizard Exam").exists())

    def test_garbage_unit_id_is_rejected(self):
        client = _login(self.teacher, self.org)
        response = self._post(client, allowed_units=["not-a-uuid"])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Exam.objects.filter(title="W4U Wizard Exam").exists())

    def test_end_before_start_targets_timing_step(self):
        client = _login(self.teacher, self.org)
        start = timezone.localtime() + timedelta(days=1)
        response = self._post(
            client,
            start_datetime=start.strftime("%Y-%m-%dT%H:%M"),
            end_datetime=(start - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["step"], 1)
        self.assertEqual(payload["field"], "end_datetime")
        self.assertIn('data-ew-error-field="end_datetime"', payload["html"])

    def test_edit_form_renders_selected_units_and_hides_legacy_block_without_cohorts(self):
        exam = self._exam(is_active=False)
        exam.allowed_units.add(self.group)
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f'<option value="{self.group.pk}" selected>634 ing — Dizayn</option>', html)
        self.assertIn('name="allowed_units"', html)
        self.assertNotIn('name="allowed_groups"', html)

    def test_group_search_units_kind_scoped_to_org(self):
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:group_search") + "?kind=units&q=")
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertEqual(ids, {str(self.group.pk), str(self.group_other.pk)})
        response = client.get(reverse("exams:group_search") + "?kind=units&q=634")
        self.assertEqual([row["text"] for row in response.json()["results"]], ["634 ing — Dizayn"])

    def test_group_search_units_respects_unit_scope_of_dean(self):
        dean = User.objects.create_user("w4u_dean", "w4u_dean@test.az", PASSWORD)
        _assign_user_to_org(dean, self.org, ProfileRole.TEACHER, "dean")
        Membership.objects.filter(user=dean, organization=self.org).update(scope_unit=self.faculty)
        role = self.org.roles.get(name="dean")
        if "exam.create" not in (role.permissions or []) and "exam.*" not in (role.permissions or []):
            role.permissions = list(role.permissions or []) + ["exam.create"]
            role.save(update_fields=["permissions"])
        client = _login(dean, self.org)
        response = client.get(reverse("exams:group_search") + "?kind=units")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.json()["results"]}, {str(self.group.pk)})
        # Əhatədən kənar qrup POST-da da rədd edilir.
        response = self._post(client, allowed_units=[str(self.group_other.pk)])
        self.assertEqual(response.status_code, 400)

    def test_assigned_student_count_counts_unit_students(self):
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:assigned_student_count") + f"?units={self.group.pk}")
        self.assertEqual(response.json()["total"], 1)  # xaric olunmuş tələbə sayılmır
        response = client.get(
            reverse("exams:assigned_student_count") + f"?units={self.group.pk}&excluded={self.student.id}"
        )
        self.assertEqual(response.json()["total"], 0)

    def test_user_search_marks_unit_members(self):
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:user_search") + f"?units={self.group.pk}&limit=50")
        rows = {row["id"]: row["group_member"] for row in response.json()["results"]}
        self.assertTrue(rows.get(str(self.student.id)))
        self.assertFalse(rows.get(str(self.student_other_group.id)))


class ActivateRedirectTests(_UnitFixture):
    def test_toggle_active_keeps_navigation_query(self):
        exam = self._exam(is_active=False)
        client = _login(self.teacher, self.org)
        url = reverse("exams:toggle_exam_active", kwargs={"slug": exam.slug})
        query = "from_section=my-exams&return_to=%2Faccounts%2Fprofile%2F%3Fsection%3Dmy-exams"
        response = client.post(f"{url}?{query}", {"desired_state": "1"})
        self.assertEqual(response.status_code, 302)
        expected = reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})
        self.assertTrue(response["Location"].startswith(expected + "?"), response["Location"])
        self.assertIn("from_section=my-exams", response["Location"])
        self.assertIn("return_to=", response["Location"])


class DuplicateToastAndDetailTests(_UnitFixture):
    def test_duplicate_view_warns_that_questions_are_not_copied(self):
        from apps.exams.models import ExamQuestion

        exam = self._exam(is_active=False)
        ExamQuestion.objects.create(exam=exam, order=1, text="Q1", points=1)
        client = _login(self.teacher, self.org)
        response = client.post(reverse("exams:duplicate_exam", kwargs={"slug": exam.slug}), follow=True)
        self.assertEqual(response.status_code, 200)
        texts = [str(m) for m in response.context["messages"]]
        levels = [m.level_tag for m in response.context["messages"]]
        self.assertEqual(len(texts), 2, texts)
        self.assertEqual(levels, ["success", "warning"])
        # `{count}` yalnız kataloq doldurulandan sonra mətndədir; açar özü formatlana bilməlidir.
        self.assertTrue(texts[1])

    def test_duplicate_view_warns_when_source_is_empty(self):
        exam = self._exam(is_active=False)
        client = _login(self.teacher, self.org)
        response = client.post(reverse("exams:duplicate_exam", kwargs={"slug": exam.slug}), follow=True)
        levels = [m.level_tag for m in response.context["messages"]]
        self.assertEqual(levels, ["success", "warning"])

    def test_detail_page_lists_registry_groups(self):
        exam = self._exam(is_active=False)
        exam.allowed_units.add(self.group, self.group_other)
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "634 ing, 701 biz")
