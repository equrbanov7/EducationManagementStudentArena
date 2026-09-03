"""PostgreSQL negative matrix for registrar migration-target DB guards."""

import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

import pytest

from apps.courses.models import Course
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    FinalGrade,
    Lesson,
    LessonMark,
    Program,
    ScheduleSlot,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required."),
]


class RegistrarMigrationTargetGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner_a = User.objects.create_user("pg_integrity_owner_a", password="pw")
            cls.owner_b = User.objects.create_user("pg_integrity_owner_b", password="pw")
            cls.org_a = Organization.objects.create(
                name="PG Integrity A",
                slug="pg-integrity-a",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner_a,
                status="active",
                is_active=True,
            )
            cls.org_b = Organization.objects.create(
                name="PG Integrity B",
                slug="pg-integrity-b",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner_b,
                status="active",
                is_active=True,
            )
            cls.student_a = User.objects.create_user("pg_integrity_student_a", password="pw")
            cls.student_b = User.objects.create_user("pg_integrity_student_b", password="pw")
            cls.teacher_a = User.objects.create_user("pg_integrity_teacher_a", password="pw")
            cls.teacher_b = User.objects.create_user("pg_integrity_teacher_b", password="pw")
            for org, student, teacher in (
                (cls.org_a, cls.student_a, cls.teacher_a),
                (cls.org_b, cls.student_b, cls.teacher_b),
            ):
                Membership.objects.create(
                    organization=org,
                    user=student,
                    role=org.roles.get(name="student"),
                    is_active=True,
                )
                Membership.objects.create(
                    organization=org,
                    user=teacher,
                    role=org.roles.get(name="teacher"),
                    is_active=True,
                )

            cls.group_a = OrgUnit.objects.create(
                organization=cls.org_a,
                name="PG Group A",
                slug="pg-integrity-group-a",
                unit_type=OrgUnitType.GROUP,
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org_b,
                name="PG Group B",
                slug="pg-integrity-group-b",
                unit_type=OrgUnitType.GROUP,
            )
            cls.period_a = cls._period(cls.org_a, "A")
            cls.period_b = cls._period(cls.org_b, "B")
            cls.program_a = Program.objects.create(organization=cls.org_a, code="PGA", name="PGA")
            cls.program_b = Program.objects.create(organization=cls.org_b, code="PGB", name="PGB")
            cls.program_a2 = Program.objects.create(organization=cls.org_a, code="PGA2", name="PGA2")
            cls.curriculum_a = Curriculum.objects.create(
                organization=cls.org_a,
                program=cls.program_a,
                admission_year=2026,
            )
            cls.curriculum_b = Curriculum.objects.create(
                organization=cls.org_b,
                program=cls.program_b,
                admission_year=2026,
            )
            cls.subject_a = Subject.objects.create(organization=cls.org_a, code="PGA-S1", name="A1")
            cls.subject_a2 = Subject.objects.create(organization=cls.org_a, code="PGA-S2", name="A2")
            cls.subject_b = Subject.objects.create(organization=cls.org_b, code="PGB-S1", name="B1")
            CurriculumSubject.objects.create(
                organization=cls.org_a,
                curriculum=cls.curriculum_a,
                subject=cls.subject_a,
                semester_number=1,
            )
            cls.record_a = StudentAcademicRecord.objects.create(
                organization=cls.org_a,
                student=cls.student_a,
                program=cls.program_a,
                curriculum=cls.curriculum_a,
                group=cls.group_a,
                admission_year=2026,
            )
            cls.offering_a = cls._offering(
                cls.org_a,
                cls.subject_a,
                cls.period_a,
                cls.group_a,
                cls.teacher_a,
            )
            cls.offering_a2 = cls._offering(
                cls.org_a,
                cls.subject_a2,
                cls.period_a,
                cls.group_a,
                cls.teacher_a,
            )
            cls.offering_b = cls._offering(
                cls.org_b,
                cls.subject_b,
                cls.period_b,
                cls.group_b,
                cls.teacher_b,
            )
            cls.enrollment_a = Enrollment.objects.create(
                organization=cls.org_a,
                student=cls.student_a,
                offering=cls.offering_a,
            )
            cls.enrollment_a2 = Enrollment.objects.create(
                organization=cls.org_a,
                student=cls.student_a,
                offering=cls.offering_a2,
            )
            cls.enrollment_b = Enrollment.objects.create(
                organization=cls.org_b,
                student=cls.student_b,
                offering=cls.offering_b,
            )
            cls.lesson_a = Lesson.objects.create(
                organization=cls.org_a,
                offering=cls.offering_a,
                instructor=cls.teacher_a,
                date=datetime.date(2026, 9, 2),
            )
            cls.component_a = AssessmentComponent.objects.create(
                organization=cls.org_a,
                offering=cls.offering_a,
                name="PG component A",
            )

    @classmethod
    def _period(cls, organization, suffix):
        return AcademicPeriod.objects.create(
            organization=organization,
            name=f"PG Period {suffix}",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date=datetime.date(2026, 9, 1),
            end_date=datetime.date(2027, 1, 31),
        )

    @classmethod
    def _offering(cls, organization, subject, period, group, instructor):
        return CourseOffering.objects.create(
            organization=organization,
            subject=subject,
            period=period,
            group=group,
            instructor=instructor,
        )

    def _rejects(self, operation):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                operation()

    def test_cross_tenant_parent_insert_matrix_is_rejected(self):
        course_b = Course.objects.create(
            owner=self.owner_b,
            title="PG tenant B course",
            organization=self.org_b,
        )
        cases = {
            "curriculum_program": lambda: Curriculum.objects.create(
                organization=self.org_a,
                program=self.program_b,
                admission_year=2025,
            ),
            "curriculum_subject": lambda: CurriculumSubject.objects.create(
                organization=self.org_a,
                curriculum=self.curriculum_a,
                subject=self.subject_b,
                semester_number=2,
            ),
            "student_group": lambda: StudentAcademicRecord.objects.create(
                organization=self.org_a,
                student=self.student_a,
                program=self.program_a2,
                curriculum=self.curriculum_a,
                group=self.group_b,
                admission_year=2026,
            ),
            "offering_period": lambda: CourseOffering.objects.create(
                organization=self.org_a,
                subject=self.subject_a2,
                period=self.period_b,
                group=self.group_a,
            ),
            "offering_course": lambda: CourseOffering.objects.create(
                organization=self.org_a,
                subject=self.subject_a2,
                period=self.period_a,
                group=None,
                course=course_b,
            ),
            "enrollment_offering": lambda: Enrollment.objects.create(
                organization=self.org_a,
                student=self.student_a,
                offering=self.offering_b,
            ),
            "schedule_offering": lambda: ScheduleSlot.objects.create(
                organization=self.org_a,
                offering=self.offering_b,
                weekday=1,
                start_time=datetime.time(9),
                end_time=datetime.time(10),
            ),
            "scheme_offering": lambda: AssessmentScheme.objects.create(
                organization=self.org_a,
                offering=self.offering_b,
            ),
            "lesson_offering": lambda: Lesson.objects.create(
                organization=self.org_a,
                offering=self.offering_b,
                date=datetime.date(2026, 9, 3),
            ),
            "lesson_mark_enrollment": lambda: LessonMark.objects.create(
                organization=self.org_a,
                lesson=self.lesson_a,
                enrollment=self.enrollment_b,
            ),
            "component_offering": lambda: AssessmentComponent.objects.create(
                organization=self.org_a,
                offering=self.offering_b,
                name="wrong tenant",
            ),
            "component_score_enrollment": lambda: ComponentScore.objects.create(
                organization=self.org_a,
                component=self.component_a,
                enrollment=self.enrollment_b,
            ),
            "final_enrollment": lambda: FinalGrade.objects.create(
                organization=self.org_a,
                enrollment=self.enrollment_b,
            ),
        }
        for label, operation in cases.items():
            with self.subTest(link=label):
                self._rejects(operation)

    def test_cross_tenant_parent_update_and_organization_move_are_rejected(self):
        self._rejects(lambda: CourseOffering.objects.filter(pk=self.offering_a.pk).update(subject=self.subject_b))
        self._rejects(lambda: Enrollment.objects.filter(pk=self.enrollment_a.pk).update(offering=self.offering_b))
        self._rejects(
            lambda: CourseOffering.objects.filter(pk=self.offering_a.pk).update(
                organization=self.org_b,
                subject=self.subject_b,
                period=self.period_b,
                group=self.group_b,
                instructor=self.teacher_b,
            )
        )

    def test_guarded_parent_organization_raw_updates_are_rejected(self):
        course_a = Course.objects.create(
            owner=self.owner_a,
            title="PG tenant A course",
            organization=self.org_a,
        )
        CourseOffering.objects.filter(pk=self.offering_a.pk).update(course=course_a)
        parents = {
            "org_unit": self.group_a,
            "program": self.program_a,
            "curriculum": self.curriculum_a,
            "subject": self.subject_a,
            "academic_period": self.period_a,
            "offering": self.offering_a,
            "lesson": self.lesson_a,
            "enrollment": self.enrollment_a,
            "component": self.component_a,
            "course": course_a,
        }
        for label, parent in parents.items():
            with self.subTest(parent=label):
                model = type(parent)
                self._rejects(
                    lambda model=model, parent=parent: model.objects.filter(pk=parent.pk).update(
                        organization=self.org_b
                    )
                )

    def test_student_reference_requires_active_same_tenant_membership(self):
        outsider = User.objects.create_user("pg_integrity_student_outsider", password="pw")
        inactive = User.objects.create_user("pg_integrity_student_inactive", password="pw")
        Membership.objects.create(
            organization=self.org_a,
            user=inactive,
            role=self.org_a.roles.get(name="student"),
            is_active=False,
        )
        for user in (outsider, self.student_b, inactive):
            with self.subTest(user=user.username):
                self._rejects(
                    lambda user=user: StudentAcademicRecord.objects.create(
                        organization=self.org_a,
                        student=user,
                        program=self.program_a2,
                        curriculum=self.curriculum_a,
                        group=self.group_a,
                        admission_year=2026,
                    )
                )
                self._rejects(
                    lambda user=user: Enrollment.objects.create(
                        organization=self.org_a,
                        student=user,
                        offering=self.offering_a2,
                    )
                )

    def test_instructor_requires_active_permissioned_membership(self):
        outsider = User.objects.create_user("pg_integrity_teacher_outsider", password="pw")
        permissionless = User.objects.create_user("pg_integrity_teacher_permissionless", password="pw")
        inactive = User.objects.create_user("pg_integrity_teacher_inactive", password="pw")
        Membership.objects.create(
            organization=self.org_a,
            user=permissionless,
            role=self.org_a.roles.get(name="student"),
            is_active=True,
        )
        Membership.objects.create(
            organization=self.org_a,
            user=inactive,
            role=self.org_a.roles.get(name="teacher"),
            is_active=False,
        )
        for instructor in (outsider, self.teacher_b, permissionless, inactive):
            with self.subTest(user=instructor.username):
                self._rejects(
                    lambda instructor=instructor: CourseOffering.objects.create(
                        organization=self.org_a,
                        subject=self.subject_a2,
                        period=self.period_a,
                        group=None,
                        instructor=instructor,
                    )
                )
                self._rejects(
                    lambda instructor=instructor: Lesson.objects.create(
                        organization=self.org_a,
                        offering=self.offering_a,
                        instructor=instructor,
                        date=datetime.date(2026, 10, 1),
                    )
                )

    def test_legacy_permission_alias_wildcard_is_accepted(self):
        wildcard_teacher = User.objects.create_user("pg_integrity_wildcard_teacher", password="pw")
        wildcard_role = Role.objects.create(
            organization=self.org_a,
            name="pg_migration_grader",
            display_name="PG migration grader",
            scope_type=RoleScopeType.COURSE,
            permissions=["grading.*"],
            is_active=True,
        )
        Membership.objects.create(
            organization=self.org_a,
            user=wildcard_teacher,
            role=wildcard_role,
            is_active=True,
        )
        offering = CourseOffering.objects.create(
            organization=self.org_a,
            subject=self.subject_a2,
            period=self.period_a,
            group=None,
            instructor=wildcard_teacher,
        )
        self.assertEqual(offering.instructor_id, wildcard_teacher.id)

    def test_same_tenant_but_different_offering_scores_are_rejected_on_insert_and_update(self):
        self._rejects(
            lambda: LessonMark.objects.create(
                organization=self.org_a,
                lesson=self.lesson_a,
                enrollment=self.enrollment_a2,
            )
        )
        self._rejects(
            lambda: ComponentScore.objects.create(
                organization=self.org_a,
                component=self.component_a,
                enrollment=self.enrollment_a2,
            )
        )
        valid_mark = LessonMark.objects.create(
            organization=self.org_a,
            lesson=self.lesson_a,
            enrollment=self.enrollment_a,
        )
        self._rejects(lambda: LessonMark.objects.filter(pk=valid_mark.pk).update(enrollment=self.enrollment_a2))

    def test_student_record_program_curriculum_coherence_is_rejected(self):
        second_student = User.objects.create_user("pg_integrity_second_student", password="pw")
        Membership.objects.create(
            organization=self.org_a,
            user=second_student,
            role=self.org_a.roles.get(name="student"),
            is_active=True,
        )
        self._rejects(
            lambda: StudentAcademicRecord.objects.create(
                organization=self.org_a,
                student=second_student,
                program=self.program_a2,
                curriculum=self.curriculum_a,
                group=self.group_a,
                admission_year=2026,
            )
        )

    def test_stored_functions_are_hardened_and_runtime_format_is_valid(self):
        expected_functions = {
            "registrar_assert_migration_target_integrity",
            "registrar_guard_active_member",
            "registrar_guard_component_score_coherence",
            "registrar_guard_lesson_mark_coherence",
            "registrar_guard_offering_course_organization",
            "registrar_guard_organization_immutable",
            "registrar_guard_same_org_fk",
            "registrar_guard_student_record_coherence",
            "registrar_member_has_permission",
        }
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_functiondef('public.registrar_guard_same_org_fk()'::regprocedure)")
            definition = cursor.fetchone()[0]
            cursor.execute(
                "SELECT proname, prosecdef, proconfig, "
                "has_function_privilege('rls_app_role', oid, 'EXECUTE') "
                "FROM pg_proc WHERE pronamespace = 'public'::regnamespace "
                "AND proname = ANY(%s)",
                [list(expected_functions)],
            )
            hardened_functions = cursor.fetchall()
            cursor.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgname = 'registrar_organization_immutable_guard' AND NOT tgisinternal"
            )
            immutable_trigger_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgfoid = 'public.registrar_guard_same_org_fk()'::regprocedure AND NOT tgisinternal"
            )
            same_org_trigger_count = cursor.fetchone()[0]
        self.assertIn("public.%I", definition)
        self.assertNotIn("public.%%I", definition)
        self.assertEqual({row[0] for row in hardened_functions}, expected_functions)
        for _name, security_definer, config, restricted_can_execute in hardened_functions:
            self.assertTrue(security_definer)
            self.assertIn("search_path=pg_catalog, public", config)
            self.assertFalse(restricted_can_execute)
        # 0041 core graph + 0042 remaining migration-target graph
        # + 0056 `registrar_enrollment.source_group_id` (alt qrupdan əlavə provenansı)
        # + 0058 `registrar_teachinghandover.offering_id` (fənn təhvili qeydi).
        self.assertEqual(immutable_trigger_count, 30)
        self.assertEqual(same_org_trigger_count, 41)

    def test_precheck_stops_instead_of_rewriting_existing_violation(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL session_replication_role = replica")
                try:
                    invalid = Curriculum.objects.create(
                        organization=self.org_a,
                        program=self.program_b,
                        admission_year=2025,
                    )
                finally:
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL session_replication_role = origin")
                with connection.cursor() as cursor:
                    cursor.execute("SELECT public.registrar_assert_migration_target_integrity()")
                self.fail(f"precheck accepted invalid curriculum {invalid.pk}")

    def test_restricted_role_cannot_insert_cross_tenant_parent(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org_a.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            self._rejects(
                lambda: Curriculum.objects.create(
                    organization=self.org_a,
                    program=self.program_b,
                    admission_year=2025,
                )
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
