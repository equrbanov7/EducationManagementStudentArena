"""Real canonical transfer, source identity, atomic rollback and guarded undo."""

import hashlib
import json
import tempfile
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.legacy_import.tests.test_models import _make_map, _make_run
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    Lesson,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.workload.services import tspx_roster_plan as contract
from apps.workload.services import tspx_roster_repair as repair
from apps.workload.services import tspx_roster_state as state
from apps.workload.services.sbio235_state import RepairError
from core.rls import bypass_rls

User = get_user_model()


class TspxRosterTests(TestCase):
    family = contract.TSPX

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.actor = User.objects.create_superuser("tspx_admin", "tspx@test.invalid", "pw")
            cls.org = Organization.objects.create(
                id=contract.ORG,
                name="TSPX",
                slug="qku",
                org_type="university",
                owner=cls.actor,
                is_active=True,
                status="active",
            )
            cls.period = AcademicPeriod.objects.create(
                id=contract.PERIOD,
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type="semester",
                start_date="2026-09-01",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.parent = OrgUnit.objects.create(
                id=cls.family.parent,
                organization=cls.org,
                name=cls.family.label_prefix,
                slug="tspx-parent",
                unit_type="group",
                settings={"degree_level": "bachelor", "sector": "az", "education_form": "full_time"},
            )
            cls.children = []
            for number, gid in enumerate(cls.family.targets.values(), 1):
                cls.children.append(
                    OrgUnit.objects.create(
                        id=gid,
                        organization=cls.org,
                        name=f"{cls.family.label_prefix}-{number}",
                        slug=f"tspx-{number}",
                        unit_type="group",
                        settings={**cls.parent.settings, "parent_group": cls.family.parent},
                    )
                )
            cls.program = Program.objects.create(organization=cls.org, code="TSPX", name="TSPX")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            cls.teacher = User.objects.create_user("tspx_teacher")
            Membership.objects.create(organization=cls.org, user=cls.teacher, role=cls.org.roles.get(name="teacher"))
            cls.subject = Subject.objects.create(organization=cls.org, code="TSPX1", name="Common lecture")
            cls.journal = CourseOffering.objects.create(
                organization=cls.org,
                period=cls.period,
                subject=cls.subject,
                group=cls.parent,
                instructor=cls.teacher,
                lesson_hours=30,
            )
            run = _make_run(cls.org)
            people = []
            cls.records = []
            for n in range(cls.family.moves + 1):
                user = User.objects.create_user(f"tspx_student{n}", first_name=f"Ad{n}", last_name=f"Soyad{n}")
                Membership.objects.create(organization=cls.org, user=user, role=cls.org.roles.get(name="student"))
                UserProfile.objects.filter(user=user).update(organization=cls.org, patronymic=f"Ata{n}")
                record = StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=cls.program,
                    curriculum=cls.curriculum,
                    group=cls.parent,
                    admission_year=2025,
                )
                cls.records.append(record)
                Enrollment.objects.create(organization=cls.org, student=user, offering=cls.journal)
                _make_map(run, legacy_pk=str(1000 + n), target_pk=str(user.pk))
                _make_map(
                    run,
                    legacy_pk=str(1000 + n),
                    entity_type="student_record",
                    target_model_label="registrar.studentacademicrecord",
                    target_pk=str(record.pk),
                )
                source_group = (
                    cls.family.children[0][0]
                    if n < cls.family.children[0][2]
                    else cls.family.children[1][0] if n < cls.family.moves else cls.family.legacy_parent
                )
                item = {
                    "legacy_student_id": 1000 + n,
                    "source_system": "myedu_mariadb",
                    "ledger_source_row_hash": "b" * 64,
                    "target_user_id": user.pk,
                    "expected_record_id": str(record.pk),
                    "clone_record_source_group_id": cls.family.parent,
                    "source_identity": {
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "patronymic": f"Ata{n}",
                    },
                    "keep_admission_year": 2025,
                    "keep_program_id": str(cls.program.pk),
                    "keep_curriculum_id": str(cls.curriculum.pk),
                    "source_home_group_id": source_group,
                }
                if n < cls.family.moves:
                    item["target_group_id"] = cls.family.targets[source_group]
                people.append(item)
            cls.plan = contract.Plan(
                cls.family.manifest_sha, people[: cls.family.moves], people[cls.family.moves :], cls.family
            )
            lesson = Lesson.objects.create(
                organization=cls.org, offering=cls.journal, date="2026-10-01", kind="seminar"
            )
            enrollment = Enrollment.objects.get(student_id=people[0]["target_user_id"], offering=cls.journal)
            cls.mark = LessonMark.objects.create(organization=cls.org, lesson=lesson, enrollment=enrollment, score=9)

    def execute(self, **kwargs):
        with bypass_rls():
            return repair.run(plan=self.plan, organization=self.org, user=self.actor, **kwargs)

    def snapshot(self):
        with bypass_rls():
            return state.capture(self.plan)

    def applied(self):
        dry = self.execute()
        return self.execute(apply=True, expected_baseline=dry["baseline"])

    def test_dryrun_rolls_back_then_exact_23_26_and_parent_one_apply_is_idempotent(self):
        before = self.snapshot()
        dry = self.execute()
        self.assertEqual(self.snapshot(), before)
        applied = self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(applied["moved_students"], self.family.moves)
        with bypass_rls():
            for gid, count in [
                (self.family.parent, 1),
                (str(self.children[0].pk), self.family.children[0][2]),
                (str(self.children[1].pk), self.family.children[1][2]),
            ]:
                self.assertEqual(StudentAcademicRecord.objects.filter(group_id=gid).count(), count)
            self.mark.refresh_from_db()
            self.assertEqual(self.mark.score, 9)
            original = self.mark.enrollment
            self.assertEqual(original.status, "dropped")
            self.assertIsNotNone(original.superseded_by_id)
        self.assertEqual(self.execute(apply=True, expected_baseline=dry["baseline"])["already_done"], 1)

    def test_apply_requires_fresh_baseline_and_stale_baseline_writes_nothing(self):
        before = self.snapshot()
        for baseline in ("", "0" * 64):
            with self.assertRaises(RepairError):
                self.execute(apply=True, expected_baseline=baseline)
            self.assertEqual(self.snapshot(), before)

    def test_other_frozen_family_cannot_use_this_manifest_or_receipt(self):
        other = contract.SI135 if self.family == contract.TSPX else contract.TSPX
        with self.assertRaisesMessage(RepairError, "fixed_reviewed_roster_contract"):
            with bypass_rls():
                repair.run(plan=replace(self.plan, family=other), organization=self.org, user=self.actor)
        reader = contract.read_si135_plan if self.family == contract.TSPX else contract.read_plan
        with self.assertRaisesMessage(RepairError, "manifest_sha"):
            reader("/unread-other-family", self.family.manifest_sha)

    def test_reused_child_grade_roster_survives_forward_and_undo_is_explicitly_blocked(self):
        with bypass_rls():
            other = Subject.objects.create(organization=self.org, code="TSPX2", name="Own child class")
            journal = CourseOffering.objects.create(
                organization=self.org,
                subject=other,
                period=self.period,
                group=self.children[0],
                instructor=self.teacher,
            )
            enrolled = Enrollment.objects.create(
                organization=self.org, offering=journal, student_id=self.plan.candidates[0]["target_user_id"]
            )
            lesson = Lesson.objects.create(organization=self.org, offering=journal, date="2026-10-02", kind="seminar")
            mark = LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=enrolled, score=8)
        result = self.applied()
        after = self.snapshot()
        with self.assertRaisesMessage(RepairError, "preexisting_child_roster"):
            self.execute(undo=result["batch"])
        self.assertEqual(self.snapshot(), after)
        with bypass_rls():
            enrolled.refresh_from_db()
            mark.refresh_from_db()
            self.assertEqual(enrolled.status, "enrolled")
            self.assertEqual(mark.score, 8)

    def test_later_child_grade_blocks_undo_before_any_mutation(self):
        result = self.applied()
        with bypass_rls():
            e = Enrollment.objects.get(student_id=self.plan.candidates[0]["target_user_id"], status="enrolled")
            lesson = Lesson.objects.create(
                organization=self.org, offering=e.offering, date="2026-10-04", kind="seminar"
            )
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=e, score=10)
        before = self.snapshot()
        with self.assertRaisesMessage(RepairError, "unchanged_receipt"):
            self.execute(undo=result["batch"])
        self.assertEqual(self.snapshot(), before)

    def test_wrong_registered_parent_or_sector_is_rejected(self):
        with bypass_rls():
            self.children[0].settings = {**self.children[0].settings, "sector": "en"}
            self.children[0].save(update_fields=["settings"])
        with self.assertRaisesMessage(RepairError, "parent_or_sector"):
            self.execute()

    def test_revoked_membership_is_not_recreated(self):
        with bypass_rls():
            Membership.objects.filter(user_id=self.plan.candidates[0]["target_user_id"]).update(is_active=False)
        before = self.snapshot()
        with self.assertRaises(ValidationError):
            self.execute()
        self.assertEqual(self.snapshot(), before)

    def test_atomic_rollback_when_late_student_identity_does_not_match(self):
        with bypass_rls():
            User.objects.filter(pk=self.plan.candidates[-1]["target_user_id"]).update(last_name="Changed")
        before = self.snapshot()
        with self.assertRaisesMessage(
            RepairError, f"identity_or_record_changed:source_slot={self.family.moves}:fields=last_name"
        ):
            self.execute()
        self.assertEqual(self.snapshot(), before)

    def test_html_encoded_source_name_keeps_exact_immutable_live_identity(self):
        candidates = deepcopy(self.plan.candidates)
        candidates[0]["source_identity"]["first_name"] = "G&uuml;nel"
        plan = replace(self.plan, candidates=candidates)
        with bypass_rls():
            User.objects.filter(pk=candidates[0]["target_user_id"]).update(first_name="Günel")
            groups, period, people = state.validate(plan, self.org)
        self.assertEqual(len(groups), 3)
        self.assertEqual(str(period.pk), str(self.period.pk))
        self.assertEqual(len(people), self.family.moves + 1)
        self.assertEqual(people[candidates[0]["expected_record_id"]].student.first_name, "Günel")

    def test_failure_after_real_transfers_rolls_back_all_records_enrollments_and_audits(self):
        before = self.snapshot()
        canonical = repair.transfer.transfer_student_group
        calls = 0

        def fail_late(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 11:
                raise RuntimeError("injected_late_transfer_failure")
            return canonical(**kwargs)

        with patch.object(repair.transfer, "transfer_student_group", side_effect=fail_late):
            with self.assertRaisesMessage(RuntimeError, "injected_late"):
                self.execute(apply=True, expected_baseline=state.baseline(before))
        self.assertEqual(self.snapshot(), before)
        with bypass_rls():
            self.assertFalse(AuditLog.objects.filter(resource_type=self.family.resource).exists())

    def test_inactive_or_non_superadmin_actor_cannot_change_roster(self):
        self.actor.is_superuser = False
        before = self.snapshot()
        with self.assertRaisesMessage(RepairError, "active_superadmin"):
            self.execute()
        self.assertEqual(self.snapshot(), before)

    def test_frozen_private_manifest_contract_and_no_password_values_in_receipt(self):
        value = {
            "format": "reviewed-canonical-student-subgroup-transfer-plan/1",
            "organization_id": contract.ORG,
            "academic_year": "2026/2027",
            "period_id": contract.PERIOD,
            "source_sql_sha256": contract.SOURCE_SHA,
            "source_parent_current_group_id": self.family.parent,
            "source_parent_legacy_group_id": self.family.legacy_parent,
            "source_target_groups": {str(k): v for k, v in self.family.targets.items()},
            "candidates": self.plan.candidates,
            "retain_parent": self.plan.retain,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(value))
            path.chmod(0o600)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(contract, "MANIFEST_SHA" if self.family == contract.TSPX else "SI135_MANIFEST_SHA", sha):
                reader = contract.read_plan if self.family == contract.TSPX else contract.read_si135_plan
                self.assertEqual(len(reader(path, sha).candidates), self.family.moves)
                path.chmod(0o644)
                with self.assertRaises(RepairError):
                    reader(path, sha)
        self.applied()
        with bypass_rls():
            data = AuditLog.objects.filter(resource_type=self.family.resource).get().new_values
            self.assertNotIn('"password"', json.dumps(data))


class TspxRosterInverseTests(TransactionTestCase):
    family = contract.TSPX
    execute = TspxRosterTests.execute
    snapshot = TspxRosterTests.snapshot
    applied = TspxRosterTests.applied

    def setUp(self):
        TspxRosterTests.setUpTestData.__func__(type(self))

    def test_direct_inverse_without_preexisting_child_roster_preserves_old_grade(self):
        result = self.applied()
        dry = self.execute(undo=result["batch"])
        self.execute(undo=result["batch"], apply=True, expected_baseline=dry["baseline"])
        with bypass_rls():
            self.assertEqual(StudentAcademicRecord.objects.filter(group=self.parent).count(), self.family.moves + 1)
            self.mark.refresh_from_db()
            self.mark.enrollment.refresh_from_db()
            self.assertEqual(self.mark.enrollment.status, "enrolled")
            self.assertEqual(self.mark.score, 9)


class Si135RosterTests(TspxRosterTests):
    family = contract.SI135


class Si135RosterInverseTests(TspxRosterInverseTests):
    family = contract.SI135
