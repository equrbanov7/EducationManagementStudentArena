"""Generic exact transition history survives without a guest/source-group marker."""

import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.registrar import gradebook, guest_merge, read_memo
from apps.registrar.enrollment_history import annotate_predecessor, predecessors
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.registrar.tests.test_guest_roster import _GuestRosterBase
from core.rls import bypass_rls


class ExactHistoryCarryTests(_GuestRosterBase):
    def setUp(self):
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)

    def transition(self, student=None):
        student = student or self.guest
        source = Enrollment.objects.get(student=student, offering=self.other_offering)
        target, _ = Enrollment.objects.get_or_create(organization=self.org, student=student, offering=self.offering)
        source.status = "dropped"
        source.superseded_by = target
        source.save(update_fields=["status", "superseded_by"])
        self.assertIsNone(target.source_group_id)
        return source, target

    def mark(self, enrollment, index, status="absent", score=None):
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=enrollment.offering,
            kind="seminar",
            date=datetime.date(2025, 9, 1) + datetime.timedelta(days=index),
            hours=2,
        )
        return LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score
        )

    def test_generic_null_marker_grid_and_recompute_preserve_own10_plus_previous1(self):
        source, target = self.transition()
        previous = self.mark(source, 0)
        scored = self.mark(source, 1, "present", 8)
        excused = self.mark(source, 2, "excused")
        for i in range(10):
            self.mark(target, i + 3)
        before = list(LessonMark.objects.order_by("pk").values_list("pk", "status", "score"))
        row = next(
            r for r in gradebook.get_offering_journal(offering=self.offering)["rows"] if r["enrollment"].pk == target.pk
        )
        self.assertEqual((row["absence_count"], row["absence_hours"]), (11, 22))
        self.assertEqual((row["carry_over"]["marks"], row["carry_over"]["scored"]), (3, 1))
        self.assertEqual(guest_merge.carried_absence_hours(target), 2)
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=target), 22)
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=source), 2)
        target.refresh_from_db()
        self.assertEqual(target.absence_hours, 22)
        self.assertIsNone(target.source_group_id)
        self.assertEqual(before, list(LessonMark.objects.order_by("pk").values_list("pk", "status", "score")))
        self.assertEqual({previous.pk, scored.pk, excused.pk} <= {v[0] for v in before}, True)

    def test_multiple_predecessors_and_credit_are_counted_once_without_copying(self):
        import uuid

        from apps.registrar.models import AbsenceCredit

        source, target = self.transition()
        other, _ = CourseOffering.objects.get_or_create(
            organization=self.org, subject=self.history, period=self.period, group=self.far_group
        )
        second = Enrollment.objects.create(
            organization=self.org, student=self.guest, offering=other, status="dropped", superseded_by=target
        )
        self.mark(source, 0)
        self.mark(second, 1)
        AbsenceCredit.objects.create(
            organization=self.org,
            enrollment=source,
            hours=1,
            reason="Təsdiqli bir saat güzəşt",
            actor=self.owner,
            request_token=uuid.uuid4(),
            old_absence_hours=2,
            new_absence_hours=1,
        )
        for _ in range(2):
            summary = guest_merge.carry_over_map([target.pk, target.pk])[target.pk]
            self.assertEqual((summary["absence_count"], summary["absence_hours"], summary["marks"]), (2, 3, 2))
            self.assertEqual(gradebook.recompute_absence_hours(enrollment=target), 3)
        self.assertEqual(LessonMark.objects.filter(enrollment=target).count(), 0)
        self.assertEqual(LessonMark.objects.filter(enrollment_id__in=[source.pk, second.pk]).count(), 2)

    def test_two_students_share_history_without_cross_student_marks(self):
        source, target = self.transition()
        second_source = Enrollment.objects.create(
            organization=self.org,
            student=self.host,
            offering=self.other_offering,
            status="dropped",
            superseded_by=Enrollment.objects.get(student=self.host, offering=self.offering),
        )
        self.mark(source, 1)
        self.mark(second_source, 2, "present", 7)
        rows = gradebook.get_offering_journal(offering=self.offering)["rows"]
        by_student = {row["enrollment"].student_id: row for row in rows}
        self.assertEqual(by_student[self.guest.pk]["absence_count"], 1)
        self.assertEqual(by_student[self.host.pk]["absence_count"], 0)
        self.assertEqual(by_student[self.host.pk]["carry_over"]["scored"], 1)
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=target), 2)

    def test_unrelated_dropped_history_and_invalid_identity_pointers_do_not_carry(self):
        from django.db import IntegrityError, transaction

        from apps.organizations.models import AcademicPeriod, Organization

        source, target = self.transition()
        self.mark(source, 1)
        Enrollment.objects.filter(pk=source.pk).update(superseded_by=None)
        self.assertEqual(guest_merge.carry_over_map([target.pk]), {})
        period = AcademicPeriod.objects.create(
            organization=self.org,
            name="Next",
            academic_year="2026/2027",
            period_type="semester",
            start_date="2026-09-01",
            end_date="2027-01-31",
        )
        foreign = Organization.objects.create(name="Foreign", slug="carry-foreign", owner=self.owner)
        # Raw legacy pointers may predate clean(); never admit mismatched identities.
        for changes in [
            dict(subject=self.math),
            dict(period=period),
            dict(organization=foreign),
            dict(student=self.host),
        ]:
            identity = dict(organization=self.org, subject=self.history, period=self.period, group=self.group2)
            wrong_student = changes.pop("student", self.guest)
            identity.update(changes)
            try:
                with transaction.atomic():
                    other, _ = CourseOffering.objects.get_or_create(**identity)
                    wrong, _ = Enrollment.objects.get_or_create(
                        organization=identity["organization"],
                        student=wrong_student,
                        offering=other,
                    )
                    Enrollment.objects.filter(pk=wrong.pk).update(status="dropped", superseded_by=target)
                    self.assertEqual(guest_merge.carry_over_map([target.pk]), {})
                    self.assertFalse(
                        annotate_predecessor(Enrollment.objects.filter(pk=target.pk)).get().has_exact_predecessor
                    )
                    Enrollment.objects.filter(pk=wrong.pk).update(superseded_by=None)
            except IntegrityError:
                # A stronger migrated tenant/reference trigger may reject the fixture itself.
                self.assertEqual(guest_merge.carry_over_map([target.pk]), {})
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=target), 0)

    def test_ordinary_roster_annotation_adds_no_query_and_cached_absence_lookup_is_free(self):
        with self.assertNumQueries(1):
            roster = read_memo.enrolled_roster(self.offering)
        with self.assertNumQueries(0):
            for enrollment in roster:
                self.assertFalse(enrollment.has_exact_predecessor)
                self.assertEqual(guest_merge.carried_absence_hours(enrollment), 0)
        with CaptureQueriesContext(connection) as queries:
            gradebook.recompute_absence_hours(enrollment=roster[0])
        # Own-hours aggregation contains the EXISTS; no standalone predecessor read.
        self.assertEqual(sum('FROM "registrar_enrollment"' in q["sql"] for q in queries), 1)
        self.assertIn("superseded_by", str(predecessors().query))


class DuplicateLessonCarryTests(ExactHistoryCarryTests):
    """Sahib 2026-11-08 (135 TSPX): əvvəlki jurnaldakı dərs hədəf jurnalda da (eyni gün + saat + növ) yazılıbsa,
    onun qayıbı ikinci dəfə sayılmır; hədəfdə olmayan dərsin qayıbı köçməyə davam edir."""

    def test_same_lesson_in_target_is_not_carried_twice(self):
        source, target = self.transition()
        self.mark(source, 0)  # 2025-09-01 seminar — hədəfdə də var
        self.mark(source, 1)  # 2025-09-02 seminar — yalnız əvvəlki jurnalda
        self.mark(target, 0)
        self.assertEqual(guest_merge.carried_absence_hours(target), 2)
        self.assertEqual(gradebook.recompute_absence_hours(enrollment=target), 4)
