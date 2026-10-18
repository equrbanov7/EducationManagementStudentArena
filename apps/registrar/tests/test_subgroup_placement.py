"""Semestr kredit yükü + «Alt qrupa yerləşdirmə» servisi (sahib 2026-10-18).

Yoxlanılır: kredit hesabı (öz / alt qrup / azad / geri götürülmüş / plan override), ``place_in_subgroup``-un
HƏR imtina kodu, uğurlu yol (tarixçə, sənəd, audit, bildiriş, jurnal çipi, cədvəl), təkrar keçid (``retake``),
birləşmə, geri götürmə, append-only qoruyucu və sorğu büdcələri.
"""

from __future__ import annotations

from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import RuntimeSetting
from apps.audit.models import AuditLog
from apps.notifications.models import InAppNotification
from apps.registrar import credit_load, gradebook, schedule, subgroup_placement_query
from apps.registrar.models import (
    AcademicStatus,
    AssessmentScheme,
    CurriculumSubject,
    Enrollment,
    EnrollmentKind,
    GuestRosterDocument,
    StudentAcademicRecord,
    SubgroupPlacementEvent,
)
from apps.registrar.public import (
    PlacementDocument,
    SubgroupPlacementError,
)
from apps.registrar.public import credit_load as public_credit_load
from apps.registrar.public import place_in_subgroup, undo_subgroup_placement
from apps.registrar.tests.subgroup_base import SubgroupFixture, pdf
from core import runtime_settings as rs
from core.rls import bypass_rls

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "subgroup-place"}}
REASON = "Dekanlığın təqdimatı əsasında alt qrupa yerləşdirmə"


def _settings(**values):
    RuntimeSetting.objects.all().delete()
    for key, value in values.items():
        RuntimeSetting.objects.create(key=key, value=value)
    rs.invalidate()


class _Base(SubgroupFixture, TestCase):
    PREFIX = "sgp"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()

    def place(self, offering=None, *, actor=None, document="pdf", reason=REASON, **kwargs):
        with bypass_rls():
            return place_in_subgroup(
                student=kwargs.pop("student", self.student),
                offering=offering or self.physics_g1,
                document=pdf() if document == "pdf" else document,
                actor=actor or self.dean,
                reason=reason,
                **kwargs,
            )

    def assertCode(self, code, **kwargs):  # noqa: N802
        with self.assertRaises(SubgroupPlacementError) as caught:
            self.place(**kwargs)
        self.assertEqual(caught.exception.code, code, caught.exception.message)
        return caught.exception


class CreditLoadTest(_Base):
    def test_own_group_load_and_default_limits(self):
        with bypass_rls():
            load = public_credit_load(self.student, self.period)
        self.assertEqual((load["total"], load["own"], load["subgroup"]), (10, 10, 0))
        self.assertEqual((load["limit"], load["remaining"]), (30, 20))
        self.assertFalse(load["over_limit"])

    def test_plan_row_credits_override_catalog(self):
        with bypass_rls():
            CurriculumSubject.objects.filter(curriculum=self.curriculum, subject=self.math).update(credits=8)
            load = credit_load.credit_load(self.student, self.period)
        self.assertEqual(load["own"], 13)

    def test_subgroup_credits_counted_with_subgroup_limit(self):
        self.place()
        with bypass_rls():
            load = credit_load.credit_load(self.student, self.period)
        self.assertEqual((load["total"], load["own"], load["subgroup"]), (16, 10, 6))
        self.assertEqual(load["limit"], 36)
        self.assertEqual(len(load["subgroup_enrollment_ids"]), 1)

    def test_exempt_dropped_and_suspended_rows_are_not_counted(self):
        with bypass_rls():
            Enrollment.objects.filter(student=self.student, offering=self.own_math).update(
                status=Enrollment.Status.DROPPED
            )
            self.assertEqual(credit_load.credit_load(self.student, self.period)["total"], 5)
            Enrollment.objects.filter(student=self.student, offering=self.own_history).update(
                status=Enrollment.Status.SUSPENDED
            )
            self.assertEqual(credit_load.credit_load(self.student, self.period)["total"], 0)

    def test_without_record_load_is_empty(self):
        with bypass_rls():
            load = credit_load.credit_load(self.teacher, self.period)
        self.assertFalse(load["has_record"])
        self.assertEqual(load["total"], 0)

    @override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
    def test_limits_follow_runtime_settings(self):
        _settings(**{"credits.max_per_semester": 24, "credits.max_with_subgroup": 0})
        try:
            self.assertEqual(credit_load.limits(), {"base": 24, "with_subgroup": 24})
        finally:
            rs.invalidate()

    def test_query_budget_is_constant(self):
        with bypass_rls():
            record = credit_load.active_record(self.student, self.org)
            with CaptureQueriesContext(connection) as small:
                credit_load.credit_load(self.student, self.period, record=record)
            self.place()
            with CaptureQueriesContext(connection) as large:
                credit_load.credit_load(self.student, self.period, record=record)
        self.assertLessEqual(len(small), 2, [q["sql"][:120] for q in small.captured_queries])
        self.assertEqual(len(small), len(large))


