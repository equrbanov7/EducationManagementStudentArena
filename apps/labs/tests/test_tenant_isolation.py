"""
Tenant isolation tests for the Labs app.

Verifies that:
- A user from Organization A cannot access lab objects from Organization B
- A teacher can only act on labs within their own organization scope
- A student cannot access another student's lab submission or answers
- Changing a lab/submission ID in the URL does not allow cross-tenant access
- Anonymous users are redirected to login
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.labs.models import Lab, LabSubmission
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_org(name, slug, owner, *, org_type=OrganizationType.SCHOOL):
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        org = Organization.objects.create(
            name=name,
            slug=slug,
            org_type=org_type,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return org


def _create_role(org, name, *, level=60, permissions=None):
    return Role.objects.create(
        organization=org,
        name=name,
        display_name=name.capitalize(),
        level=level,
        scope_type=RoleScopeType.ORGANIZATION,
        permissions=permissions or [f"{name}.*"],
        is_active=True,
    )


def _assign_user_to_org(user, org, profile_role, role):
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=org,
        defaults={"role": role, "is_primary": True, "is_active": True},
    )


def _login_with_org(client, user, org):
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()


def _make_lab(course, title, owner, *, status="published"):
    now = timezone.now()
    return Lab.objects.create(
        course=course,
        title=title,
        start_datetime=now - timedelta(days=1),
        end_datetime=now + timedelta(days=7),
        max_score=100,
        status=status,
        created_by=owner,
    )


# ---------------------------------------------------------------------------
# Test: Cross-Org Lab Access
# ---------------------------------------------------------------------------


class LabCrossTenantAccessTest(TestCase):
    """
    A user from Org A must not be able to read, edit, delete or submit
    to labs that belong to Org B.
    """

    def setUp(self):
        self.client = Client()

        self.teacher_a = User.objects.create_user(
            username="lt_teacher_a", email="teacher_a@lt-orga.com", password="StrongPass123!"
        )
        self.teacher_b = User.objects.create_user(
            username="lt_teacher_b", email="teacher_b@lt-orgb.com", password="StrongPass123!"
        )
        self.student_a = User.objects.create_user(
            username="lt_student_a", email="student_a@lt-orga.com", password="StrongPass123!"
        )
        self.student_b = User.objects.create_user(
            username="lt_student_b", email="student_b@lt-orgb.com", password="StrongPass123!"
        )

        self.org_a = _create_org("Lab Tenant Org A", "lt-org-a", self.teacher_a)
        self.org_b = _create_org("Lab Tenant Org B", "lt-org-b", self.teacher_b)

        self.role_teacher_a = _create_role(self.org_a, "teacher", level=60, permissions=["course.*"])
        self.role_student_a = _create_role(self.org_a, "student", level=20, permissions=["course.view"])
        self.role_teacher_b = _create_role(self.org_b, "teacher", level=60, permissions=["course.*"])
        self.role_student_b = _create_role(self.org_b, "student", level=20, permissions=["course.view"])

        _assign_user_to_org(self.teacher_a, self.org_a, ProfileRole.TEACHER, self.role_teacher_a)
        _assign_user_to_org(self.student_a, self.org_a, ProfileRole.STUDENT, self.role_student_a)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER, self.role_teacher_b)
        _assign_user_to_org(self.student_b, self.org_b, ProfileRole.STUDENT, self.role_student_b)

        self.course_a = Course.objects.create(
            owner=self.teacher_a, title="LT Course A", status="published", organization=self.org_a
        )
        self.course_b = Course.objects.create(
            owner=self.teacher_b, title="LT Course B", status="published", organization=self.org_b
        )

        self.lab_a = _make_lab(self.course_a, "LT Lab A", self.teacher_a)
        self.lab_b = _make_lab(self.course_b, "LT Lab B", self.teacher_b)

        CourseMembership.objects.create(course=self.course_a, user=self.student_a, role="student")
        self.lab_a.allowed_students.add(self.student_a)

    # ------------------------------------------------------------------
    # Teacher cross-tenant blocked
    # ------------------------------------------------------------------

    def test_teacher_a_cannot_view_org_b_lab_detail(self):
        """Teacher from Org A cannot access the lab detail page of Org B."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:lab_detail", kwargs={"pk": self.lab_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403, 404))

    def test_teacher_a_cannot_edit_org_b_lab(self):
        """Teacher from Org A cannot edit Org B's lab."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:edit_lab", kwargs={"pk": self.lab_b.id})
        response = self.client.post(url, {"title": "Injected Title"})
        self.assertIn(response.status_code, (302, 403, 404))
        self.lab_b.refresh_from_db()
        self.assertEqual(self.lab_b.title, "LT Lab B")

    def test_teacher_a_cannot_delete_org_b_lab(self):
        """Teacher from Org A cannot delete Org B's lab."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:delete_lab", kwargs={"pk": self.lab_b.id})
        response = self.client.post(url)
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertTrue(Lab.objects.filter(id=self.lab_b.id).exists())

    def test_teacher_a_cannot_view_org_b_lab_submissions(self):
        """Teacher from Org A cannot view submission list for Org B's lab."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:lab_submissions", kwargs={"pk": self.lab_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403, 404))

    def test_teacher_a_cannot_publish_org_b_lab(self):
        """Teacher from Org A cannot publish Org B's lab."""
        self.lab_b.status = "draft"
        self.lab_b.save(update_fields=["status"])
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:publish_lab", kwargs={"pk": self.lab_b.id})
        response = self.client.post(url)
        self.assertIn(response.status_code, (302, 403, 404))
        self.lab_b.refresh_from_db()
        self.assertEqual(self.lab_b.status, "draft")

    def test_teacher_a_cannot_manage_blocks_on_org_b_lab(self):
        """Teacher from Org A cannot manage blocks on Org B's lab."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:manage_blocks", kwargs={"pk": self.lab_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403, 404))

    # ------------------------------------------------------------------
    # Student cross-tenant blocked
    # ------------------------------------------------------------------

    def test_student_a_cannot_view_org_b_lab(self):
        """Student from Org A cannot access the lab detail of Org B."""
        _login_with_org(self.client, self.student_a, self.org_a)
        url = reverse("labs:lab_detail", kwargs={"pk": self.lab_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403, 404))

    def test_student_a_cannot_submit_to_org_b_lab(self):
        """Student from Org A cannot submit answers to Org B's lab."""
        _login_with_org(self.client, self.student_a, self.org_a)
        url = reverse("labs:submit_lab", kwargs={"pk": self.lab_b.id})
        response = self.client.post(url, {"answers": "{}"})
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertFalse(LabSubmission.objects.filter(assignment__lab=self.lab_b).exists())

    # ------------------------------------------------------------------
    # Anonymous
    # ------------------------------------------------------------------

    def test_anonymous_cannot_access_lab_detail(self):
        """Anonymous users are redirected to login when accessing a lab."""
        url = reverse("labs:lab_detail", kwargs={"pk": self.lab_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_anonymous_cannot_submit_to_lab(self):
        """Anonymous users cannot submit to a lab."""
        url = reverse("labs:submit_lab", kwargs={"pk": self.lab_a.id})
        response = self.client.post(url, {"answers": "{}"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


# ---------------------------------------------------------------------------
# Test: Lab submission ownership isolation
# ---------------------------------------------------------------------------


class LabSubmissionOwnershipTest(TestCase):
    """
    Within the same organization a student should only see their own
    lab submissions; a teacher from a different org should not be able
    to grade them.
    """

    def setUp(self):
        self.client = Client()

        self.teacher = User.objects.create_user(
            username="lso_teacher", email="lso_teacher@lso.com", password="StrongPass123!"
        )
        self.student_1 = User.objects.create_user(
            username="lso_student_1", email="lso_s1@lso.com", password="StrongPass123!"
        )
        self.student_2 = User.objects.create_user(
            username="lso_student_2", email="lso_s2@lso.com", password="StrongPass123!"
        )
        self.teacher_b = User.objects.create_user(
            username="lso_teacher_b", email="lso_teacher_b@lso.com", password="StrongPass123!"
        )

        self.org = _create_org("LSO Org A", "lso-org-a", self.teacher)
        self.org_b = _create_org("LSO Org B", "lso-org-b", self.teacher_b)

        self.role_teacher = _create_role(self.org, "teacher", level=60, permissions=["course.*"])
        self.role_student = _create_role(self.org, "student", level=20, permissions=["course.view"])
        self.role_teacher_b = _create_role(self.org_b, "teacher", level=60, permissions=["course.*"])

        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, self.role_teacher)
        _assign_user_to_org(self.student_1, self.org, ProfileRole.STUDENT, self.role_student)
        _assign_user_to_org(self.student_2, self.org, ProfileRole.STUDENT, self.role_student)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER, self.role_teacher_b)

        self.course = Course.objects.create(
            owner=self.teacher, title="LSO Course", status="published", organization=self.org
        )
        CourseMembership.objects.create(course=self.course, user=self.student_1, role="student")
        CourseMembership.objects.create(course=self.course, user=self.student_2, role="student")

        self.lab = _make_lab(self.course, "LSO Lab", self.teacher)
        self.lab.allowed_students.add(self.student_1, self.student_2)

    def test_cross_org_teacher_cannot_grade_lab_submission(self):
        """Teacher from Org B cannot grade submissions on Org A's lab."""
        from apps.labs.models import LabAssignment

        assignment = LabAssignment.objects.create(
            lab=self.lab,
            student=self.student_1,
        )
        submission = LabSubmission.objects.create(
            assignment=assignment,
            attempt_number=1,
        )
        _login_with_org(self.client, self.teacher_b, self.org_b)
        url = reverse("labs:grade_submission_page", kwargs={"pk": submission.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403, 404))

    def test_my_lab_answers_only_shows_own_answers(self):
        """my_lab_answers endpoint only returns the requesting student's data."""
        _login_with_org(self.client, self.student_2, self.org)
        url = reverse("labs:my_lab_answers", kwargs={"pk": self.lab.id})
        response = self.client.get(url)
        if response.status_code == 200 and response.context:
            submission = response.context.get("submission")
            if submission:
                self.assertNotEqual(submission.assignment.student_id, self.student_1.id)


# ---------------------------------------------------------------------------
# Test: Cross-Tenant Create, Delete-Submissions, Block CRUD, Grade POST
# ---------------------------------------------------------------------------


class LabCreateBlockGradeCrossTenantTest(TestCase):
    """
    Endpoints that accept a cross-tenant course_id, lab_id, or submission_id
    must reject.  Covers: create_lab via course_id tampering,
    delete_submissions, create_block, and grade_submission_page POST.
    """

    def setUp(self):
        self.client = Client()

        self.teacher_a = User.objects.create_user(
            username="lcg_teacher_a", email="lcg_a@orga.com", password="StrongPass123!"
        )
        self.teacher_b = User.objects.create_user(
            username="lcg_teacher_b", email="lcg_b@orgb.com", password="StrongPass123!"
        )
        self.student_b = User.objects.create_user(
            username="lcg_student_b", email="lcg_sb@orgb.com", password="StrongPass123!"
        )

        self.org_a = _create_org("LCG Org A", "lcg-org-a", self.teacher_a)
        self.org_b = _create_org("LCG Org B", "lcg-org-b", self.teacher_b)

        self.role_teacher_a = _create_role(self.org_a, "teacher", level=60, permissions=["course.*", "grade.*"])
        self.role_teacher_b = _create_role(self.org_b, "teacher", level=60, permissions=["course.*", "grade.*"])
        self.role_student_b = _create_role(self.org_b, "student", level=20, permissions=["course.view"])

        _assign_user_to_org(self.teacher_a, self.org_a, ProfileRole.TEACHER, self.role_teacher_a)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER, self.role_teacher_b)
        _assign_user_to_org(self.student_b, self.org_b, ProfileRole.STUDENT, self.role_student_b)

        self.course_a = Course.objects.create(
            owner=self.teacher_a, title="LCG Course A", status="published", organization=self.org_a
        )
        self.course_b = Course.objects.create(
            owner=self.teacher_b, title="LCG Course B", status="published", organization=self.org_b
        )

        self.lab_b = _make_lab(self.course_b, "LCG Lab B", self.teacher_b)

        CourseMembership.objects.create(course=self.course_b, user=self.student_b, role="student")
        self.lab_b.allowed_students.add(self.student_b)

    # -- Create via cross-tenant course_id ------------------------------------

    def test_create_lab_with_cross_tenant_course_id_blocked(self):
        """Teacher A cannot create a lab under Org B's course."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:create_lab", kwargs={"course_id": self.course_b.id})
        response = self.client.post(
            url,
            {
                "title": "Injected Lab",
                "start_datetime": "2025-01-01 00:00",
                "end_datetime": "2025-12-31 23:59",
                "max_score": 100,
            },
        )
        self.assertIn(response.status_code, (403, 404))

    # -- Delete submissions cross-tenant --------------------------------------

    def test_delete_submissions_cross_tenant_blocked(self):
        """Teacher A cannot delete submissions on Org B's lab."""
        from apps.labs.models import LabAssignment

        assignment_b = LabAssignment.objects.create(lab=self.lab_b, student=self.student_b)
        sub = LabSubmission.objects.create(assignment=assignment_b, attempt_number=1)

        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:delete_submissions", kwargs={"pk": self.lab_b.id})
        response = self.client.post(url, {"submission_ids": [sub.id]})
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertTrue(LabSubmission.objects.filter(id=sub.id).exists())

    # -- Create block cross-tenant --------------------------------------------

    def test_create_block_cross_tenant_blocked(self):
        """Teacher A cannot create a block on Org B's lab."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:create_block", kwargs={"pk": self.lab_b.id})
        response = self.client.post(url, {"title": "Injected Block"})
        self.assertIn(response.status_code, (403, 404))

    # -- Grade submission page POST cross-tenant ------------------------------

    def test_grade_submission_post_cross_tenant_blocked(self):
        """Teacher A cannot grade (POST) a submission from Org B's lab."""
        from apps.labs.models import LabAssignment

        assignment_b = LabAssignment.objects.create(lab=self.lab_b, student=self.student_b)
        sub = LabSubmission.objects.create(assignment=assignment_b, attempt_number=1)

        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:grade_submission_page", kwargs={"pk": sub.id})
        response = self.client.post(url, {"score": "90", "feedback": "Nice"})
        self.assertIn(response.status_code, (302, 403, 404))
        sub.refresh_from_db()
        self.assertIsNone(sub.score)


# ---------------------------------------------------------------------------
# Test: Cross-Tenant Lab Question CRUD & API
# ---------------------------------------------------------------------------


class LabQuestionCrossTenantTest(TestCase):
    """
    create_question, edit_question, delete_question accept a block_id or
    question pk.  Swapping these for cross-tenant IDs must be blocked.
    Also covers api_get_students with a cross-tenant course_id.
    """

    def setUp(self):
        self.client = Client()

        self.teacher_a = User.objects.create_user(
            username="lqct_teacher_a", email="lqct_a@orga.com", password="StrongPass123!"
        )
        self.teacher_b = User.objects.create_user(
            username="lqct_teacher_b", email="lqct_b@orgb.com", password="StrongPass123!"
        )

        self.org_a = _create_org("LQCT Org A", "lqct-org-a", self.teacher_a)
        self.org_b = _create_org("LQCT Org B", "lqct-org-b", self.teacher_b)

        self.role_teacher_a = _create_role(self.org_a, "teacher", level=60, permissions=["course.*"])
        self.role_teacher_b = _create_role(self.org_b, "teacher", level=60, permissions=["course.*"])

        _assign_user_to_org(self.teacher_a, self.org_a, ProfileRole.TEACHER, self.role_teacher_a)
        _assign_user_to_org(self.teacher_b, self.org_b, ProfileRole.TEACHER, self.role_teacher_b)

        self.course_b = Course.objects.create(
            owner=self.teacher_b, title="LQCT Course B", status="published", organization=self.org_b
        )
        self.lab_b = _make_lab(self.course_b, "LQCT Lab B", self.teacher_b)

        from apps.labs.models import LabBlock

        self.block_b = LabBlock.objects.create(lab=self.lab_b, title="Block B", order=1)

        from apps.labs.models import LabQuestion

        self.question_b = LabQuestion.objects.create(
            block=self.block_b, question_text="Q?", question_number=1, points=10
        )

    # -- create_question ------------------------------------------------------

    def test_create_question_cross_tenant_blocked(self):
        """Teacher A cannot create a question on Org B's lab block."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:create_question", kwargs={"block_id": self.block_b.id})
        response = self.client.post(url, {"question_text": "Injected Q", "points": 5})
        self.assertIn(response.status_code, (403, 404))

    # -- edit_question --------------------------------------------------------

    def test_edit_question_cross_tenant_blocked(self):
        """Teacher A cannot edit a question belonging to Org B's lab."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:edit_question", kwargs={"pk": self.question_b.id})
        response = self.client.post(url, {"question_text": "Hacked Q", "points": 99})
        self.assertIn(response.status_code, (403, 404))
        self.question_b.refresh_from_db()
        self.assertEqual(self.question_b.question_text, "Q?")

    def test_edit_question_get_cross_tenant_blocked(self):
        """Teacher A cannot retrieve (GET) question data from Org B's lab."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:edit_question", kwargs={"pk": self.question_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (403, 404))

    # -- delete_question ------------------------------------------------------

    def test_delete_question_cross_tenant_blocked(self):
        """Teacher A cannot delete a question belonging to Org B's lab."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:delete_question", kwargs={"pk": self.question_b.id})
        response = self.client.post(url)
        self.assertIn(response.status_code, (403, 404))

        from apps.labs.models import LabQuestion

        self.assertTrue(LabQuestion.objects.filter(id=self.question_b.id).exists())

    # -- api_get_students cross-tenant course_id ------------------------------

    def test_api_get_students_cross_tenant_blocked(self):
        """Teacher A cannot list students for Org B's course via the labs API."""
        _login_with_org(self.client, self.teacher_a, self.org_a)
        url = reverse("labs:api_get_students", kwargs={"course_id": self.course_b.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, (403, 404))
