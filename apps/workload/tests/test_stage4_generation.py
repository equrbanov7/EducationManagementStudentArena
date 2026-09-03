"""Plandan sətir törətməsi, Excel idxalı və bildiriş alıcıları (Mərhələ 4)."""

from __future__ import annotations

import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from core.constants import RoleScopeType

from ..constants import TaskStatus
from ..models import TaskFacultySlice, TeachingTaskRow
from ..services import (
    WorkloadDenied,
    apply_import,
    approve_slice,
    build_mapping,
    generate_rows_from_plan,
    parse_workbook,
    resolve_actor,
    return_slice,
    submit_task,
)
from ..services.imports import ImportFileError
from .factories import activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

OFFICE_PERMS = ["workload.view", "workload.manage", "workload.submit", "workload.report"]
DEAN_PERMS = ["workload.view", "workload.approve"]


def _approved_plan(org, stack, *, rows=2, status="approved"):
    """Təsdiqlənmiş tədris planı + sətirləri (Mərhələ 2 sxemi)."""
    from apps.registrar.models import Curriculum, CurriculumSubject, Subject

    plan = Curriculum.objects.create(
        organization=org,
        program=stack["program"],
        admission_year=2026,
        name="DS4 plan",
        status=status,
        version=1,
    )
    for index in range(rows):
        subject = Subject.objects.create(organization=org, code=f"GEN{index}", name=f"Fənn {index}", ects=5)
        CurriculumSubject.objects.create(
            organization=org,
            curriculum=plan,
            subject=subject,
            semester_number=index + 1,
            credits=5,
            total_hours=150,
            lecture_hours=30,
            seminar_hours=15,
            lab_hours=15,
            selfwork_hours=90,
        )
    return plan


class GenerationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("ds4-gen")
        cls.stack = make_structure(cls.org, code="GEN")
        cls.office = User.objects.create_user("gen.office", "gen@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)

    def actor(self):
        return resolve_actor(self.office, self.org)

    def test_rows_are_generated_from_the_approved_plan(self):
        _approved_plan(self.org, self.stack)
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        result = generate_rows_from_plan(task=task, actor=self.actor())
        self.assertEqual(result["created"], 2)
        rows = list(TeachingTaskRow.objects.filter(task=task).order_by("order"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].lecture_total, 30)
        self.assertEqual(rows[0].seminar_total, 15)
        self.assertEqual(rows[0].credits_value, 5)
        self.assertEqual(rows[0].specialty_id, self.stack["specialty"].pk)
        self.assertEqual(rows[0].faculty_id, self.stack["faculty"].pk)
        self.assertEqual(rows[0].season, "fall")
        self.assertEqual(rows[1].season, "spring")

    def test_generation_is_idempotent(self):
        _approved_plan(self.org, self.stack)
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        generate_rows_from_plan(task=task, actor=self.actor())
        second = generate_rows_from_plan(task=task, actor=self.actor())
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["existing"], 2)
        self.assertEqual(TeachingTaskRow.objects.filter(task=task).count(), 2)

    def test_draft_plan_is_not_a_source(self):
        _approved_plan(self.org, self.stack, status="draft")
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        result = generate_rows_from_plan(task=task, actor=self.actor())
        self.assertEqual(result["created"], 0)
        self.assertIn(self.stack["program"].name, result["blocked"])

    def test_generation_is_blocked_once_the_document_is_submitted(self):
        _approved_plan(self.org, self.stack)
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, self.stack)
        submit_task(task=task, actor=self.actor())
        task.refresh_from_db()
        with self.assertRaises(WorkloadDenied) as ctx:
            generate_rows_from_plan(task=task, actor=self.actor())
        self.assertEqual(ctx.exception.code, "workload.task_not_editable")


class ExcelImportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("ds4-imp")
        cls.stack = make_structure(cls.org, code="IMP")
        cls.office = User.objects.create_user("imp.office", "imp@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)

    def _workbook(self):
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.append(["Semestr", "Qruplar", "Fənn", "İxtisas", "Mühazirə cəmi", "Seminar cəmi", "Cəmi", "Kredit"])
        sheet.append(
            ["PAYIZ", self.stack["group"].name, self.stack["subject"].name, self.stack["specialty"].name, 30, 15, 45, 6]
        )
        sheet.append(["YAZ", "237 YOX", "Kataloqda olmayan fənn", "", 30, 0, 30, 4])
        stream = io.BytesIO()
        book.save(stream)
        stream.seek(0)
        return SimpleUploadedFile(
            "tapsiriq.xlsx",
            stream.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_parse_and_map(self):
        records = parse_workbook(self._workbook())
        self.assertEqual(len(records), 2)
        preview = build_mapping(organization=self.org, records=records)
        self.assertEqual(preview["row_count"], 2)
        self.assertEqual(preview["matched"], 1)
        self.assertGreaterEqual(preview["unmatched"], 1)

    def test_apply_keeps_unmatched_names_as_text(self):
        records = build_mapping(organization=self.org, records=parse_workbook(self._workbook()))["records"]
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        result = apply_import(task=task, actor=resolve_actor(self.office, self.org), records=records)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["text_only"], 1)
        rows = list(TeachingTaskRow.objects.filter(task=task).order_by("season"))
        matched = [row for row in rows if row.subject_id]
        unmatched = [row for row in rows if not row.subject_id]
        self.assertEqual(len(matched), 1)
        self.assertEqual(unmatched[0].subject_text, "Kataloqda olmayan fənn")

    def test_wrong_suffix_is_rejected(self):
        upload = SimpleUploadedFile("tapsiriq.csv", b"a,b", content_type="text/csv")
        with self.assertRaises(ImportFileError) as ctx:
            parse_workbook(upload)
        self.assertEqual(ctx.exception.code, "workload.bad_suffix")


class NotificationRecipientTest(TestCase):
    """Zəncirin hər keçidində KİM xəbər tutur (handoff §6.3)."""

    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("ds4-note")
        cls.stack = make_structure(cls.org, code="NOTE")
        cls.office = User.objects.create_user("note.office", "n1@x.test", "pw")
        cls.dean = User.objects.create_user("note.dean", "n2@x.test", "pw")
        cls.chair_head = User.objects.create_user("note.chair", "n3@x.test", "pw")
        activate_member(cls.org, cls.office, "teaching_office_head", permissions=OFFICE_PERMS, level=85)
        activate_member(
            cls.org,
            cls.dean,
            "dean",
            permissions=DEAN_PERMS,
            scope_unit=cls.stack["faculty"],
            scope_type=RoleScopeType.UNIT,
            level=70,
        )
        # Bildiriş alıcıları BÖLMƏ RƏHBƏRİNDƏN gəlir (OrgUnit.head).
        cls.stack["faculty"].head = cls.dean
        cls.stack["faculty"].save(update_fields=["head"])
        cls.stack["chair"].head = cls.chair_head
        cls.stack["chair"].save(update_fields=["head"])

    def _notifications(self, user):
        from apps.notifications.models import InAppNotification

        return list(InAppNotification.objects.filter(recipient=user).order_by("created_at"))

    def test_submit_notifies_the_dean(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, self.stack)
        submit_task(task=task, actor=resolve_actor(self.office, self.org))
        events = [note.metadata.get("event") for note in self._notifications(self.dean)]
        self.assertIn("workload_slice_submitted", events)

    def test_return_notifies_the_office_and_the_chair_head(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, self.stack)
        submit_task(task=task, actor=resolve_actor(self.office, self.org))
        return_slice(
            slice_obj=TaskFacultySlice.objects.get(task=task),
            actor=resolve_actor(self.dean, self.org),
            reason="Saat bölgüsü plan sətri ilə uyğun deyil — yenidən yoxlanılsın.",
        )
        for user in (self.office, self.chair_head):
            events = [note.metadata.get("event") for note in self._notifications(user)]
            self.assertIn("workload_task_returned", events, user.username)

    def test_approval_notifies_the_chair_head(self):
        task = make_task(self.org, self.stack["chair"], created_by=self.office)
        make_row(task, self.stack)
        submit_task(task=task, actor=resolve_actor(self.office, self.org))
        approve_slice(slice_obj=TaskFacultySlice.objects.get(task=task), actor=resolve_actor(self.dean, self.org))
        task.refresh_from_db()
        self.assertEqual(task.status, TaskStatus.APPROVED)
        events = [note.metadata.get("event") for note in self._notifications(self.chair_head)]
        self.assertIn("workload_task_approved", events)