class PlacementFailureCodesTest(_Base):
    def test_forbidden_without_key(self):
        self.assertCode("forbidden", actor=self.plain)

    def test_out_of_scope_dean(self):
        self.assertCode("out_of_scope", actor=self.far_dean)

    def test_inactive_student(self):
        with bypass_rls():
            StudentAcademicRecord.objects.filter(pk=self.record.pk).update(status=AcademicStatus.ACADEMIC_LEAVE)
        self.assertCode("student_inactive")

    def test_inactive_offering(self):
        with bypass_rls():
            type(self.physics_g1).objects.filter(pk=self.physics_g1.pk).update(is_active=False)
        self.assertCode("offering_inactive")

    def test_closed_roster(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.physics_g1)
            AssessmentScheme.objects.filter(pk=scheme.pk).update(is_published=True, approval_status="approved")
        self.assertCode("roster_closed")

    def test_own_group_journal(self):
        self.assertCode("own_group", offering=self.own_history)

    def test_already_enrolled(self):
        self.place()
        self.assertCode("already_enrolled")

    def test_active_elsewhere_without_release(self):
        self.assertCode("active_elsewhere", offering=self.history_g1)

    def test_already_passed(self):
        passed = {self.physics.pk: {"passed": True, "failed": False}}
        with mock.patch.object(subgroup_placement_query, "subject_outcomes", return_value=passed):
            self.assertCode("already_passed")

    def test_credit_limit(self):
        with mock.patch.object(credit_load, "limits", return_value={"base": 10, "with_subgroup": 12}):
            error = self.assertCode("credit_limit")
        self.assertIn("16", error.message)
        self.assertIn("12", error.message)

    @override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
    def test_capacity_full(self):
        _settings(**{"credits.journal_capacity": 1})
        try:
            self.assertCode("capacity_full")
        finally:
            rs.invalidate()

    @override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
    def test_schedule_clash_blocks_when_configured(self):
        self.slot(self.own_math, weekday=1, start=(9, 0), end=(10, 20))
        self.slot(self.physics_g1, weekday=1, start=(9, 30), end=(10, 50))
        _settings(**{"credits.clash_blocks": True})
        try:
            self.assertCode("schedule_clash")
        finally:
            rs.invalidate()

    def test_document_required(self):
        self.assertCode("document_required", document=None)
        self.assertCode("document_required", document={"number": "123-S"})

    def test_document_invalid(self):
        fake = SimpleUploadedFile("teqdimat.pdf", b"hello world", content_type="application/pdf")
        self.assertCode("document_invalid", document=fake)
        docx = SimpleUploadedFile("teqdimat.docx", b"PK\x03\x04data", content_type="application/octet-stream")
        self.assertCode("document_invalid", document=docx)
        self.assertCode("document_invalid", document={"number": "12", "date": "2999-01-01"})

    def test_reason_required(self):
        self.assertCode("reason_required", reason="qısa")

    def test_nothing_written_on_failure(self):
        with mock.patch.object(credit_load, "limits", return_value={"base": 10, "with_subgroup": 12}):
            self.assertCode("credit_limit")
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student=self.student, offering=self.physics_g1).exists())
            self.assertFalse(SubgroupPlacementEvent.objects.exists())
            self.assertFalse(GuestRosterDocument.objects.exists())


