"""Engine-neutral reference-identity and controlled-transfer tests."""

import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.organizations.models import AcademicPeriod, Membership, OrgUnit
from apps.registrar import transfer
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    CourseOffering,
    CourseWork,
    CriterionScore,
    Curriculum,
    Enrollment,
    FinalGrade,
    GroupTransferEvidence,
    Lesson,
    LessonMark,
    Program,
    ResitRecord,
    Rubric,
    RubricCriterion,
    ScheduleSlot,
    SelfWorkMark,
    SelfWorkTopic,
    Subject,
)
from core.constants import AcademicPeriodType, OrgUnitType
from core.rls import bypass_rls

from .test_rubrics import RubricBaseTest

User = get_user_model()


class ReferenceIdentityValidationTests(RubricBaseTest):
    def _alternatives(self):
        group = OrgUnit.objects.create(
            organization=self.org,
            name="Identity second group",
            slug="identity-second-group",
            unit_type=OrgUnitType.GROUP,
        )
        period = AcademicPeriod.objects.create(
            organization=self.org,
            name="Identity second period",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2025/2026",
            start_date=datetime.date(2025, 9, 1),
            end_date=datetime.date(2026, 1, 31),
        )
        subject = Subject.objects.create(
            organization=self.org,
            code="IDENTITY-2",
            name="Identity second subject",
        )
        offering = CourseOffering.objects.create(
            organization=self.org,
            subject=subject,
            period=period,
            group=group,
            instructor=self.teacher,
        )
        second_student = User.objects.create_user("identity_second_student", password="pw")
        Membership.objects.create(
            organization=self.org,
            user=second_student,
            role=self.org.roles.get(name="student"),
            is_active=True,
        )
        second_enrollment = Enrollment.objects.create(
            organization=self.org,
            student=second_student,
            offering=self.offering,
        )
        rubric = Rubric.objects.create(organization=self.org, name="Identity second rubric")
        criterion = RubricCriterion.objects.create(
            organization=self.org,
            rubric=self.rubric,
            name="Identity spare criterion",
        )
        component = AssessmentComponent.objects.create(
            organization=self.org,
            offering=self.offering,
            rubric=self.rubric,
            name="Identity second component",
        )
        return {
            "group": group,
            "period": period,
            "subject": subject,
            "offering": offering,
            "enrollment": second_enrollment,
            "rubric": rubric,
            "criterion": criterion,
            "component": component,
        }

    def _identity_rows(self, alternatives):
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=datetime.date(2025, 1, 10),
            created_by=self.teacher,
        )
        second_lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=datetime.date(2025, 1, 11),
            created_by=self.teacher,
        )
        mark = LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=self.enrollment,
            entered_by=self.teacher,
        )
        scheme, _created = AssessmentScheme.objects.get_or_create(
            organization=self.org,
            offering=self.offering,
        )
        slot = ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.offering,
            weekday=1,
            start_time=datetime.time(9),
            end_time=datetime.time(10),
            created_by=self.teacher,
        )
        second_component = AssessmentComponent.objects.create(
            organization=self.org,
            offering=self.offering,
            rubric=self.rubric,
            name="Identity parallel component",
        )
        component_score = ComponentScore.objects.create(
            organization=self.org,
            component=self.component,
            enrollment=self.enrollment,
            score=1,
            entered_by=self.teacher,
        )
        criteria = list(self.rubric.criteria.order_by("order"))
        criterion_score = CriterionScore.objects.create(
            organization=self.org,
            component=self.component,
            criterion=criteria[0],
            enrollment=self.enrollment,
            points=1,
            entered_by=self.teacher,
        )
        topic = SelfWorkTopic.objects.create(
            organization=self.org,
            offering=self.offering,
            title="Identity topic",
        )
        second_topic = SelfWorkTopic.objects.create(
            organization=self.org,
            offering=self.offering,
            title="Identity parallel topic",
        )
        selfwork_mark = SelfWorkMark.objects.create(
            organization=self.org,
            topic=topic,
            enrollment=self.enrollment,
            entered_by=self.teacher,
        )
        coursework = CourseWork.objects.create(
            organization=self.org,
            enrollment=self.enrollment,
            topic="Identity course work",
            entered_by=self.teacher,
        )
        final_grade = FinalGrade.objects.create(
            organization=self.org,
            enrollment=self.enrollment,
            entered_by=self.teacher,
        )
        resit = ResitRecord.objects.create(
            organization=self.org,
            enrollment=self.enrollment,
            reason="total",
            decided_by=self.teacher,
        )
        return {
            "lesson": lesson,
            "second_lesson": second_lesson,
            "mark": mark,
            "scheme": scheme,
            "slot": slot,
            "second_component": second_component,
            "component_score": component_score,
            "criterion_score": criterion_score,
            "second_criterion": criteria[1],
            "topic": topic,
            "second_topic": second_topic,
            "selfwork_mark": selfwork_mark,
            "coursework": coursework,
            "final_grade": final_grade,
            "resit": resit,
        }

    def test_existing_reference_identity_save_matrix_is_rejected(self):
        with bypass_rls():
            alternatives = self._alternatives()
            rows = self._identity_rows(alternatives)
            cases = (
                (self.enrollment, "offering", alternatives["offering"]),
                (rows["lesson"], "offering", alternatives["offering"]),
                (rows["mark"], "lesson", rows["second_lesson"]),
                (rows["mark"], "enrollment", alternatives["enrollment"]),
                (rows["scheme"], "offering", alternatives["offering"]),
                (rows["slot"], "offering", alternatives["offering"]),
                (rows["component_score"], "component", rows["second_component"]),
                (rows["component_score"], "enrollment", alternatives["enrollment"]),
                (rows["criterion_score"], "component", rows["second_component"]),
                (rows["criterion_score"], "criterion", rows["second_criterion"]),
                (rows["criterion_score"], "enrollment", alternatives["enrollment"]),
                (rows["topic"], "offering", alternatives["offering"]),
                (rows["selfwork_mark"], "topic", rows["second_topic"]),
                (rows["selfwork_mark"], "enrollment", alternatives["enrollment"]),
                (rows["coursework"], "enrollment", alternatives["enrollment"]),
                (rows["final_grade"], "enrollment", alternatives["enrollment"]),
                (rows["resit"], "enrollment", alternatives["enrollment"]),
                (self.rubric.criteria.first(), "rubric", alternatives["rubric"]),
            )
            for instance, field, replacement in cases:
                original = getattr(instance, field)
                setattr(instance, field, replacement)
                with self.subTest(model=instance._meta.label, field=field):
                    with self.assertRaises(ValidationError) as caught:
                        instance.save(update_fields=[field])
                    self.assertIn(field, caught.exception.message_dict)
                setattr(instance, field, original)

    def test_conditional_parent_identity_freezes_only_after_dependents(self):
        with bypass_rls():
            alternatives = self._alternatives()
            cases = (
                (self.offering, "subject", alternatives["subject"]),
                (self.offering, "period", alternatives["period"]),
                (self.offering, "group", alternatives["group"]),
                (self.component, "offering", alternatives["offering"]),
                (self.component, "rubric", alternatives["rubric"]),
            )
            ComponentScore.objects.create(
                organization=self.org,
                component=self.component,
                enrollment=self.enrollment,
                score=0,
                entered_by=self.teacher,
            )
            for instance, field, replacement in cases:
                original = getattr(instance, field)
                setattr(instance, field, replacement)
                with self.subTest(model=instance._meta.label, field=field):
                    with self.assertRaises(ValidationError):
                        instance.save(update_fields=[field])
                setattr(instance, field, original)

            second_program = Program.objects.create(
                organization=self.org,
                code="IDENTITY-P2",
                name="Identity second program",
            )
            self.curriculum.program = second_program
            with self.assertRaises(ValidationError):
                self.curriculum.save(update_fields=["program"])

            empty_curriculum = Curriculum.objects.create(
                organization=self.org,
                program=self.program,
                admission_year=2030,
            )
            empty_curriculum.program = second_program
            empty_curriculum.save(update_fields=["program"])
            self.assertEqual(empty_curriculum.program_id, second_program.pk)

            empty_component = alternatives["component"]
            empty_component.rubric = self.rubric
            empty_component.save(update_fields=["rubric"])
            self.assertEqual(empty_component.rubric_id, self.rubric.pk)

    def test_group_save_is_rejected_but_sanctioned_transfer_succeeds(self):
        with bypass_rls():
            alternatives = self._alternatives()
            self.record.group = alternatives["group"]
            with self.assertRaises(ValidationError) as caught:
                self.record.save(update_fields=["group"])
            self.assertIn("group", caught.exception.message_dict)
            self.record.refresh_from_db()

            result = transfer.transfer_student_group(
                record=self.record,
                new_group=alternatives["group"],
                period=self.period,
                by_user=self.owner,
            )
            self.assertEqual(result["moved"], 1)
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, alternatives["group"].pk)
            evidence = GroupTransferEvidence.objects.get(record=self.record)
            self.assertTrue(evidence.is_finalized)
            self.assertIsNotNone(evidence.audit_ref)

    def test_transfer_requires_actor_and_cleans_authorization_after_audit_failure(self):
        with bypass_rls():
            alternatives = self._alternatives()
            with self.assertRaises(ValidationError):
                transfer.transfer_student_group(
                    record=self.record,
                    new_group=alternatives["group"],
                    period=self.period,
                    by_user=None,
                )
            with (
                patch.object(transfer.audit_service, "log_action", side_effect=RuntimeError("audit failed")),
                self.assertRaisesRegex(RuntimeError, "audit failed"),
            ):
                transfer.transfer_student_group(
                    record=self.record,
                    new_group=alternatives["group"],
                    period=self.period,
                    by_user=self.owner,
                )
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group.pk)
            self.assertFalse(GroupTransferEvidence.objects.filter(record=self.record).exists())
            self.record.group = alternatives["group"]
            with self.assertRaises(ValidationError):
                self.record.save(update_fields=["group"])

    def test_transfer_evidence_is_append_only_in_model_layer(self):
        with bypass_rls():
            alternatives = self._alternatives()
            transfer.transfer_student_group(
                record=self.record,
                new_group=alternatives["group"],
                period=self.period,
                by_user=self.owner,
            )
            evidence = GroupTransferEvidence.objects.get(record=self.record)
            evidence.actor_ref = self.student.pk
            with self.assertRaises(ValidationError):
                evidence.save(update_fields=["actor_ref"])
            with self.assertRaises(ValidationError):
                evidence.delete()

    def test_transfer_without_period_is_supported_only_when_no_current_period_exists(self):
        with bypass_rls():
            alternatives = self._alternatives()
            with self.assertRaises(ValidationError):
                transfer.transfer_student_group(
                    record=self.record,
                    new_group=alternatives["group"],
                    period=None,
                    by_user=self.owner,
                )
            AcademicPeriod.objects.filter(pk=self.period.pk).update(is_current=False)
            result = transfer.transfer_student_group(
                record=self.record,
                new_group=alternatives["group"],
                period=None,
                by_user=self.owner,
            )
            self.assertEqual((result["moved"], result["created"]), (0, 0))
            evidence = GroupTransferEvidence.objects.get(record=self.record)
            self.assertIsNone(evidence.period_id)
            self.assertTrue(evidence.is_finalized)

    def test_ordinary_mutable_updates_remain_supported(self):
        with bypass_rls():
            self.enrollment.absence_hours = 2
            self.enrollment.save(update_fields=["absence_hours"])
            self.component.name = "Updated display name"
            self.component.save(update_fields=["name"])
            self.assertEqual(self.enrollment.absence_hours, 2)
            self.assertEqual(self.component.name, "Updated display name")
