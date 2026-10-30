"""Exact institutional identity bridges do not relax the general ledger rule."""

from contextlib import ExitStack
from unittest.mock import patch

from django.test import TestCase

from apps.legacy_import.services import reviewed_content_student_bridge as bridge
from apps.legacy_import.services.reviewed_content_contract import ContentError
from apps.registrar.models import CourseOffering, Curriculum, Enrollment, StudentAcademicRecord
from apps.workload.tests import test_scoped_snapshot as fixtures


class StudentBridgeTests(TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        self.actor.username, self.actor.first_name, self.actor.last_name = "salman.zeynalov", "Salman", "Zeynalov"
        self.actor.save()
        profile = self.actor.profile
        profile.organization, profile.patronymic, profile.institutional_identifier, profile.access_state = (
            self.org,
            "Sarvan",
            "10928",
            "active",
        )
        profile.save()
        fixtures.activate_member(self.org, self.actor, "student")
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.teacher,
        )
        self.record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.actor,
            group=self.stack["group"],
            program=self.stack["program"],
            curriculum=Curriculum.objects.create(
                organization=self.org, program=self.stack["program"], admission_year=2026
            ),
            admission_year=2026,
            status="enrolled",
            is_active=True,
        )
        Enrollment.objects.create(organization=self.org, offering=self.offering, student=self.actor)
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        for key, value in {
            "USER": self.actor.pk,
            "TARGET": str(self.offering.pk),
            "GROUP": str(self.stack["group"].pk),
            "PERIOD": str(self.stack["period"].pk),
            "SUBJECT": str(self.stack["subject"].pk),
        }.items():
            self.patches.enter_context(patch.object(bridge, key, value))
        self.data = {
            "selected_target_ids": [str(self.offering.pk)],
            "students": [{"id": 10928, "group_id": 829}],
            "points": [{"student_id": 10928}],
        }

    def test_exact_identifier_and_current_record_bridge(self):
        self.prepare()
        mappings = {}
        bridge.reviewed_student_bridge(self.data, mappings, lock=True)
        self.assertEqual(mappings, {"10928": {str(self.actor.pk)}})

    def test_conflicting_ledger_and_changed_identity_refused(self):
        self.prepare()
        with self.assertRaisesMessage(ContentError, "ledger_conflict"):
            bridge.reviewed_student_bridge(self.data, {"10928": {"999"}})
        self.actor.first_name = "Other"
        self.actor.save()
        with self.assertRaisesMessage(ContentError, "exact_identity_changed"):
            bridge.reviewed_student_bridge(self.data, {})

    def test_wrong_group_refused_and_unselected_source_unchanged(self):
        self.prepare()
        self.record.is_active = False
        self.record.save()
        with self.assertRaisesMessage(ContentError, "current_group_changed"):
            bridge.reviewed_student_bridge(self.data, {})
        self.data["points"] = []
        mappings = {}
        bridge.reviewed_student_bridge(self.data, mappings)
        self.assertEqual(mappings, {})
