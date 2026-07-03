"""
Seed a deterministic multi-role E2E scenario used by Playwright tests.

The command is intentionally idempotent so CI can run it on every build
without creating duplicate users, organizations, assignments, or exams.
"""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.organizations.default_roles import get_default_roles_for_org_type
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic
from core.roles import ProfileRole

User = get_user_model()


class Command(BaseCommand):
    help = "Seed a deterministic multi-role E2E scenario for Playwright role and regression tests."

    ACTIVE_ORG_NAME = "CI Role Matrix University"
    ACTIVE_ORG_SLUG = "ci-role-matrix-university"
    ISOLATED_ORG_NAME = "CI Isolated University"
    ISOLATED_ORG_SLUG = "ci-isolated-university"
    PENDING_ORG_NAME = "CI Pending University"
    PENDING_ORG_SLUG = "ci-pending-university"

    COURSE_TITLE = "CI Role Matrix Course"
    COURSE_SLUG = "ci-role-matrix-course"
    ASSIGNMENT_TITLE = "CI Assignment"
    GROUP_NAME = "CI Group A"
    EXAM_TITLE = "CI Exam"
    EXAM_SLUG = "ci-role-matrix-exam"
    RESUME_EXAM_TITLE = "CI Resume Exam"
    RESUME_EXAM_SLUG = "ci-resume-exam"
    ISOLATED_EXAM_TITLE = "CI Isolated Exam"
    ISOLATED_EXAM_SLUG = "ci-isolated-exam"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            help="Shared password applied to every seeded role user.",
        )
        parser.add_argument("--owner-username", default="ci_owner_e2e")
        parser.add_argument("--admin-username", default="ci_admin_e2e")
        parser.add_argument("--teacher-username", default="ci_teacher_e2e")
        parser.add_argument("--staff-username", default="ci_staff_e2e")
        parser.add_argument("--student-username", default="ci_student_e2e")
        parser.add_argument("--late-student-username", default="ci_late_student_e2e")
        parser.add_argument("--resume-student-username", default="ci_resume_student_e2e")
        parser.add_argument("--pending-owner-username", default="ci_pending_owner_e2e")
        parser.add_argument("--isolated-owner-username", default="ci_isolated_owner_e2e")
        parser.add_argument("--org-slug", default=self.ACTIVE_ORG_SLUG)
        parser.add_argument("--isolated-org-slug", default=self.ISOLATED_ORG_SLUG)
        parser.add_argument("--pending-org-slug", default=self.PENDING_ORG_SLUG)

    def _require_password(self, options):
        password = (options.get("password") or "").strip()
        if not password:
            raise CommandError("--password is required so the scenario credentials are explicit.")
        return password

    def _ensure_roles(self, organization):
        roles = {}
        for role_template in get_default_roles_for_org_type(OrganizationType.UNIVERSITY):
            role, _ = Role.objects.update_or_create(
                organization=organization,
                name=role_template["name"],
                defaults={
                    "display_name": role_template["display_name"],
                    "description": role_template.get("description", ""),
                    "level": role_template["level"],
                    "scope_type": role_template["scope_type"],
                    "permissions": role_template["permissions"],
                    "is_system": True,
                    "is_active": True,
                },
            )
            roles[role.name] = role
        return roles

    def _ensure_user(self, *, username, password, email, first_name, last_name):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_password(password)
        user.save()
        return user

    def _configure_profile(
        self,
        *,
        user,
        organization,
        profile_role,
        requested_organization=None,
    ):
        profile = user.profile
        profile.organization = organization
        profile.requested_organization = requested_organization
        profile.requested_organization_name = requested_organization.name if requested_organization else ""
        profile.organization_type = OrganizationType.UNIVERSITY
        profile.country = "Azerbaijan"
        profile.role = profile_role
        if profile_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
            profile.student_university_name = organization.name if organization else ""
        profile.save()
        return profile

    def _ensure_membership(self, *, user, organization, role, assigned_by, primary=True):
        membership, _ = Membership.objects.update_or_create(
            user=user,
            organization=organization,
            role=role,
            scope_unit=None,
            defaults={
                "title": role.display_name,
                "assigned_by": assigned_by,
                "is_active": True,
                "is_primary": primary,
            },
        )
        return membership

    def _ensure_course_membership(self, *, course, user, role, group_name=""):
        CourseMembership = django_apps.get_model("courses", "CourseMembership")
        membership, _ = CourseMembership.objects.update_or_create(
            course=course,
            user=user,
            defaults={
                "role": role,
                "group_name": group_name,
            },
        )
        return membership

    def _ensure_active_org(self, *, owner, org_slug):
        organization, _ = Organization.objects.update_or_create(
            slug=org_slug,
            defaults={
                "name": self.ACTIVE_ORG_NAME,
                "org_type": OrganizationType.UNIVERSITY,
                "owner": owner,
                "description": "Deterministic role-based E2E scenario.",
                "country": "Azerbaijan",
                "organization_identifier": "CI-ROLE-UNI",
                "email": "ci-role@example.com",
                "phone": "+994000000001",
                "address": "CI Role Matrix Campus",
                "website": "https://emsarena.local/ci-role-matrix",
                "is_active": True,
                "status": "active",
            },
        )
        return organization

    def _ensure_isolated_org(self, *, owner, org_slug):
        organization, _ = Organization.objects.update_or_create(
            slug=org_slug,
            defaults={
                "name": self.ISOLATED_ORG_NAME,
                "org_type": OrganizationType.UNIVERSITY,
                "owner": owner,
                "description": "Secondary tenant for isolation checks.",
                "country": "Azerbaijan",
                "organization_identifier": "CI-ISOLATED-UNI",
                "email": "ci-isolated@example.com",
                "phone": "+994000000002",
                "address": "CI Isolated Campus",
                "website": "https://emsarena.local/ci-isolated",
                "is_active": True,
                "status": "active",
            },
        )
        return organization

    def _ensure_pending_org(self, *, owner, org_slug):
        organization, _ = Organization.objects.update_or_create(
            slug=org_slug,
            defaults={
                "name": self.PENDING_ORG_NAME,
                "org_type": OrganizationType.UNIVERSITY,
                "owner": owner,
                "description": "Pending approval tenant used for regression checks.",
                "country": "Azerbaijan",
                "organization_identifier": "CI-PENDING-UNI",
                "email": "ci-pending@example.com",
                "phone": "+994000000003",
                "address": "CI Pending Campus",
                "website": "https://emsarena.local/ci-pending",
                "is_active": True,
                "status": "pending",
            },
        )
        return organization

    def _ensure_exam_question(self, *, exam, text):
        ExamQuestion = django_apps.get_model("exams", "ExamQuestion")
        ExamQuestionOption = django_apps.get_model("exams", "ExamQuestionOption")
        question, _ = ExamQuestion.objects.update_or_create(
            exam=exam,
            order=1,
            defaults={
                "text": text,
                "answer_mode": "single",
                "points": 1,
                "is_active": True,
            },
        )

        if question.options.count() < 2:
            question.options.all().delete()
            ExamQuestionOption.objects.create(question=question, text="Teacher", is_correct=True)
            ExamQuestionOption.objects.create(question=question, text="Student", is_correct=False)
        else:
            options = list(question.options.order_by("id")[:2])
            options[0].text = "Teacher"
            options[0].is_correct = True
            options[0].save(update_fields=["text", "is_correct"])
            options[1].text = "Student"
            options[1].is_correct = False
            options[1].save(update_fields=["text", "is_correct"])

        return question

    @transaction.atomic
    @rls_worker_atomic()
    @bypass_rls()
    def handle(self, *args, **options):
        # M2 (2026-07-02): cross-app modellər lazy — organizations→courses/exams/
        # assignments import kənarlarını kəsir (AGENTS §5, pattern 2).
        Course = django_apps.get_model("courses", "Course")
        StudentGroup = django_apps.get_model("exams", "StudentGroup")
        Assignment = django_apps.get_model("assignments", "Assignment")
        Exam = django_apps.get_model("exams", "Exam")
        ExamAttempt = django_apps.get_model("exams", "ExamAttempt")
        ExamAnswer = django_apps.get_model("exams", "ExamAnswer")
        password = self._require_password(options)

        owner = self._ensure_user(
            username=options["owner_username"],
            password=password,
            email="ci-owner-e2e@emsarena.local",
            first_name="CI",
            last_name="Owner",
        )
        org = self._ensure_active_org(owner=owner, org_slug=options["org_slug"])
        roles = self._ensure_roles(org)
        self._configure_profile(user=owner, organization=org, profile_role=ProfileRole.ORG_OWNER)
        self._ensure_membership(user=owner, organization=org, role=roles["rector"], assigned_by=owner, primary=True)

        admin = self._ensure_user(
            username=options["admin_username"],
            password=password,
            email="ci-admin-e2e@emsarena.local",
            first_name="CI",
            last_name="Admin",
        )
        self._configure_profile(user=admin, organization=org, profile_role=ProfileRole.ORG_ADMIN)
        self._ensure_membership(
            user=admin,
            organization=org,
            role=roles["vice_rector"],
            assigned_by=owner,
            primary=True,
        )

        teacher = self._ensure_user(
            username=options["teacher_username"],
            password=password,
            email="ci-teacher-e2e@emsarena.local",
            first_name="CI",
            last_name="Teacher",
        )
        self._configure_profile(user=teacher, organization=org, profile_role=ProfileRole.TEACHER)
        self._ensure_membership(user=teacher, organization=org, role=roles["teacher"], assigned_by=owner, primary=True)

        staff = self._ensure_user(
            username=options["staff_username"],
            password=password,
            email="ci-staff-e2e@emsarena.local",
            first_name="CI",
            last_name="Staff",
        )
        self._configure_profile(user=staff, organization=org, profile_role=ProfileRole.MEMBER)
        self._ensure_membership(user=staff, organization=org, role=roles["member"], assigned_by=owner, primary=True)

        student = self._ensure_user(
            username=options["student_username"],
            password=password,
            email="ci-student-e2e@emsarena.local",
            first_name="CI",
            last_name="Student",
        )
        self._configure_profile(user=student, organization=org, profile_role=ProfileRole.STUDENT)
        self._ensure_membership(user=student, organization=org, role=roles["student"], assigned_by=owner, primary=True)

        late_student = self._ensure_user(
            username=options["late_student_username"],
            password=password,
            email="ci-late-student-e2e@emsarena.local",
            first_name="CI",
            last_name="LateStudent",
        )
        self._configure_profile(user=late_student, organization=org, profile_role=ProfileRole.STUDENT)
        self._ensure_membership(
            user=late_student,
            organization=org,
            role=roles["student"],
            assigned_by=owner,
            primary=True,
        )

        resume_student = self._ensure_user(
            username=options["resume_student_username"],
            password=password,
            email="ci-resume-student-e2e@emsarena.local",
            first_name="CI",
            last_name="ResumeStudent",
        )
        self._configure_profile(user=resume_student, organization=org, profile_role=ProfileRole.STUDENT)
        self._ensure_membership(
            user=resume_student,
            organization=org,
            role=roles["student"],
            assigned_by=owner,
            primary=True,
        )

        course, _ = Course.objects.update_or_create(
            slug=self.COURSE_SLUG,
            defaults={
                "owner": teacher,
                "title": self.COURSE_TITLE,
                "description": "Seeded role-based Playwright course.",
                "organization": org,
                "status": "published",
            },
        )
        self._ensure_course_membership(course=course, user=teacher, role="teacher")

        group, _ = StudentGroup.objects.get_or_create(
            organization=org,
            teacher=teacher,
            name=self.GROUP_NAME,
        )
        group.teachers.add(teacher)
        if not group.students.filter(id=student.id).exists():
            group.students.add(student)

        self._ensure_course_membership(
            course=course,
            user=student,
            role="student",
            group_name=group.name,
        )

        now = timezone.now()
        assignment, _ = Assignment.objects.update_or_create(
            course=course,
            title=self.ASSIGNMENT_TITLE,
            defaults={
                "created_by": teacher,
                "description": "Seeded assignment for the E2E scenario.",
                "start_date": now - timedelta(days=1),
                "due_date": now + timedelta(days=7),
                "max_attempts": 2,
                "max_score": 100,
                "status": "published",
            },
        )
        assignment.assigned_students.set([student])

        exam, _ = Exam.objects.update_or_create(
            slug=self.EXAM_SLUG,
            defaults={
                "title": self.EXAM_TITLE,
                "description": "Seeded exam for the E2E scenario.",
                "exam_type": "test",
                "author": teacher,
                "course": course,
                "organization": org,
                "is_active": True,
                "is_public": False,
                "total_duration_minutes": 15,
                "default_question_time_seconds": 30,
                "max_attempts_per_user": 1,
                "random_question_count": 1,
                "default_question_points": 1,
            },
        )
        self._ensure_exam_question(exam=exam, text="Who manages grading in this seeded scenario?")
        exam.allowed_groups.set([group])

        if not group.students.filter(id=late_student.id).exists():
            group.students.add(late_student)
        self._ensure_course_membership(
            course=course,
            user=late_student,
            role="student",
            group_name=group.name,
        )
        assignment.assigned_students.add(*list(group.students.all()))

        isolated_owner = self._ensure_user(
            username=options["isolated_owner_username"],
            password=password,
            email="ci-isolated-owner-e2e@emsarena.local",
            first_name="CI",
            last_name="IsolatedOwner",
        )
        isolated_org = self._ensure_isolated_org(owner=isolated_owner, org_slug=options["isolated_org_slug"])
        isolated_roles = self._ensure_roles(isolated_org)
        self._configure_profile(user=isolated_owner, organization=isolated_org, profile_role=ProfileRole.ORG_OWNER)
        self._ensure_membership(
            user=isolated_owner,
            organization=isolated_org,
            role=isolated_roles["rector"],
            assigned_by=isolated_owner,
            primary=True,
        )
        isolated_course, _ = Course.objects.update_or_create(
            slug="ci-isolated-course",
            defaults={
                "owner": isolated_owner,
                "title": "CI Isolated Course",
                "description": "Cross-tenant isolation target.",
                "organization": isolated_org,
                "status": "published",
            },
        )
        self._ensure_course_membership(course=isolated_course, user=isolated_owner, role="teacher")
        isolated_exam, _ = Exam.objects.update_or_create(
            slug=self.ISOLATED_EXAM_SLUG,
            defaults={
                "title": self.ISOLATED_EXAM_TITLE,
                "description": "Cross-tenant isolation target.",
                "exam_type": "test",
                "author": isolated_owner,
                "course": isolated_course,
                "organization": isolated_org,
                "is_active": True,
                "is_public": False,
                "total_duration_minutes": 10,
                "default_question_time_seconds": 30,
                "max_attempts_per_user": 1,
                "random_question_count": 1,
                "default_question_points": 1,
            },
        )
        self._ensure_exam_question(exam=isolated_exam, text="Cross-tenant access should stay isolated.")

        pending_owner = self._ensure_user(
            username=options["pending_owner_username"],
            password=password,
            email="ci-pending-owner-e2e@emsarena.local",
            first_name="CI",
            last_name="PendingOwner",
        )
        pending_org = self._ensure_pending_org(owner=pending_owner, org_slug=options["pending_org_slug"])
        pending_roles = self._ensure_roles(pending_org)
        self._configure_profile(
            user=pending_owner,
            organization=pending_org,
            profile_role=ProfileRole.ORG_OWNER,
            requested_organization=pending_org,
        )
        self._ensure_membership(
            user=pending_owner,
            organization=pending_org,
            role=pending_roles["rector"],
            assigned_by=pending_owner,
            primary=True,
        )

        resume_exam, _ = Exam.objects.update_or_create(
            slug=self.RESUME_EXAM_SLUG,
            defaults={
                "title": self.RESUME_EXAM_TITLE,
                "description": "Seeded in-progress exam for resume regression coverage.",
                "exam_type": "test",
                "author": teacher,
                "course": course,
                "organization": org,
                "is_active": True,
                "is_public": False,
                "total_duration_minutes": 10,
                "default_question_time_seconds": 30,
                "max_attempts_per_user": 1,
                "random_question_count": 1,
                "default_question_points": 1,
            },
        )
        resume_question = self._ensure_exam_question(
            exam=resume_exam,
            text="This exam should resume the existing in-progress attempt.",
        )
        resume_exam.allowed_users.set([resume_student])

        ExamAttempt.objects.filter(exam=resume_exam, user=resume_student).delete()
        resume_attempt = ExamAttempt.objects.create(
            user=resume_student,
            exam=resume_exam,
            attempt_number=1,
            status="in_progress",
        )
        ExamAnswer.objects.update_or_create(
            attempt=resume_attempt,
            question=resume_question,
            defaults={"is_correct": False},
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded E2E role scenario with users: "
                + ", ".join(
                    [
                        owner.username,
                        admin.username,
                        teacher.username,
                        staff.username,
                        student.username,
                        late_student.username,
                        resume_student.username,
                        pending_owner.username,
                    ]
                )
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Active org: {org.slug}; isolated org: {isolated_org.slug}; pending org: {pending_org.slug}"
            )
        )
