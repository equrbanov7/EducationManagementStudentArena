"""PostgreSQL negative matrix for the remaining migration-target guards."""

import datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

import pytest

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    ComponentScoreCorrection,
    CourseOffering,
    CourseWork,
    CourseWorkCorrection,
    CriterionScore,
    Enrollment,
    FinalGrade,
    GroupElectiveChoice,
    JournalCorrection,
    Lesson,
    LessonCorrection,
    LessonMark,
    ResitRecord,
    Rubric,
    RubricCriterion,
    ScheduleSlot,
    SelfWorkCorrection,
    SelfWorkMark,
    SelfWorkTopic,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required."),
]


class RemainingMigrationTargetGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner_a = User.objects.create_user("remaining_pg_owner_a", password="pw")
            cls.owner_b = User.objects.create_user("remaining_pg_owner_b", password="pw")
            cls.org_a = cls._organization(cls.owner_a, "A")
            cls.org_b = cls._organization(cls.owner_b, "B")

            cls.student_a = User.objects.create_user("remaining_pg_student_a", password="pw")
            cls.student_b = User.objects.create_user("remaining_pg_student_b", password="pw")
            cls.teacher_a = User.objects.create_user("remaining_pg_teacher_a", password="pw")
            cls.teacher_b = User.objects.create_user("remaining_pg_teacher_b", password="pw")
            cls.actor_a = User.objects.create_user("remaining_pg_actor_a", password="pw")
            cls.actor_a2 = User.objects.create_user("remaining_pg_actor_a2", password="pw")
            cls.actor_b = User.objects.create_user("remaining_pg_actor_b", password="pw")
            for org, student, teacher, actors in (
                (cls.org_a, cls.student_a, cls.teacher_a, (cls.actor_a, cls.actor_a2)),
                (cls.org_b, cls.student_b, cls.teacher_b, (cls.actor_b,)),
            ):
                cls._membership(org, student, "student")
                cls._membership(org, teacher, "teacher")
                for actor in actors:
                    cls._membership(org, actor, "member")

            cls.inactive_actor_a = User.objects.create_user("remaining_pg_inactive_actor", password="pw")
            cls._membership(cls.org_a, cls.inactive_actor_a, "member", active=False)
            cls.permissionless_a = User.objects.create_user("remaining_pg_permissionless", password="pw")
            cls._membership(cls.org_a, cls.permissionless_a, "member")
            cls.inactive_teacher_a = User.objects.create_user("remaining_pg_inactive_teacher", password="pw")
            cls._membership(cls.org_a, cls.inactive_teacher_a, "teacher", active=False)

            cls.group_a = cls._group(cls.org_a, "A")
            cls.group_b = cls._group(cls.org_b, "B")
            cls.period_a = cls._period(cls.org_a, "A")
            cls.period_b = cls._period(cls.org_b, "B")
            cls.subject_a = Subject.objects.create(organization=cls.org_a, code="RPA", name="RPA")
            cls.subject_a2 = Subject.objects.create(organization=cls.org_a, code="RPA2", name="RPA2")
            cls.subject_b = Subject.objects.create(organization=cls.org_b, code="RPB", name="RPB")
            cls.offering_a = cls._offering(cls.org_a, cls.subject_a, cls.period_a, cls.group_a, cls.teacher_a)
            cls.offering_a2 = cls._offering(cls.org_a, cls.subject_a2, cls.period_a, cls.group_a, cls.teacher_a)
            cls.offering_b = cls._offering(cls.org_b, cls.subject_b, cls.period_b, cls.group_b, cls.teacher_b)
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
            cls.lesson_a = cls._lesson(cls.org_a, cls.offering_a, cls.teacher_a, 2)
            cls.lesson_a2 = cls._lesson(cls.org_a, cls.offering_a, cls.teacher_a, 3)
            cls.lesson_b = cls._lesson(cls.org_b, cls.offering_b, cls.teacher_b, 2)
            cls.mark_a = LessonMark.objects.create(
                organization=cls.org_a,
                lesson=cls.lesson_a,
                enrollment=cls.enrollment_a,
                entered_by=cls.teacher_a,
            )
            cls.mark_a2 = LessonMark.objects.create(
                organization=cls.org_a,
                lesson=cls.lesson_a2,
                enrollment=cls.enrollment_a,
                entered_by=cls.teacher_a,
            )
            cls.mark_b = LessonMark.objects.create(
                organization=cls.org_b,
                lesson=cls.lesson_b,
                enrollment=cls.enrollment_b,
                entered_by=cls.teacher_b,
            )
            cls.rubric_a = Rubric.objects.create(organization=cls.org_a, name="Remaining rubric A")
            cls.rubric_b = Rubric.objects.create(organization=cls.org_b, name="Remaining rubric B")
            cls.criterion_a = RubricCriterion.objects.create(
                organization=cls.org_a,
                rubric=cls.rubric_a,
                name="Criterion A",
            )
            cls.criterion_b = RubricCriterion.objects.create(
                organization=cls.org_b,
                rubric=cls.rubric_b,
                name="Criterion B",
            )
            cls.component_a = AssessmentComponent.objects.create(
                organization=cls.org_a,
                offering=cls.offering_a,
                rubric=cls.rubric_a,
                name="Remaining component A",
            )
            cls.component_b = AssessmentComponent.objects.create(
                organization=cls.org_b,
                offering=cls.offering_b,
                rubric=cls.rubric_b,
                name="Remaining component B",
            )
            cls.topic_a = SelfWorkTopic.objects.create(
                organization=cls.org_a,
                offering=cls.offering_a,
                title="Remaining topic A",
            )
            cls.topic_b = SelfWorkTopic.objects.create(
                organization=cls.org_b,
                offering=cls.offering_b,
                title="Remaining topic B",
            )

    @classmethod
    def _organization(cls, owner, suffix):
        return Organization.objects.create(
            name=f"Remaining PG {suffix}",
            slug=f"remaining-pg-{suffix.lower()}",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )

    @classmethod
    def _membership(cls, organization, user, role_name, active=True):
        return Membership.objects.create(
            organization=organization,
            user=user,
            role=organization.roles.get(name=role_name),
            is_active=active,
        )

    @classmethod
    def _group(cls, organization, suffix):
        return OrgUnit.objects.create(
            organization=organization,
            name=f"Remaining group {suffix}",
            slug=f"remaining-pg-group-{suffix.lower()}",
            unit_type=OrgUnitType.GROUP,
        )

    @classmethod
    def _period(cls, organization, suffix):
        return AcademicPeriod.objects.create(
            organization=organization,
            name=f"Remaining period {suffix}",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026/2027",
            start_date=datetime.date(2026, 9, 1),
            end_date=datetime.date(2027, 1, 31),
        )

    @classmethod
    def _offering(cls, organization, subject, period, group, teacher):
        return CourseOffering.objects.create(
            organization=organization,
            subject=subject,
            period=period,
            group=group,
            instructor=teacher,
        )

    @classmethod
    def _lesson(cls, organization, offering, teacher, day):
        return Lesson.objects.create(
            organization=organization,
            offering=offering,
            date=datetime.date(2026, 9, day),
            created_by=teacher,
            instructor=teacher,
        )

    def _rejects(self, operation):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                operation()

    def _journal_correction(self, **overrides):
        lesson_mark = overrides.get("lesson_mark", self.mark_a)
        values = {
            "organization": self.org_a,
            "lesson_mark": lesson_mark,
            "lesson_mark_ref": lesson_mark.pk,
            "lesson_ref": lesson_mark.lesson_id,
            "enrollment_ref": lesson_mark.enrollment_id,
            "field": "score",
            "old_score": 4,
            "new_score": 5,
            "reason": "technical",
            "note": "Verified evidence",
            "document": "journal_corrections/remaining.pdf",
            "corrected_by": self.actor_a,
            "corrected_by_name": self.actor_a.username,
        }
        values.update(overrides)
        return JournalCorrection.objects.create(**values)

    def test_cross_tenant_parent_insert_matrix_is_rejected(self):
        cases = {
            "group_choice_group": lambda: GroupElectiveChoice.objects.create(
                organization=self.org_a,
                group=self.group_b,
                period=self.period_a,
                elective_group="BLOCK",
                chosen_subject=self.subject_a,
                decided_by=self.actor_a,
            ),
            "rubric_criterion": lambda: RubricCriterion.objects.create(
                organization=self.org_a,
                rubric=self.rubric_b,
                name="wrong tenant",
            ),
            "component_rubric": lambda: AssessmentComponent.objects.create(
                organization=self.org_a,
                offering=self.offering_a,
                rubric=self.rubric_b,
                name="wrong rubric tenant",
            ),
            "criterion_score": lambda: CriterionScore.objects.create(
                organization=self.org_a,
                component=self.component_a,
                criterion=self.criterion_a,
                enrollment=self.enrollment_b,
            ),
            "selfwork_topic": lambda: SelfWorkTopic.objects.create(
                organization=self.org_a,
                offering=self.offering_b,
                title="wrong tenant",
            ),
            "selfwork_mark": lambda: SelfWorkMark.objects.create(
                organization=self.org_a,
                topic=self.topic_a,
                enrollment=self.enrollment_b,
            ),
            "coursework": lambda: CourseWork.objects.create(
                organization=self.org_a,
                enrollment=self.enrollment_b,
                topic="wrong tenant",
            ),
            "resit": lambda: ResitRecord.objects.create(
                organization=self.org_a,
                enrollment=self.enrollment_b,
                reason="total",
            ),
            "journal_correction": lambda: self._journal_correction(lesson_mark=self.mark_b),
            "lesson_correction": lambda: LessonCorrection.objects.create(
                organization=self.org_a,
                lesson=self.lesson_b,
                reason="technical",
                note="wrong tenant",
                document="journal_lesson_corrections/wrong.pdf",
                corrected_by=self.actor_a,
                corrected_by_name=self.actor_a.username,
            ),
            "selfwork_correction": lambda: SelfWorkCorrection.objects.create(
                organization=self.org_a,
                topic=self.topic_a,
                enrollment=self.enrollment_b,
                old_done=False,
                new_done=True,
                reason="technical",
                note="wrong tenant",
                document="journal_selfwork_corrections/wrong.pdf",
                corrected_by=self.actor_a,
                corrected_by_name=self.actor_a.username,
            ),
            "coursework_correction": lambda: CourseWorkCorrection.objects.create(
                organization=self.org_a,
                enrollment=self.enrollment_b,
                reason="technical",
                note="wrong tenant",
                document="journal_coursework_corrections/wrong.pdf",
                corrected_by=self.actor_a,
                corrected_by_name=self.actor_a.username,
            ),
            "component_correction": lambda: ComponentScoreCorrection.objects.create(
                organization=self.org_a,
                component=self.component_a,
                enrollment=self.enrollment_b,
                reason="technical",
                note="wrong tenant",
                document="journal_component_corrections/wrong.pdf",
                corrected_by=self.actor_a,
                corrected_by_name=self.actor_a.username,
            ),
        }
        for label, operation in cases.items():
            with self.subTest(link=label):
                self._rejects(operation)

    def test_same_tenant_different_offering_pairs_are_rejected(self):
        cases = {
            "criterion_score": lambda: CriterionScore.objects.create(
                organization=self.org_a,
                component=self.component_a,
                criterion=self.criterion_a,
                enrollment=self.enrollment_a2,
            ),
            "selfwork_mark": lambda: SelfWorkMark.objects.create(
                organization=self.org_a,
                topic=self.topic_a,
                enrollment=self.enrollment_a2,
            ),
            "selfwork_correction": lambda: SelfWorkCorrection.objects.create(
                organization=self.org_a,
                topic=self.topic_a,
                enrollment=self.enrollment_a2,
                old_done=False,
                new_done=True,
                reason="technical",
                note="different offering",
                document="journal_selfwork_corrections/different.pdf",
                corrected_by=self.actor_a,
                corrected_by_name=self.actor_a.username,
            ),
            "component_correction": lambda: ComponentScoreCorrection.objects.create(
                organization=self.org_a,
                component=self.component_a,
                enrollment=self.enrollment_a2,
                reason="technical",
                note="different offering",
                document="journal_component_corrections/different.pdf",
                corrected_by=self.actor_a,
                corrected_by_name=self.actor_a.username,
            ),
        }
        for label, operation in cases.items():
            with self.subTest(link=label):
                self._rejects(operation)

    def test_cross_tenant_actor_is_rejected_across_write_categories(self):
        cases = {
            "decision": lambda: GroupElectiveChoice.objects.create(
                organization=self.org_a,
                group=self.group_a,
                period=self.period_a,
                elective_group="ACTOR",
                chosen_subject=self.subject_a,
                decided_by=self.actor_b,
            ),
            "created_by": lambda: ScheduleSlot.objects.create(
                organization=self.org_a,
                offering=self.offering_a,
                weekday=1,
                start_time=datetime.time(9),
                end_time=datetime.time(10),
                created_by=self.actor_b,
            ),
            "entered_by": lambda: ComponentScore.objects.create(
                organization=self.org_a,
                component=self.component_a,
                enrollment=self.enrollment_a,
                entered_by=self.actor_b,
            ),
            "approval_actor": lambda: AssessmentScheme.objects.create(
                organization=self.org_a,
                offering=self.offering_a,
                submitted_by=self.actor_b,
            ),
            "correction_actor": lambda: self._journal_correction(corrected_by=self.actor_b),
        }
        for label, operation in cases.items():
            with self.subTest(actor=label):
                self._rejects(operation)

    def test_inactive_actor_cannot_be_written_or_reassigned(self):
        self._rejects(
            lambda: FinalGrade.objects.create(
                organization=self.org_a,
                enrollment=self.enrollment_a,
                entered_by=self.inactive_actor_a,
            )
        )
        final_grade = FinalGrade.objects.create(
            organization=self.org_a,
            enrollment=self.enrollment_a,
            entered_by=self.actor_a,
        )
        correction = self._journal_correction(
            corrected_by=self.actor_a,
            corrected_by_name=self.actor_a.username,
        )
        self._rejects(lambda: FinalGrade.objects.filter(pk=final_grade.pk).update(entered_by=self.inactive_actor_a))
        self.assertEqual(correction.corrected_by_id, self.actor_a.id)

    def test_membership_revocation_does_not_invalidate_historical_rows(self):
        final_grade = FinalGrade.objects.create(
            organization=self.org_a,
            enrollment=self.enrollment_a,
            entered_by=self.actor_a,
        )
        correction = self._journal_correction()
        Membership.objects.filter(organization=self.org_a, user=self.actor_a).update(is_active=False)
        final_grade.exam_score = 30
        final_grade.save(update_fields=["exam_score"])
        with connection.cursor() as cursor:
            cursor.execute("SELECT public.registrar_assert_remaining_target_integrity()")
        final_grade.refresh_from_db()
        correction.refresh_from_db()
        self.assertEqual(final_grade.entered_by_id, self.actor_a.id)
        self.assertEqual(correction.corrected_by_id, self.actor_a.id)

    def test_new_instructor_requires_live_grade_input_authority(self):
        for instructor in (self.teacher_b, self.permissionless_a, self.inactive_teacher_a):
            with self.subTest(instructor=instructor.username):
                self._rejects(
                    lambda instructor=instructor: LessonCorrection.objects.create(
                        organization=self.org_a,
                        lesson=self.lesson_a,
                        new_instructor=instructor,
                        reason="technical",
                        note="assignment",
                        document="journal_lesson_corrections/assignment.pdf",
                        corrected_by=self.actor_a,
                        corrected_by_name=self.actor_a.username,
                    )
                )
        accepted = LessonCorrection.objects.create(
            organization=self.org_a,
            lesson=self.lesson_a,
            new_instructor=self.teacher_a,
            reason="technical",
            note="authorized assignment",
            document="journal_lesson_corrections/authorized.pdf",
            corrected_by=self.actor_a,
            corrected_by_name=self.actor_a.username,
        )
        self.assertEqual(accepted.new_instructor_id, self.teacher_a.id)
        historical = LessonCorrection.objects.create(
            organization=self.org_a,
            lesson=self.lesson_a,
            old_instructor=self.inactive_teacher_a,
            reason="technical",
            note="historical instructor snapshot",
            document="journal_lesson_corrections/historical.pdf",
            corrected_by=self.actor_a,
            corrected_by_name=self.actor_a.username,
        )
        self.assertEqual(historical.old_instructor_id, self.inactive_teacher_a.id)

    def test_inactive_organization_rejects_new_actor_attribution(self):
        superuser = User.objects.create_superuser(
            "remaining_pg_inactive_org_superuser",
            email="remaining-inactive-org-superuser@example.com",
            password="pw",
        )
        Organization.objects.filter(pk=self.org_a.pk).update(is_active=False)
        for actor in (self.actor_a, superuser):
            with self.subTest(actor=actor.username):
                self._rejects(
                    lambda actor=actor: FinalGrade.objects.create(
                        organization=self.org_a,
                        enrollment=self.enrollment_a,
                        entered_by=actor,
                    )
                )

    def test_deactivated_user_rejects_new_student_and_instructor_links_but_preserves_history(self):
        with bypass_rls():
            new_student = User.objects.create_user("remaining_pg_deactivated_student", password="pw")
            new_teacher = User.objects.create_user("remaining_pg_deactivated_teacher", password="pw")
            self._membership(self.org_a, new_student, "student")
            self._membership(self.org_a, new_teacher, "teacher")
            User.objects.filter(pk__in=[new_student.pk, new_teacher.pk]).update(is_active=False)

            self._rejects(
                lambda: Enrollment.objects.create(
                    organization=self.org_a,
                    student=new_student,
                    offering=self.offering_a,
                )
            )
            self._rejects(lambda: CourseOffering.objects.filter(pk=self.offering_a.pk).update(instructor=new_teacher))

            User.objects.filter(pk__in=[self.student_a.pk, self.teacher_a.pk]).update(is_active=False)
            Enrollment.objects.filter(pk=self.enrollment_a.pk).update(absence_hours=1)
            CourseOffering.objects.filter(pk=self.offering_a.pk).update(lesson_hours=4)
            self.enrollment_a.refresh_from_db()
            self.offering_a.refresh_from_db()
            self.assertEqual(self.enrollment_a.student_id, self.student_a.pk)
            self.assertEqual(self.offering_a.instructor_id, self.teacher_a.pk)

    def test_inactive_organization_rejects_new_student_and_instructor_links_but_preserves_history(self):
        with bypass_rls():
            new_student = User.objects.create_user("remaining_pg_inactive_org_student", password="pw")
            new_teacher = User.objects.create_user("remaining_pg_inactive_org_teacher", password="pw")
            self._membership(self.org_a, new_student, "student")
            self._membership(self.org_a, new_teacher, "teacher")
            Organization.objects.filter(pk=self.org_a.pk).update(is_active=False)

            self._rejects(
                lambda: Enrollment.objects.create(
                    organization=self.org_a,
                    student=new_student,
                    offering=self.offering_a,
                )
            )
            self._rejects(lambda: CourseOffering.objects.filter(pk=self.offering_a.pk).update(instructor=new_teacher))

            Enrollment.objects.filter(pk=self.enrollment_a.pk).update(absence_hours=1)
            CourseOffering.objects.filter(pk=self.offering_a.pk).update(lesson_hours=4)
            self.enrollment_a.refresh_from_db()
            self.offering_a.refresh_from_db()
            self.assertEqual(self.enrollment_a.student_id, self.student_a.pk)
            self.assertEqual(self.offering_a.instructor_id, self.teacher_a.pk)

    def test_correction_evidence_parent_and_actor_are_immutable(self):
        correction = self._journal_correction()
        cases = {
            "evidence": lambda: JournalCorrection.objects.filter(pk=correction.pk).update(note="tampered"),
            "parent": lambda: JournalCorrection.objects.filter(pk=correction.pk).update(lesson_mark=self.mark_a2),
            "actor": lambda: JournalCorrection.objects.filter(pk=correction.pk).update(corrected_by=self.actor_a2),
            "organization": lambda: JournalCorrection.objects.filter(pk=correction.pk).update(organization=self.org_b),
        }
        for label, operation in cases.items():
            with self.subTest(field=label):
                self._rejects(operation)

    def test_new_parent_organization_raw_moves_are_rejected(self):
        self._rejects(lambda: Rubric.objects.filter(pk=self.rubric_a.pk).update(organization=self.org_b))
        self._rejects(lambda: SelfWorkTopic.objects.filter(pk=self.topic_a.pk).update(organization=self.org_b))
        self._rejects(lambda: RubricCriterion.objects.filter(pk=self.criterion_a.pk).update(organization=self.org_b))

    def test_cross_tenant_relation_raw_updates_are_rejected(self):
        self._rejects(lambda: RubricCriterion.objects.filter(pk=self.criterion_a.pk).update(rubric=self.rubric_b))
        self._rejects(lambda: SelfWorkTopic.objects.filter(pk=self.topic_a.pk).update(offering=self.offering_b))

    def test_precheck_stops_instead_of_rewriting_existing_violation(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL session_replication_role = replica")
                try:
                    invalid = SelfWorkMark.objects.create(
                        organization=self.org_a,
                        topic=self.topic_a,
                        enrollment=self.enrollment_a2,
                    )
                finally:
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL session_replication_role = origin")
                with connection.cursor() as cursor:
                    cursor.execute("SELECT public.registrar_assert_remaining_target_integrity()")
                self.fail(f"precheck accepted invalid self-work mark {invalid.pk}")

    def test_stored_functions_are_hardened_and_trigger_matrix_is_complete(self):
        expected_functions = {
            "registrar_actor_can_write_for_organization",
            "registrar_actor_belongs_to_organization",
            "registrar_assert_remaining_target_integrity",
            "registrar_guard_correction_evidence_immutable",
            "registrar_guard_criterion_score_coherence",
            "registrar_guard_same_offering_pair",
            "registrar_guard_same_org_historical_actor",
            "registrar_guard_same_org_actor",
            "registrar_member_has_permission",
        }
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_functiondef('public.registrar_guard_same_offering_pair()'::regprocedure)")
            definition = cursor.fetchone()[0]
            cursor.execute(
                "SELECT pg_get_functiondef("
                "'public.registrar_member_has_permission(uuid, bigint, text)'::regprocedure)"
            )
            member_definition = cursor.fetchone()[0]
            cursor.execute(
                "SELECT proname, prosecdef, proconfig, "
                "has_function_privilege('rls_app_role', oid, 'EXECUTE') "
                "FROM pg_proc WHERE pronamespace = 'public'::regnamespace "
                "AND proname = ANY(%s)",
                [list(expected_functions)],
            )
            hardened_functions = cursor.fetchall()
            cursor.execute(
                "SELECT tgname, count(*) FROM pg_trigger "
                "WHERE NOT tgisinternal AND tgname = ANY(%s) GROUP BY tgname",
                [
                    [
                        "registrar_correction_evidence_immutable_guard",
                        "registrar_criterion_score_coherence_guard",
                        "registrar_same_offering_pair_guard",
                    ]
                ],
            )
            trigger_counts = dict(cursor.fetchall())
            cursor.execute(
                "SELECT count(*) FROM pg_trigger "
                "WHERE NOT tgisinternal AND tgname LIKE 'registrar_same_org_actor_%%_guard'"
            )
            actor_trigger_count = cursor.fetchone()[0]
        self.assertIn("public.%I", definition)
        self.assertNotIn("public.%%I", definition)
        self.assertIn("JOIN public.auth_user", member_definition)
        self.assertIn("JOIN public.organizations_organization", member_definition)
        self.assertEqual({row[0] for row in hardened_functions}, expected_functions)
        for _name, security_definer, config, restricted_can_execute in hardened_functions:
            self.assertTrue(security_definer)
            self.assertIn("search_path=pg_catalog, public", config)
            self.assertFalse(restricted_can_execute)
        self.assertEqual(actor_trigger_count, 18)
        self.assertEqual(trigger_counts["registrar_same_offering_pair_guard"], 3)
        self.assertEqual(trigger_counts["registrar_criterion_score_coherence_guard"], 1)
        self.assertEqual(trigger_counts["registrar_correction_evidence_immutable_guard"], 5)

    def test_restricted_role_cannot_insert_cross_tenant_parent(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org_a.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            self._rejects(
                lambda: SelfWorkTopic.objects.create(
                    organization=self.org_a,
                    offering=self.offering_b,
                    title="restricted cross tenant",
                )
            )
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
