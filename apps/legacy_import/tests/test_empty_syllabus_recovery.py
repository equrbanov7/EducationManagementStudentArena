"""Actual ORM dry/apply/idempotence/conflict/undo with a bounded source fixture."""

import hashlib
import io
import json
import tempfile
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command

from apps.legacy_import.services import empty_syllabus_recovery as recovery
from apps.legacy_import.services import workload_syllabi
from apps.legacy_import.tests.test_workload_syllabi import WorkloadSyllabusTests, plan
from apps.syllabus.models import Syllabus


class EmptySyllabusRecoveryTests(WorkloadSyllabusTests):
    # Reuse tenant/author/sentinel fixtures and retain parent regression coverage.
    def run_empty(
        self, *, apply=False, undo="", tamper=False, wrong_subject=False, changed_plan=False, missing_assignment=False
    ):
        source = plan()["source"]
        spec = replace(
            workload_syllabi.SPEC,
            subject_id=str(uuid4() if wrong_subject else self.subject.pk),
            require_current_period=False,
            group_id=str(self.offering.group_id),
        )
        task = recovery.core.model("workload.TeachingTask").objects.get_or_create(
            organization=self.org, academic_year="2026/2027", chair=self.offering.group
        )[0]
        workload_row = recovery.core.model("workload.TeachingTaskRow").objects.create(
            organization=self.org,
            task=task,
            subject=self.subject,
            period=self.period,
            lecture_plan=16 if changed_plan else 15,
            seminar_plan=15,
            lecture_total=15,
            seminar_total=15,
        )
        workload_row.groups.add(self.offering.group)
        if not missing_assignment:
            recovery.core.model("workload.TeacherAssignment").objects.create(
                organization=self.org, row=workload_row, teacher=self.author, activity="lecture", hours=15
            )
        row = {
            "row_id": str(workload_row.pk),
            "source_plan_units": {"lecture": 15, "seminar": 15, "lab": 0},
            "offering_id": spec.offering,
            "source_syllabus_id": spec.source_syllabus,
            "source_digest": recovery.core.digest(source),
        }
        if tamper:
            source["week"][0]["movzu"] = "Unauthorized replacement"
        package = {"format": "empty-own-syllabus-evidence/1", "unique_sources": {str(spec.source_syllabus): source}}
        raw = json.dumps(package).encode()
        output = io.StringIO()
        with (
            tempfile.NamedTemporaryFile() as file,
            patch.object(recovery, "ROWS", (row,)),
            patch.object(recovery.timezone, "localdate", return_value=self.period.start_date),
            patch.object(recovery, "spec_for", return_value=spec),
        ):
            file.write(raw)
            file.flush()
            kwargs = dict(actor=self.actor.username, apply=apply, stdout=output)
            if undo:
                kwargs["undo"] = undo
            else:
                kwargs.update(file=file.name, sha256=hashlib.sha256(raw).hexdigest())
            call_command("recover_empty_workload_syllabi", **kwargs)
        return output.getvalue()

    def test_batch_dry_apply_idempotent_and_undo(self):
        self.offering.lesson_hours = 30
        self.offering.save(update_fields=["lesson_hours"])
        self.period.is_current = False
        self.period.save(update_fields=["is_current"])
        self.assertIn("syllabi_created=1", self.run_empty())
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())
        output = self.run_empty(apply=True)
        batch = output.split("batch=")[1].strip()
        self.assertIn("already_present=1", self.run_empty(apply=True))
        self.assertIn("versions_archived=1", self.run_empty(apply=True, undo=batch))
        self.assertFalse(Syllabus.objects.get(offering=self.offering).is_active)
        self.assert_others_unchanged()

    def test_changed_source_and_hours_fail_without_writes(self):
        with self.assertRaisesMessage(Exception, "pinned_source_changed"):
            self.run_empty(apply=True, tamper=True)
        self.offering.lesson_hours = 99
        self.offering.save(update_fields=["lesson_hours"])
        with self.assertRaisesMessage(Exception, "live_workload_hours_changed"):
            self.run_empty(apply=True)
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_wrong_subject_uuid_rejected_despite_matching_code(self):
        with self.assertRaisesMessage(Exception, "live_offering_scope"):
            self.run_empty(apply=True, wrong_subject=True)

    def test_existing_lesson_and_locked_period_rejected(self):
        from apps.registrar.models import Lesson

        self.offering.lesson_hours = 30
        self.offering.save(update_fields=["lesson_hours"])
        Lesson.objects.create(
            organization=self.org, offering=self.offering, date=self.period.start_date, kind="lecture", hours=1
        )
        with self.assertRaisesMessage(Exception, "live_journal_no_longer_empty"):
            self.run_empty(apply=True)
        Lesson.objects.filter(offering=self.offering).delete()
        self.period.locked_at = recovery.timezone.now()
        self.period.save(update_fields=["locked_at"])
        with self.assertRaisesMessage(Exception, "live_period_locked_or_outside_dates"):
            self.run_empty(apply=True)

    def test_changed_official_plan_and_assignment_rejected(self):
        with self.assertRaisesMessage(Exception, "live_official_kind_hours_changed"):
            self.run_empty(apply=True, changed_plan=True)
        with self.assertRaisesMessage(Exception, "live_workload_assignment_missing"):
            self.run_empty(apply=True, missing_assignment=True)
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_current_effective_syllabus_never_overwritten(self):
        self.offering.lesson_hours = 30
        self.offering.save(update_fields=["lesson_hours"])
        self.run_command(apply=True)
        existing = Syllabus.objects.get(offering=self.offering)
        with self.assertRaisesMessage(Exception, "existing_syllabus_no_overwrite"):
            self.run_empty(apply=True)
        self.assertEqual(Syllabus.objects.get(offering=self.offering).pk, existing.pk)