class PlacementHappyPathTest(_Base):
    def test_place_writes_enrollment_event_document_audit_and_notifications(self):
        with self.captureOnCommitCallbacks(execute=True):
            result = self.place()
        with bypass_rls():
            event = SubgroupPlacementEvent.objects.get()
            enrollment = result["enrollment"]
            self.assertEqual(enrollment.source_group_id, self.group2.id)
            self.assertEqual(enrollment.added_by_id, self.dean.id)
            self.assertEqual(enrollment.kind, EnrollmentKind.MANDATORY)
            self.assertEqual((event.credits_before, event.credits_after, event.credit_limit), (10, 16, 36))
            self.assertEqual(event.source_group_id, self.group2.id)
            self.assertEqual(event.target_group_id, self.group1.id)
            document = event.document
            self.assertIsNotNone(document)
            self.assertNotIn("teqdimat", document.document.name)
            self.assertTrue(document.document.name.endswith(".pdf"))
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="registrar.subgroup_placement", resource_id=str(event.pk)
                ).exists()
            )
            recipients = set(InAppNotification.objects.values_list("recipient_id", flat=True))
            self.assertEqual(recipients, {self.student.id, self.teacher.id})
            journal = gradebook.get_offering_journal(offering=self.physics_g1)
            rows = {row["student"].id: row for row in journal["rows"]}
            self.assertTrue(rows[self.student.id]["is_guest"])
            slot = self.slot(self.physics_g1, weekday=3)
            student_slots = schedule.get_student_schedule(self.org, self.student, self.group2, self.period)
            self.assertIn(slot.pk, [s.pk for s in student_slots])

    def test_order_number_and_date_without_file(self):
        result = self.place(document={"number": "Əmr 45/S", "date": "2025-09-10"})
        with bypass_rls():
            event = SubgroupPlacementEvent.objects.get(pk=result["event"].pk)
        self.assertIsNone(event.document_id)
        self.assertEqual(event.order_number, "Əmr 45/S")
        self.assertEqual(event.order_date.isoformat(), "2025-09-10")

    def test_placement_document_dataclass(self):
        result = self.place(document=PlacementDocument(file=pdf(), number="77"))
        self.assertIsNotNone(result["event"].document_id)

    def test_failed_subject_is_placed_as_retake(self):
        failed = {self.physics.pk: {"passed": False, "failed": True}}
        with mock.patch.object(subgroup_placement_query, "subject_outcomes", return_value=failed):
            result = self.place()
        self.assertTrue(result["retake"])
        self.assertEqual(result["enrollment"].kind, EnrollmentKind.RETAKE)

    def test_clash_is_a_warning_by_default(self):
        self.slot(self.own_math, weekday=1, start=(9, 0), end=(10, 20))
        self.slot(self.physics_g1, weekday=1, start=(9, 30), end=(10, 50))
        self.slot(self.physics_g1, weekday=2, start=(9, 30), end=(10, 50), week_type="odd")
        result = self.place()
        self.assertEqual([w["code"] for w in result["warnings"]], ["schedule_clash"])
        self.assertEqual(len(result["event"].details["clashes"]), 1)

    def test_odd_and_even_weeks_do_not_clash(self):
        self.slot(self.own_math, weekday=1, week_type="even")
        self.slot(self.physics_g1, weekday=1, week_type="odd")
        self.assertEqual(self.place()["warnings"], [])

    def test_release_source_merge_keeps_credit_and_hides_own_slot(self):
        own_slot = self.slot(self.own_history, weekday=4)
        self.slot(self.history_g1, weekday=4)
        result = self.place(self.history_g1, release_source=True)
        self.assertTrue(result["released"])
        with bypass_rls():
            own = Enrollment.objects.get(student=self.student, offering=self.own_history)
            self.assertEqual(own.status, Enrollment.Status.DROPPED)
            self.assertEqual(own.superseded_by_id, result["enrollment"].id)
            self.assertEqual(credit_load.credit_load(self.student, self.period)["total"], 10)
            slots = schedule.get_student_schedule(self.org, self.student, self.group2, self.period)
        self.assertNotIn(own_slot.pk, [s.pk for s in slots])
        self.assertEqual(result["warnings"], [])

    def test_org_wide_actor_can_place_any_student(self):
        result = self.place(actor=self.org_admin)
        self.assertEqual(result["event"].actor_id, self.org_admin.id)


