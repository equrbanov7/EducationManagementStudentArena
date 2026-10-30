"""Actual ORM dry/apply/idempotence/conflict/undo with a bounded source fixture."""

import hashlib
import io
import json
import tempfile
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command

from apps.legacy_import.services import six_syllabus_recovery as recovery
from apps.legacy_import.services import workload_syllabi
from apps.legacy_import.tests.test_workload_syllabi import WorkloadSyllabusTests, plan
from apps.syllabus.models import Syllabus


class SixSyllabusRecoveryTests(WorkloadSyllabusTests):
    # Reuse tenant/author/sentinel fixtures and retain parent regression coverage.
    def run_six(self, *, apply=False, undo="", tamper=False, wrong_subject=False):
        source = plan()["source"]
        spec = replace(
            workload_syllabi.SPEC,
            subject_id=str(uuid4() if wrong_subject else self.subject.pk),
            require_current_period=False,
        )
        row = {
            "offering_id": spec.offering,
            "source_syllabus_id": spec.source_syllabus,
            "source_digest": recovery.core.digest(source),
        }
        if tamper:
            source["week"][0]["movzu"] = "Unauthorized replacement"
        package = {"format": "six-own-syllabus-evidence/1", "unique_sources": {str(spec.source_syllabus): source}}
        raw = json.dumps(package).encode()
        output = io.StringIO()
        with (
            tempfile.NamedTemporaryFile() as file,
            patch.object(recovery, "ROWS", (row,)),
            patch.object(recovery, "spec_for", return_value=spec),
        ):
            file.write(raw)
            file.flush()
            kwargs = dict(actor=self.actor.username, apply=apply, stdout=output)
            if undo:
                kwargs["undo"] = undo
            else:
                kwargs.update(file=file.name, sha256=hashlib.sha256(raw).hexdigest())
            call_command("recover_six_workload_syllabi", **kwargs)
        return output.getvalue()

    def test_batch_dry_apply_idempotent_spring_and_undo(self):
        self.offering.lesson_hours = 30
        self.offering.save(update_fields=["lesson_hours"])
        self.period.is_current = False
        self.period.save(update_fields=["is_current"])
        self.assertIn("syllabi_created=1", self.run_six())
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())
        output = self.run_six(apply=True)
        batch = output.split("batch=")[1].strip()
        self.assertIn("already_present=1", self.run_six(apply=True))
        self.assertIn("versions_archived=1", self.run_six(apply=True, undo=batch))
        self.assertFalse(Syllabus.objects.get(offering=self.offering).is_active)
        self.assert_others_unchanged()

    def test_changed_source_and_hours_fail_without_writes(self):
        with self.assertRaisesMessage(Exception, "pinned_source_changed"):
            self.run_six(apply=True, tamper=True)
        self.offering.lesson_hours = 99
        self.offering.save(update_fields=["lesson_hours"])
        with self.assertRaisesMessage(Exception, "live_workload_hours_changed"):
            self.run_six(apply=True)
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_wrong_subject_uuid_rejected_despite_matching_code(self):
        with self.assertRaisesMessage(Exception, "live_offering_scope"):
            self.run_six(apply=True, wrong_subject=True)
