"""Kafedra köçürməsi: iki tərəfli RBAC, rəsmi düzəliş, dəyişməz jurnal və bölgü."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, Lesson, LessonMark
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.constants import TaskStatus
from apps.workload.models import LoadObjection, TaskFacultySlice, TaskRowReview, TeacherAssignment, WorkloadAmendment
from apps.workload.services import resolve_actor
from apps.workload.services import row_transfer as service
from apps.workload.services.repair_fingerprints import academic_fingerprint
from apps.workload.services.sbio235_state import records
from apps.workload.services.scoping import WorkloadDenied
from apps.workload.views.row_transfer_api import row_transfer, row_transfer_destinations
from core.constants import RoleScopeType
from core.rls import apply_rls_request_context, reset_rls_context

from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()
PERMS = ["workload.view", "workload.manage", "workload.distribute"]
AMEND = {"reason": "correction", "note": "Dərs yükü səhv kafedraya daxil edilib, düzgün kafedraya köçürülür."}


@override_settings(RLS_TRANSACTION_SCOPED=True)
class RowTransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("transfer_admin", "admin@x.test", "pw")
        cls.org = make_org("row-transfer", owner=cls.admin)
        cls.stack = make_structure(cls.org, code="TRANSFER")
        cls.target_chair = OrgUnit.objects.create(
            organization=cls.org,
            name="Marketinq",
            slug="tf-target",
            unit_type="chair",
            parent=cls.stack["faculty"],
        )
        cls.source = make_task(cls.org, cls.stack["chair"], status=TaskStatus.DISTRIBUTED)
        cls.target = make_task(cls.org, cls.target_chair, status=TaskStatus.DISTRIBUTED)
        cls.row = make_row(cls.source, cls.stack, lecture_total=45, seminar_total=30)
        cls.teacher = User.objects.create_user("transfer_teacher")
        activate_member(
            cls.org,
            cls.teacher,
            "teacher",
            permissions=TEACHER_PERMS,
            scope_unit=cls.stack["chair"],
            scope_type=RoleScopeType.COURSE,
        )
        cls.primary = Membership.objects.get(user=cls.teacher, role__name="teacher")
        cls.primary.is_primary = True
        cls.primary.save(update_fields=["is_primary"])
        cls.teacher2 = User.objects.create_user("transfer_teacher2")
        Membership.objects.create(
            organization=cls.org,
            user=cls.teacher2,
            role=cls.primary.role,
            scope_unit=cls.stack["chair"],
            is_primary=True,
            is_active=True,
        )
        for activity, teacher, hours in (("lecture", cls.teacher, 45), ("seminar", cls.teacher2, 30)):
            TeacherAssignment.objects.create(
                organization=cls.org,
                row=cls.row,
                activity=activity,
                teacher=teacher,
                hours=hours,
                groups_note="534Bİ az 1+2",
                note="mənbə qeydi",
            )
        cls.journal = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            period=cls.stack["period"],
            group=cls.stack["group"],
            instructor=cls.teacher,
            lesson_hours=75,
        )
        JournalShare.objects.create(organization=cls.org, offering=cls.journal, teacher=cls.teacher2, is_active=True)
        cls.student = User.objects.create_user("transfer_student")
        Membership.objects.create(
            organization=cls.org,
            user=cls.student,
            role=cls.org.roles.get(name="student"),
            scope_unit=cls.stack["group"],
            is_active=True,
        )
        enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.journal, student=cls.student)
        cls.lesson = Lesson.objects.create(
            organization=cls.org,
            offering=cls.journal,
            date="2026-10-20",
            kind="seminar",
            hours=2,
            instructor=cls.teacher2,
        )
        cls.mark = LessonMark.objects.create(
            organization=cls.org,
            lesson=cls.lesson,
            enrollment=enrollment,
            score=9,
            status="present",
            entered_by=cls.teacher2,
        )
        syllabus = Syllabus.objects.create(
            organization=cls.org,
            subject=cls.stack["subject"],
            offering=cls.journal,
            period=cls.stack["period"],
            author=cls.teacher,
            chair_unit=cls.stack["chair"],
        )
        version = SyllabusVersion.objects.create(
            organization=cls.org,
            syllabus=syllabus,
            status="approved",
            approved_by=cls.admin,
            approved_at=timezone.now(),
            locked_at=timezone.now(),
            plan_hours={"lecture": 45, "seminar": 30},
        )
        SyllabusSection.objects.create(
            organization=cls.org, version=version, section_id="week", data={"rows": [{"topic": "keep"}]}
        )
        syllabus.current_version = syllabus.approved_version = version
        syllabus.save(update_fields=["current_version", "approved_version"])
        cls.review = TaskRowReview.objects.create(
            organization=cls.org,
            row=cls.row,
            coordinator=cls.admin,
            status="reviewed",
            comment="Koordinator vizası saxlanılır",
        )
        cls.objection = LoadObjection.objects.create(
            organization=cls.org,
            row=cls.row,
            teacher=cls.teacher,
            reason_key="hours",
            text="Mövcud etiraz tarixçəsi saxlanılır.",
        )

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        self.actor = resolve_actor(self.admin, self.org)

    def tearDown(self):
        reset_rls_context()

    def transfer(self, **kwargs):
        options = dict(
            actor=self.actor,
            row_id=self.row.pk,
            source_task_id=self.source.pk,
            destination_chair_id=self.target_chair.pk,
            amend=AMEND,
        )
        options.update(kwargs)
        return service.transfer_row(**options)

    def academic(self):
        return academic_fingerprint(organization_id=self.org.pk, offerings=[self.journal])

    def request(self, view, *, method="post", payload=None, user=None):
        payload = payload or {"task_id": str(self.source.pk), "row_id": str(self.row.pk)}
        rf = RequestFactory()
        req = (
            rf.get("/", payload)
            if method == "get"
            else rf.post("/", json.dumps(payload), content_type="application/json")
        )
        req.organization, req.user = self.org, user or self.admin
        return view(req)

    def test_transfer_preserves_uuid_splits_history_journal_and_primary_chairs(self):
        before = service._protected_row(self.row)
        academic = self.academic()
        primary = records(Membership.objects.filter(user__in=(self.teacher, self.teacher2), is_primary=True))
        result = self.transfer()
        self.row.refresh_from_db()
        self.assertEqual(self.row.task_id, self.target.pk)
        self.assertEqual(service._protected_row(self.row), before)
        self.assertEqual(self.academic(), academic)
        self.assertEqual(
            records(Membership.objects.filter(user__in=(self.teacher, self.teacher2), is_primary=True)), primary
        )
        extra = Membership.objects.filter(
            user__in=(self.teacher, self.teacher2), scope_unit=self.target_chair, is_active=True
        )
        self.assertEqual(extra.count(), 2)
        self.assertFalse(extra.filter(is_primary=True).exists())
        self.assertEqual(WorkloadAmendment.objects.filter(target_id=self.row.pk).count(), 2)
        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual((self.source.status, self.target.status), ("amended", "amended"))
        self.assertEqual(self.source.rows.count(), 0)
        self.assertIn(str(self.row.pk), result["edit_url"])
        self.assertEqual(AuditLog.objects.filter(reason="workload.row_chair_transferred").count(), 1)

    def test_two_chair_permissions_are_required(self):
        head = User.objects.create_user("source_head")
        activate_member(
            self.org,
            head,
            "transfer_head",
            permissions=PERMS,
            scope_unit=self.stack["chair"],
            scope_type=RoleScopeType.UNIT,
        )
        actor = resolve_actor(head, self.org)
        with self.assertRaisesMessage(WorkloadDenied, "idarə etmək"):
            self.transfer(actor=actor)
        self.assertEqual(service.destinations(actor=actor, row=self.row), [])
        self.assertFalse(WorkloadAmendment.objects.exists())

    def test_manage_without_distribute_is_denied(self):
        user = User.objects.create_user("manage_only")
        activate_member(
            self.org, user, "manage_only", permissions=["workload.manage"], scope_type=RoleScopeType.ORGANIZATION
        )
        with self.assertRaises(WorkloadDenied):
            self.transfer(actor=resolve_actor(user, self.org))

    def test_foreign_destination_and_source_are_denied(self):
        foreign = make_org("transfer-foreign")
        stack = make_structure(foreign, code="FOREIGN")
        with self.assertRaises(WorkloadDenied):
            self.transfer(destination_chair_id=stack["chair"].pk)
        task = make_task(foreign, stack["chair"], status="distributed")
        row = make_row(task, stack)
        with self.assertRaises(WorkloadDenied):
            self.transfer(row_id=row.pk, source_task_id=task.pk)
        self.row.refresh_from_db()
        self.assertEqual(self.row.task_id, self.source.pk)

    def test_unapproved_stages_are_not_automatically_promoted(self):
        for stage in (
            "draft",
            "submitted",
            "returned",
            "approved",
            "distributing",
            "pending_final_approval",
            "cancelled",
        ):
            with self.subTest(stage=stage):
                self.target.status = stage
                self.target.save(update_fields=["status"])
                with self.assertRaises(WorkloadDenied):
                    self.transfer()
                self.target.refresh_from_db()
                self.assertEqual(self.target.status, stage)
                self.assertFalse(WorkloadAmendment.objects.exists())

    def test_pending_faculty_slice_is_not_erased_or_skipped(self):
        slice_ = TaskFacultySlice.objects.create(
            organization=self.org, task=self.target, faculty=self.stack["faculty"], status="pending"
        )
        with self.assertRaises(WorkloadDenied):
            self.transfer()
        slice_.refresh_from_db()
        self.assertEqual(slice_.status, "pending")
        self.assertFalse(WorkloadAmendment.objects.exists())

    def test_approved_faculty_slice_is_preserved(self):
        slice_ = TaskFacultySlice.objects.create(
            organization=self.org, task=self.target, faculty=self.stack["faculty"], status="approved"
        )
        before = records(TaskFacultySlice.objects.filter(pk=slice_.pk))
        self.transfer()
        self.assertEqual(records(TaskFacultySlice.objects.filter(pk=slice_.pk)), before)

    def test_duplicate_physical_row_is_rejected_without_merging_or_deleting(self):
        duplicate = make_row(self.target, self.stack, lecture_total=45, seminar_total=30)
        with self.assertRaises(WorkloadDenied):
            self.transfer()
        self.assertEqual(self.target.rows.count(), 1)
        self.assertEqual(duplicate.assignments.count(), 0)
        self.assertFalse(WorkloadAmendment.objects.exists())

    def test_missing_destination_does_not_create_or_approve_task(self):
        self.target.delete()
        with self.assertRaises(WorkloadDenied):
            self.transfer()
        self.assertFalse(self.target_chair.teaching_tasks.exists())

    def test_stale_source_task_and_same_chair_retry_are_safe(self):
        with self.assertRaises(WorkloadDenied):
            self.transfer(destination_chair_id=self.stack["chair"].pk)
        self.transfer()
        with self.assertRaises(WorkloadDenied):
            self.transfer()
        self.assertEqual(WorkloadAmendment.objects.count(), 2)

    def test_invalid_amendment_rolls_back_secondary_memberships(self):
        before = records(Membership.objects.filter(organization=self.org))
        with self.assertRaises(WorkloadDenied):
            self.transfer(amend={"reason": "bad", "note": "Invalid reason must roll back"})
        self.assertEqual(records(Membership.objects.filter(organization=self.org)), before)
        self.row.refresh_from_db()
        self.assertEqual(self.row.task_id, self.source.pk)

    def test_academic_change_rolls_back_everything(self):
        original = service.open_amendment

        def broken(**kwargs):
            result = original(**kwargs)
            if kwargs["task"].pk == self.target.pk:
                LessonMark.objects.filter(pk=self.mark.pk).update(score=1)
            return result

        before = self.academic()
        with patch.object(service, "open_amendment", side_effect=broken):
            with self.assertRaises(WorkloadDenied):
                self.transfer()
        self.assertEqual(self.academic(), before)
        self.row.refresh_from_db()
        self.assertEqual(self.row.task_id, self.source.pk)
        self.assertFalse(WorkloadAmendment.objects.exists())

    def test_choices_and_post_endpoint_use_current_source_and_note(self):
        response = self.request(row_transfer_destinations, method="get")
        self.assertEqual(
            json.loads(response.content)["results"],
            [{"id": str(self.target_chair.pk), "name": "Marketinq", "task_id": str(self.target.pk)}],
        )
        payload = {
            "task_id": str(self.source.pk),
            "row_id": str(self.row.pk),
            "destination_chair_id": str(self.target_chair.pk),
        }
        self.assertEqual(self.request(row_transfer, payload=payload).status_code, 409)
        payload.update(amend_reason="correction", amend_note=AMEND["note"])
        response = self.request(row_transfer, payload=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["task_id"], str(self.target.pk))
        self.assertEqual(self.request(row_transfer, payload=payload).status_code, 409)

    def test_post_only_login_required_and_malformed_ids_fail_closed(self):
        self.assertEqual(self.request(row_transfer, method="get").status_code, 405)
        self.assertEqual(self.request(row_transfer_destinations, method="get", user=AnonymousUser()).status_code, 302)
        self.assertEqual(self.request(row_transfer, payload={"row_id": "bad", "task_id": "bad"}).status_code, 409)
        self.assertEqual(reverse("workload:row_transfer"), "/ders-yuku/setir/kocur/")