class PlacementUndoTest(_Base):
    def test_undo_drops_enrollment_and_keeps_history(self):
        placed = self.place()
        with self.captureOnCommitCallbacks(execute=True), bypass_rls():
            undone = undo_subgroup_placement(
                event_id=placed["event"].pk,
                actor=self.dean,
                reason="Səhv yerləşdirmə — geri götürülür",
                organization=self.org,
            )
        with bypass_rls():
            enrollment = Enrollment.objects.get(pk=placed["enrollment"].pk)
            self.assertEqual(enrollment.status, Enrollment.Status.DROPPED)
            self.assertEqual(SubgroupPlacementEvent.objects.count(), 2)
            self.assertEqual(undone["event"].undoes_id, placed["event"].pk)
            self.assertEqual((undone["event"].credits_before, undone["event"].credits_after), (16, 10))
            self.assertEqual(credit_load.credit_load(self.student, self.period)["total"], 10)
            self.assertTrue(GuestRosterDocument.objects.filter(enrollment=enrollment).exists())
            self.assertEqual(InAppNotification.objects.filter(recipient=self.student).count(), 1)

    def test_undo_twice_and_out_of_scope(self):
        placed = self.place()
        with bypass_rls():
            with self.assertRaises(SubgroupPlacementError) as caught:
                undo_subgroup_placement(
                    event_id=placed["event"].pk,
                    actor=self.far_dean,
                    reason="Başqa fakültədən cəhd",
                    organization=self.org,
                )
            self.assertEqual(caught.exception.code, "not_found")
            undo_subgroup_placement(event_id=placed["event"].pk, actor=self.dean, reason=REASON, organization=self.org)
            with self.assertRaises(SubgroupPlacementError) as caught:
                undo_subgroup_placement(
                    event_id=placed["event"].pk, actor=self.dean, reason=REASON, organization=self.org
                )
            self.assertEqual(caught.exception.code, "already_undone")

    def test_undo_then_place_again(self):
        placed = self.place()
        with bypass_rls():
            undo_subgroup_placement(event_id=placed["event"].pk, actor=self.dean, reason=REASON, organization=self.org)
        again = self.place()
        self.assertEqual(again["enrollment"].pk, placed["enrollment"].pk)
        self.assertEqual(again["enrollment"].status, Enrollment.Status.ENROLLED)

    def test_undo_restores_merged_source(self):
        placed = self.place(self.history_g1, release_source=True)
        with bypass_rls():
            undo_subgroup_placement(event_id=placed["event"].pk, actor=self.dean, reason=REASON, organization=self.org)
            own = Enrollment.objects.get(student=self.student, offering=self.own_history)
        self.assertEqual(own.status, Enrollment.Status.ENROLLED)
        self.assertIsNone(own.superseded_by_id)


class PlacementImmutabilityTest(_Base):
    def test_event_cannot_be_changed_or_deleted(self):
        event = self.place()["event"]
        event.reason = "dəyişdirilmiş səbəb mətni"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()

    def test_database_guard_rejects_raw_update(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL trigger")
        from django.db import DatabaseError, transaction

        event = self.place()["event"]
        with bypass_rls(), self.assertRaises(DatabaseError), transaction.atomic():
            SubgroupPlacementEvent.objects.filter(pk=event.pk).update(reason="saxtalaşdırılmış səbəb")


class CandidateOfferingsQueryTest(_Base):
    def test_candidates_show_credits_clashes_and_constant_queries(self):
        self.slot(self.own_math, weekday=1, start=(9, 0), end=(10, 20))
        self.slot(self.physics_g1, weekday=1, start=(9, 30), end=(10, 50))
        with bypass_rls():
            record = credit_load.active_record(self.student, self.org)
            with CaptureQueriesContext(connection) as first:
                rows = subgroup_placement_query.candidate_offerings(
                    organization=self.org,
                    student=self.student,
                    record=record,
                    subject_id=self.physics.pk,
                    period=self.period,
                )
            from apps.registrar.models import CourseOffering

            for group in (self.far_group,):
                extra = CourseOffering.objects.create(
                    organization=self.org,
                    subject=self.physics,
                    period=self.period,
                    group=group,
                    instructor=self.teacher,
                )
                self.slot(extra, weekday=2)
            with CaptureQueriesContext(connection) as second:
                more = subgroup_placement_query.candidate_offerings(
                    organization=self.org,
                    student=self.student,
                    record=record,
                    subject_id=self.physics.pk,
                    period=self.period,
                )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["credits"], 6)
        self.assertEqual(rows[0]["enrolled"], 1)
        self.assertEqual(len(rows[0]["clashes"]), 1)
        self.assertEqual(len(more), 2)
        self.assertEqual(len(first), len(second))
