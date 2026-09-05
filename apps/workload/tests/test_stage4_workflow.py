"""Mərhələ 4 — dərs yükü zənciri: state maşını, əhatə, bildiriş, arxiv.

Zəncir (handoff §6.3):
    TŞ (12) yaradır → koordinator (13) viza/irad → dekan (15) təsdiq/qaytarma
    → kafedra müdiri (14) bölür → müəllim (16) təsdiq/etiraz.

Bu dəst HƏM qanuni, HƏM qanunsuz keçidləri kilidləyir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.workload import state_machine as sm
from apps.workload.constants import (
    ObjectionReason,
    ObjectionStatus,
    RowReviewStatus,
    SliceStatus,
    TaskStatus,
)
from apps.workload.models import LoadObjection, TaskFacultySlice, TaskRowReview
from apps.workload.services import (
    WorkloadDenied,
    approve_slice,
    assign_teacher,
    confirm_distribution,
    confirm_own_load,
    create_objection,
    resolve_actor,
    return_slice,
    review_all,
    review_queue,
    set_row_review,
    slice_progress,
    submit_task,
)

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit", "workload.report"]
COORD_PERMS = ["workload.view", "workload.review"]
DEAN_PERMS = ["workload.view", "workload.approve", "workload.report"]
CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute"]


class StateMachineTest(TestCase):
    """Saf keçid cədvəli — baza olmadan."""

    def test_legal_transitions(self):
        self.assertTrue(sm.can_transition(sm.DRAFT, sm.SUBMITTED))
        self.assertTrue(sm.can_transition(sm.SUBMITTED, sm.RETURNED))
        self.assertTrue(sm.can_transition(sm.RETURNED, sm.SUBMITTED))
        self.assertTrue(sm.can_transition(sm.SUBMITTED, sm.APPROVED))
        self.assertTrue(sm.can_transition(sm.APPROVED, sm.DISTRIBUTING))
        self.assertTrue(sm.can_transition(sm.DISTRIBUTING, sm.DISTRIBUTED))
        self.assertTrue(sm.can_transition(sm.DISTRIBUTED, sm.AMENDED))
        self.assertTrue(sm.can_transition(sm.AMENDED, sm.DISTRIBUTED))

    def test_illegal_transitions(self):
        self.assertFalse(sm.can_transition(sm.DRAFT, sm.APPROVED))
        self.assertFalse(sm.can_transition(sm.DRAFT, sm.DISTRIBUTED))
        self.assertFalse(sm.can_transition(sm.SUBMITTED, sm.DISTRIBUTING))
        self.assertFalse(sm.can_transition(sm.CANCELLED, sm.DRAFT))
        self.assertFalse(sm.can_transition(sm.DISTRIBUTED, sm.SUBMITTED))
        with self.assertRaises(sm.IllegalTransition):
            sm.ensure_transition(sm.DRAFT, sm.DISTRIBUTED)


class ChainBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("ds4")
        cls.stack = make_structure(cls.org, code="DS4")
        cls.office = User.objects.create_user("ds4.office", "office@x.test", "pw")
        cls.coordinator = User.objects.create_user("ds4.coord", "coord@x.test", "pw")
        cls.dean = User.objects.create_user("ds4.dean", "dean@x.test", "pw")
        cls.chair_head = User.objects.create_user("ds4.chair", "chair@x.test", "pw")
        cls.teacher = User.objects.create_user("ds4.teacher", "teacher@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)
        activate_member(
            cls.org,
            cls.coordinator,
            "program_coordinator",
            permissions=COORD_PERMS,
            scope_unit=cls.stack["specialty"],
            scope_type="unit",
            level=45,
        )
        activate_member(
            cls.org,
            cls.dean,
            "dean",
            permissions=DEAN_PERMS,
            scope_unit=cls.stack["faculty"],
            scope_type="unit",
            level=70,
        )
        activate_member(
            cls.org,
            cls.chair_head,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.stack["chair"],
            scope_type="unit",
            level=60,
        )
        activate_member(
            cls.org,
            cls.teacher,
            "teacher",
            permissions=TEACHER_PERMS + ["workload.object"],
            scope_unit=cls.stack["chair"],
            scope_type="unit",
            level=30,
        )

    def actor(self, user):
        return resolve_actor(user, self.org)

    def fresh_task(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, self.stack)
        return task

    def visa_all(self, user=None):
        """Koordinator vizası — dekan təsdiqi bunsuz bağlıdır (P2-36)."""
        return review_all(actor=self.actor(user or self.coordinator))


class SubmitTest(ChainBase):
    def test_submit_creates_one_slice_per_faculty(self):
        task = self.fresh_task()
        result = submit_task(task=task, actor=self.actor(self.office))
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.SUBMITTED)
        self.assertEqual(result["slices"], 1)
        self.assertEqual(TaskFacultySlice.objects.filter(task=task, faculty=self.stack["faculty"]).count(), 1)

    def test_submit_is_denied_without_the_submit_permission(self):
        task = self.fresh_task()
        with self.assertRaises(WorkloadDenied) as ctx:
            submit_task(task=task, actor=self.actor(self.chair_head))
        self.assertEqual(ctx.exception.code, "workload.submit_denied")

    def test_empty_document_is_not_submitted(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        with self.assertRaises(WorkloadDenied) as ctx:
            submit_task(task=task, actor=self.actor(self.office))
        self.assertEqual(ctx.exception.code, "workload.no_faculty_slice")

    def test_resubmitting_an_already_submitted_document_is_illegal(self):
        task = self.fresh_task()
        submit_task(task=task, actor=self.actor(self.office))
        task.refresh_from_db()
        with self.assertRaises(sm.IllegalTransition):
            submit_task(task=task, actor=self.actor(self.office))


class ReviewTest(ChainBase):
    def setUp(self):
        self.task = self.fresh_task()
        self.row = self.task.rows.first()
        submit_task(task=self.task, actor=self.actor(self.office))
        self.task.refresh_from_db()

    def test_coordinator_sees_only_own_specialty(self):
        rows = review_queue(actor=self.actor(self.coordinator), academic_year=YEAR)
        self.assertEqual(list(rows), [self.row])

    def test_other_specialty_is_denied(self):
        other = make_structure(self.org, code="OTHER")
        other_task = make_task(self.org, other["chair"], created_by=self.office)
        other_row = make_row(other_task, other)
        submit_task(task=other_task, actor=self.actor(self.office))
        self.assertNotIn(other_row, list(review_queue(actor=self.actor(self.coordinator), academic_year=YEAR)))
        with self.assertRaises(WorkloadDenied) as ctx:
            set_row_review(row=other_row, actor=self.actor(self.coordinator), status=RowReviewStatus.REVIEWED)
        self.assertEqual(ctx.exception.code, "workload.review_denied")

    def test_visa_marks_the_row_reviewed(self):
        set_row_review(row=self.row, actor=self.actor(self.coordinator), status=RowReviewStatus.REVIEWED)
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_status, RowReviewStatus.REVIEWED)

    def test_remark_clears_the_reviewed_flag(self):
        """Handoff §5/13: sətir eyni anda həm vizalanmış, həm iradlı ola bilməz."""
        set_row_review(row=self.row, actor=self.actor(self.coordinator), status=RowReviewStatus.REVIEWED)
        set_row_review(
            row=self.row,
            actor=self.actor(self.coordinator),
            status=RowReviewStatus.FLAGGED,
            comment="Qrup sayı ixtisas planı ilə uyğun gəlmir, yenidən yoxlanılsın.",
        )
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_status, RowReviewStatus.FLAGGED)
        self.assertEqual(TaskRowReview.objects.filter(row=self.row).count(), 1)

    def test_remark_requires_a_comment(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            set_row_review(
                row=self.row, actor=self.actor(self.coordinator), status=RowReviewStatus.FLAGGED, comment="qısa"
            )
        self.assertEqual(ctx.exception.code, "workload.reason_too_short")

    def test_review_is_closed_once_the_document_leaves_the_review_stage(self):
        slice_obj = TaskFacultySlice.objects.get(task=self.task)
        self.visa_all()
        approve_slice(slice_obj=slice_obj, actor=self.actor(self.dean))
        fresh_row = self.row.__class__.objects.select_related("task").get(pk=self.row.pk)
        with self.assertRaises(WorkloadDenied) as ctx:
            set_row_review(row=fresh_row, actor=self.actor(self.coordinator), status=RowReviewStatus.REVIEWED)
        self.assertEqual(ctx.exception.code, "workload.review_closed")


class DeanDecisionTest(ChainBase):
    def setUp(self):
        self.task = self.fresh_task()
        self.row = self.task.rows.first()
        submit_task(task=self.task, actor=self.actor(self.office))
        self.task.refresh_from_db()
        self.slice = TaskFacultySlice.objects.get(task=self.task)

    def test_approving_every_slice_approves_the_document(self):
        self.visa_all()
        result = approve_slice(slice_obj=self.slice, actor=self.actor(self.dean))
        self.task.refresh_from_db()
        self.assertEqual(self.slice.__class__.objects.get(pk=self.slice.pk).status, SliceStatus.APPROVED)
        self.assertEqual(self.task.status, TaskStatus.APPROVED)
        self.assertEqual(result["approved"], result["total"])

    def test_partial_approval_keeps_the_document_submitted(self):
        """İki fakültə diliminin BİRİ təsdiqlənəndə sənəd hələ `submitted`-dır."""
        other = make_structure(self.org, code="X2")
        make_row(self.task, other)
        self.task.status = TaskStatus.DRAFT
        self.task.save(update_fields=["status"])
        TaskFacultySlice.objects.filter(task=self.task).delete()
        submit_task(task=self.task, actor=self.actor(self.office))
        self.task.refresh_from_db()
        self.assertEqual(slice_progress(self.task)["total"], 2)

        first = TaskFacultySlice.objects.get(task=self.task, faculty=self.stack["faculty"])
        self.visa_all()
        approve_slice(slice_obj=first, actor=self.actor(self.dean))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SUBMITTED)

        second_dean = User.objects.create_user("ds4.dean_x2", "deanx2@x.test", "pw")
        activate_member(
            self.org,
            second_dean,
            "dean_x2",
            permissions=DEAN_PERMS,
            scope_unit=other["faculty"],
            scope_type="unit",
        )
        second = TaskFacultySlice.objects.get(task=self.task, faculty=other["faculty"])
        self.visa_all()
        approve_slice(slice_obj=second, actor=self.actor(second_dean))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.APPROVED)

    def test_dean_of_another_faculty_is_denied(self):
        other = make_structure(self.org, code="F2")
        stranger = User.objects.create_user("ds4.dean2", "dean2@x.test", "pw")
        activate_member(
            self.org, stranger, "dean2", permissions=DEAN_PERMS, scope_unit=other["faculty"], scope_type="unit"
        )
        with self.assertRaises(WorkloadDenied) as ctx:
            self.visa_all()
            approve_slice(slice_obj=self.slice, actor=self.actor(stranger))
        self.assertEqual(ctx.exception.code, "workload.approve_denied")

    def test_return_requires_a_reason_and_marks_rows(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            return_slice(slice_obj=self.slice, actor=self.actor(self.dean), reason="qısa")
        self.assertEqual(ctx.exception.code, "workload.reason_too_short")

        result = return_slice(
            slice_obj=self.slice,
            actor=self.actor(self.dean),
            reason="Qrup sayı ixtisas planı ilə uyğun gəlmir — birləşmə yenidən yoxlanılsın.",
        )
        self.task.refresh_from_db()
        self.row.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.RETURNED)
        self.assertEqual(self.row.review_status, RowReviewStatus.RETURNED)
        self.assertEqual(result["returned_rows"], 1)

    def test_returned_document_can_be_edited_and_resubmitted(self):
        return_slice(
            slice_obj=self.slice,
            actor=self.actor(self.dean),
            reason="Saat bölgüsü düzəldilməlidir — mühazirə cəmi plan ilə uyğun deyil.",
        )
        self.task.refresh_from_db()
        result = submit_task(task=self.task, actor=self.actor(self.office))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.SUBMITTED)
        self.assertEqual(self.task.revision, 1)
        self.assertEqual(result["slices"], 1)
        self.row.refresh_from_db()
        self.assertEqual(self.row.review_status, RowReviewStatus.PENDING)
        # Köhnə qərar TARİXÇƏ kimi qalır (silinmir).
        self.assertEqual(TaskFacultySlice.objects.filter(task=self.task).count(), 2)

    def test_stale_revision_slice_cannot_be_decided(self):
        """QA dalğa 2 (2026-09-03) reqressiyası — köhnəlmiş dilim qərarı.

        Dilim qaytarılıb sənəd YENİDƏN göndəriləndə cari revision üçün yeni
        dilim yaranır, köhnəsi tarixçə kimi qalır.  Əvvəllər dekan həmin KÖHNƏ
        dilimi təsdiqləyə bilirdi: `ok: true` qayıdır, audit «təsdiqləndi»
        yazır, LAKİN `slice_progress` yalnız cari revision-u saydığı üçün sənəd
        irəliləmirdi — sükutla itən qərar.  İndi 409 (`stale_revision`).
        """
        stale = self.slice
        return_slice(
            slice_obj=stale,
            actor=self.actor(self.dean),
            reason="Saat bölgüsü düzəldilməlidir — mühazirə cəmi plan ilə uyğun deyil.",
        )
        self.task.refresh_from_db()
        submit_task(task=self.task, actor=self.actor(self.office))
        self.task.refresh_from_db()
        stale.refresh_from_db()
        self.assertNotEqual(stale.revision, self.task.revision)

        with self.assertRaises(WorkloadDenied) as ctx:
            self.visa_all()
            approve_slice(slice_obj=stale, actor=self.actor(self.dean), comment="köhnə dilim")
        self.assertEqual(ctx.exception.code, "workload.stale_revision")

        with self.assertRaises(WorkloadDenied) as ctx:
            return_slice(
                slice_obj=stale,
                actor=self.actor(self.dean),
                reason="Köhnəlmiş dilimi qaytarmaq da mümkün olmamalıdır.",
            )
        self.assertEqual(ctx.exception.code, "workload.stale_revision")

        # CARİ revision-un dilimi normal işləyir.
        current = TaskFacultySlice.objects.get(task=self.task, revision=self.task.revision)
        self.visa_all()
        approve_slice(slice_obj=current, actor=self.actor(self.dean), comment="cari dilim")
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.APPROVED)


class DistributionGateTest(ChainBase):
    def test_chair_cannot_distribute_before_the_deanery_approves(self):
        task = self.fresh_task()
        row = task.rows.first()
        submit_task(task=task, actor=self.actor(self.office))
        task.refresh_from_db()
        row.refresh_from_db()
        with self.assertRaises(WorkloadDenied) as ctx:
            assign_teacher(
                row=row, actor=self.actor(self.chair_head), activity="lecture", teacher_id=self.teacher.pk, hours=10
            )
        self.assertEqual(ctx.exception.code, "workload.not_approved_yet")

    def test_chair_distributes_after_approval(self):
        task = self.fresh_task()
        row = task.rows.first()
        submit_task(task=task, actor=self.actor(self.office))
        task.refresh_from_db()
        self.visa_all()
        approve_slice(slice_obj=TaskFacultySlice.objects.get(task=task), actor=self.actor(self.dean))
        task.refresh_from_db()
        row.refresh_from_db()
        assign_teacher(
            row=row, actor=self.actor(self.chair_head), activity="lecture", teacher_id=self.teacher.pk, hours=30
        )
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.DISTRIBUTING)

    def test_legacy_chair_created_draft_still_distributes(self):
        """F1-dən ƏVVƏLKİ sənəd (heç vaxt göndərilməyib) işləməyə davam edir."""
        task = self.fresh_task()
        row = task.rows.first()
        assign_teacher(
            row=row, actor=self.actor(self.chair_head), activity="lecture", teacher_id=self.teacher.pk, hours=10
        )
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.DISTRIBUTING)


class ObjectionTest(ChainBase):
    def setUp(self):
        self.task = self.fresh_task()
        self.row = self.task.rows.first()
        submit_task(task=self.task, actor=self.actor(self.office))
        self.task.refresh_from_db()
        self.visa_all()
        approve_slice(slice_obj=TaskFacultySlice.objects.get(task=self.task), actor=self.actor(self.dean))
        self.task.refresh_from_db()
        self.row.refresh_from_db()
        self.assignment = assign_teacher(
            row=self.row,
            actor=self.actor(self.chair_head),
            activity="lecture",
            teacher_id=self.teacher.pk,
            hours=30,
        )
        assign_teacher(
            row=self.row, actor=self.actor(self.chair_head), activity="seminar", teacher_id=self.teacher.pk, hours=30
        )
        self.task.refresh_from_db()
        confirm_distribution(task=self.task, actor=self.actor(self.chair_head))
        self.task.refresh_from_db()

    def test_teacher_objects_with_one_of_the_four_reasons(self):
        objection = create_objection(
            actor=self.actor(self.teacher),
            assignment_id=self.assignment.pk,
            reason_key=ObjectionReason.HOURS,
            text="Mühazirə saatı 30 deyil, 15 olmalıdır — plan sətri belə deyil.",
        )
        self.assertEqual(objection.status, ObjectionStatus.OPEN)
        self.assertEqual(LoadObjection.objects.filter(row=self.row).count(), 1)

    def test_objection_needs_a_valid_reason_key(self):
        with self.assertRaises(WorkloadDenied) as ctx:
            create_objection(
                actor=self.actor(self.teacher),
                assignment_id=self.assignment.pk,
                reason_key="uydurma",
                text="Bu səbəb kataloqda yoxdur, ona görə rədd edilməlidir.",
            )
        self.assertEqual(ctx.exception.code, "workload.invalid_reason")

    def test_teacher_cannot_object_to_someone_elses_row(self):
        stranger = User.objects.create_user("ds4.teacher2", "t2@x.test", "pw")
        activate_member(self.org, stranger, "teacher2", permissions=TEACHER_PERMS + ["workload.object"], level=30)
        with self.assertRaises(WorkloadDenied) as ctx:
            create_objection(
                actor=self.actor(stranger),
                assignment_id=self.assignment.pk,
                reason_key=ObjectionReason.NORM,
                text="Bu sətir mənim yüküm deyil — etiraz rədd edilməlidir.",
            )
        self.assertEqual(ctx.exception.code, "workload.objection_denied")

    def test_confirmation_is_recorded_on_the_profile(self):
        result = confirm_own_load(actor=self.actor(self.teacher), academic_year=YEAR)
        self.assertIsNotNone(result["confirmed_at"])

    def test_chair_sees_the_objection(self):
        from apps.workload.services import chair_objections

        create_objection(
            actor=self.actor(self.teacher),
            assignment_id=self.assignment.pk,
            reason_key=ObjectionReason.SUBJECT,
            text="Bu fənn mənim ixtisasım deyil — başqa müəllimə verilməlidir.",
        )
        self.assertEqual(len(list(chair_objections(task=self.task))), 1)
