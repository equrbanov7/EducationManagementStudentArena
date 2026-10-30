"""41 source-backed moves preserve extra people, authors, marks and immutable maps."""

import copy
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
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
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.services import bi_mu536_roster_plan as contract
from apps.workload.services import bi_mu536_roster_repair as repair
from apps.workload.services import bi_mu536_roster_state as state
from apps.workload.services.sbio235_state import RepairError
from core.rls import bypass_rls

User = get_user_model()


def payload(people):
    return {
        "format": "reviewed-bi-mu536-liveidentity-roster/1",
        "organization_id": contract.ORG,
        "academic_year": "2026/2027",
        "period_id": contract.PERIOD,
        "source_sql_sha256": contract.SOURCE_SQL_SHA,
        "source_rows_sha256": contract.SOURCE_ROWS_SHA,
        "live_gui_evidence_sha256": contract.GUI_SHA,
        "excluded_source_ids": sorted(contract.EXCLUDED),
        "candidates": people,
    }


class BiMuContractTests(SimpleTestCase):
    def test_fuzzy_spelling_is_not_identity_evidence_and_suffix_is_normalized(self):
        value = {"first_name": "Günel", "last_name": "Sınaqlı", "patronymic": "Namiq"}
        other = {"first_name": "GÜNEL", "last_name": "SINAQLI", "patronymic": "NAMİQ QIZI"}
        self.assertEqual(contract.identity(value), contract.identity(other))
        other["first_name"] = "Nüranə"
        value["first_name"] = "Nuranə"
        self.assertNotEqual(contract.identity(value), contract.identity(other))
        with self.assertRaises(RepairError):
            contract.identity({**value, "patronymic": ""})

    def test_unsealed_source_never_reaches_plan_resolution(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plan.json"
            path.write_text("{}")
            path.chmod(0o600)
            with self.assertRaisesMessage(RepairError, "fixed_bi_mu536_manifest_sha_required"):
                contract.read_plan(path, hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaisesMessage(RepairError, "manifest_sha256_mismatch"):
                contract.read_plan(path, contract.MANIFEST_SHA)


class BiMuRosterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.actor = User.objects.create_superuser("bimu_admin", "test@example.invalid", "pw")
            cls.org = Organization.objects.create(
                pk=contract.ORG, owner=cls.actor, slug="qku", name="QKU", org_type="university", status="active"
            )
            cls.org.refresh_from_db()
            cls.period = AcademicPeriod.objects.create(
                pk=contract.PERIOD,
                organization=cls.org,
                name="Fall",
                academic_year="2026/2027",
                start_date="2026-09-01",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.period.refresh_from_db()
            cls.teacher = User.objects.create_user("bimu_teacher")
            Membership.objects.create(organization=cls.org, user=cls.teacher, role=cls.org.roles.get(name="teacher"))
            cls.people, cls.candidate_records, cls.extras, cls.journals, cls.children = [], [], [], {}, {}
            for family in contract.FAMILIES:
                spec = contract.GEOMETRY[family.name]
                specialty = OrgUnit.objects.create(
                    pk=spec["specialty"],
                    organization=cls.org,
                    name=family.name,
                    slug=family.name,
                    unit_type="specialty",
                )
                program = Program.objects.create(
                    organization=cls.org,
                    specialty_unit=specialty,
                    code=family.name,
                    name=family.name,
                    official_code=spec["program"],
                )
                curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
                groups = []
                for number, gid in enumerate(family.group_ids):
                    group = OrgUnit.objects.create(
                        pk=gid,
                        organization=cls.org,
                        parent=specialty,
                        name=spec["names"][number],
                        slug=f"{family.name}-{number}",
                        unit_type="group",
                        settings={
                            "education_form": "full_time",
                            **(
                                {"sector": "az", "degree_level": "bachelor", "parent_group": family.parent}
                                if number
                                else {}
                            ),
                        },
                    )
                    groups.append(group)
                cls.children[family.name] = groups
                subject = Subject.objects.create(organization=cls.org, name=family.name + " subject", code=family.name)
                offering = CourseOffering.objects.create(
                    organization=cls.org,
                    group=groups[0],
                    period=cls.period,
                    subject=subject,
                    instructor=cls.teacher,
                    lesson_hours=30,
                )
                cls.journals[family.name] = offering
                lesson = Lesson.objects.create(
                    organization=cls.org,
                    offering=offering,
                    date="2026-10-01",
                    kind="seminar",
                    instructor=cls.teacher,
                    created_by=cls.actor,
                )
                syllabus = Syllabus.objects.create(
                    organization=cls.org, subject=subject, period=cls.period, author=cls.teacher, offering=offering
                )
                version = SyllabusVersion.objects.create(
                    organization=cls.org,
                    syllabus=syllabus,
                    major=1,
                    status="approved",
                    approved_at=timezone.now(),
                    approved_by=cls.actor,
                    locked_at=timezone.now(),
                    plan_hours={"lecture": 15, "seminar": 15},
                )
                SyllabusSection.objects.create(
                    organization=cls.org,
                    version=version,
                    section_id="week",
                    data={"rows": [{"topic": "Keep original approved body"}]},
                )
                syllabus.current_version = syllabus.approved_version = version
                syllabus.save(update_fields=["current_version", "approved_version"])
                # Both families retain extra active and inactive records. Three
                # pre-existing child accounts have their own enrollments/marks.
                for index in range(family.moves + 4):
                    number = len(cls.people) if index < family.moves else 100 + len(cls.extras)
                    user = User.objects.create_user(
                        f"bimu_{family.name}_{index}", first_name=f"AD{number}", last_name=f"SOYAD{number}"
                    )
                    Membership.objects.create(organization=cls.org, user=user, role=cls.org.roles.get(name="student"))
                    UserProfile.objects.filter(user=user).update(organization=cls.org, patronymic=f"ATA{number} QIZI")
                    group = groups[0] if index < family.moves + 2 else groups[1 if family == contract.BI else 2]
                    record = StudentAcademicRecord.objects.create(
                        organization=cls.org,
                        student=user,
                        program=program,
                        curriculum=curriculum,
                        group=group,
                        admission_year=2026,
                    )
                    if index < family.moves:
                        enrollment = Enrollment.objects.create(organization=cls.org, student=user, offering=offering)
                        LessonMark.objects.create(
                            organization=cls.org, enrollment=enrollment, lesson=lesson, score=9, entered_by=cls.teacher
                        )
                        source_identity = {
                            "first_name": f"Ad{number}",
                            "last_name": f"Soyad{number}",
                            "patronymic": f"Ata{number}",
                        }
                        cls.people.append(
                            {
                                "legacy_student_id": 1000 + number,
                                "source_home_group_id": spec["source_child"],
                                "source_identity": source_identity,
                                "source_entry_year": 2026,
                                "current_username": user.username,
                                "current_identity": {
                                    "first_name": user.first_name,
                                    "last_name": user.last_name,
                                    "patronymic": f"ATA{number} QIZI",
                                },
                                "current_parent_group_name": spec["names"][0],
                                "program_official_code": spec["program"],
                                "keep_admission_year": 2026,
                            }
                        )
                        cls.candidate_records.append(record)
                    else:
                        if index == family.moves + 1:
                            record.status = "expelled"
                            record.is_active = False
                            record.save(update_fields=["status", "is_active"])
                        cls.extras.append(record)
                        if index == family.moves + 2 or (family == contract.MU and index == family.moves + 3):
                            child_offer, _ = CourseOffering.objects.get_or_create(
                                organization=cls.org,
                                group=group,
                                period=cls.period,
                                subject=subject,
                                defaults={"instructor": cls.teacher, "lesson_hours": 30},
                            )
                            child_enrollment = Enrollment.objects.create(
                                organization=cls.org, student=user, offering=child_offer
                            )
                            child_lesson, _ = Lesson.objects.get_or_create(
                                organization=cls.org,
                                offering=child_offer,
                                date="2026-10-01",
                                kind="seminar",
                                defaults={"instructor": cls.teacher},
                            )
                            LessonMark.objects.create(
                                organization=cls.org, enrollment=child_enrollment, lesson=child_lesson, score=8
                            )
            cls.manifest = payload(cls.people)

    def setUp(self):
        self.plan = contract.parse(copy.deepcopy(self.manifest), contract.MANIFEST_SHA)

    def execute(self, **kwargs):
        with bypass_rls():
            return repair.run(plan=self.plan, organization=self.org, user=self.actor, **kwargs)

    def snapshot(self):
        with bypass_rls():
            scopes, *_ = state.resolve(self.plan, self.org, allow_targets=True)
            return state.capture(scopes)

    def applied(self):
        dry = self.execute()
        return self.execute(apply=True, expected_baseline=dry["baseline"])

    def test_41_canonical_moves_dry_apply_repeat_preserve_extras_marks_and_authors(self):
        before = self.snapshot()
        dry = self.execute()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(dry["moved_students"], 41)
        result = self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(result["moved_students"], 41)
        with bypass_rls():
            for person in self.plan.candidates:
                record = StudentAcademicRecord.objects.get(student__username=person["current_username"])
                family = contract.BI if person["source_home_group_id"] == 966 else contract.MU
                self.assertEqual(str(record.group_id), family.targets[person["source_home_group_id"]])
            self.assertEqual(model_count("legacy_import.LegacyEntityMap"), 0)
        self.assertEqual(self.execute()["already_done"], 1)
        after = self.snapshot()
        for family in contract.FAMILIES:
            key = family.name
            self.assertEqual(before[key]["academic"], after[key]["academic"])
            old = {r["id"]: r for r in before[key]["records"]}
            new = {r["id"]: r for r in after[key]["records"]}
            for extra in self.extras:
                if str(extra.pk) in old:
                    self.assertEqual(old[str(extra.pk)], new[str(extra.pk)])

    def test_failure_last_person_rolls_back_both_families(self):
        before = self.snapshot()
        original = repair.transfer.transfer_student_group
        calls = []

        def failing(**kwargs):
            calls.append(1)
            if len(calls) == 41:
                raise RepairError("final_student_failure")
            return original(**kwargs)

        with patch.object(repair.transfer, "transfer_student_group", side_effect=failing):
            with self.assertRaisesMessage(RepairError, "final_student_failure"):
                self.execute()
        self.assertEqual(self.snapshot(), before)

    def test_wrong_father_inactive_account_wrong_year_or_program_fail_without_writes(self):
        for field, value, model_name in (
            ("patronymic", "OTHER", "profile"),
            ("access_state", "archived", "profile"),
            ("admission_year", 2025, "record"),
            ("official_code", "6004001", "program"),
        ):
            with self.subTest(field=field), transaction.atomic():
                with bypass_rls():
                    record = self.candidate_records[0]
                    obj = {"profile": record.student.profile, "record": record, "program": record.program}[model_name]
                    original = getattr(obj, field)
                    setattr(obj, field, value)
                    obj.save(update_fields=[field])
                    with self.assertRaises(RepairError):
                        self.execute()
                    setattr(obj, field, original)
                transaction.set_rollback(True)

    def test_stale_baseline_and_missing_full_identity_fail_closed(self):
        with self.assertRaisesMessage(RepairError, "baseline_conflict"):
            self.execute(apply=True, expected_baseline="f" * 64)
        raw = copy.deepcopy(self.manifest)
        raw["candidates"][0]["source_identity"]["patronymic"] = ""
        with self.assertRaisesMessage(RepairError, "full_three"):
            contract.parse(raw, contract.MANIFEST_SHA)

    def test_registered_parent_or_english_sector_mismatch_fails(self):
        with bypass_rls():
            child = self.children[contract.BI.name][2]
            old = child.settings
            for changed in ({**old, "parent_group": contract.MU.parent}, {**old, "sector": "en"}):
                OrgUnit.objects.filter(pk=child.pk).update(settings=changed)
                with self.assertRaisesMessage(RepairError, "registered_family_metadata_changed"):
                    self.execute()
            OrgUnit.objects.filter(pk=child.pk).update(settings=old)

    def test_existing_immutable_map_conflict_is_rejected_without_inventing_new_map(self):
        from apps.legacy_import.tests.test_models import _make_map, _make_run

        with bypass_rls():
            run = _make_run(self.org)
            _make_map(
                run,
                legacy_pk=str(self.people[0]["legacy_student_id"]),
                target_pk=str(self.candidate_records[1].student_id),
            )
        with self.assertRaisesMessage(RepairError, "existing_immutable_mapping_conflict"):
            self.execute()
        with bypass_rls():
            self.assertEqual(model_count("legacy_import.LegacyEntityMap"), 1)

    def test_preexisting_child_grade_is_preserved_and_blocks_automatic_inverse(self):
        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org,
                group=self.children[contract.BI.name][2],
                period=self.period,
                subject=self.journals[contract.BI.name].subject,
                instructor=self.teacher,
                lesson_hours=30,
            )
            enrollment = Enrollment.objects.create(
                organization=self.org, student=self.candidate_records[0].student, offering=offering
            )
            lesson = Lesson.objects.create(
                organization=self.org, offering=offering, date="2026-10-02", kind="seminar", instructor=self.teacher
            )
            mark = LessonMark.objects.create(organization=self.org, enrollment=enrollment, lesson=lesson, score=6)
        result = self.applied()
        after = self.snapshot()
        with bypass_rls():
            mark.refresh_from_db()
            self.assertEqual(mark.score, 6)
            enrollment.refresh_from_db()
            self.assertEqual(enrollment.status, "enrolled")
        with self.assertRaisesMessage(RepairError, "preexisting_child_roster_requires_reviewed_compensation"):
            self.execute(undo=result["batch"])
        self.assertEqual(self.snapshot(), after)

    def test_second_active_program_record_is_never_chosen_by_name_or_headcount(self):
        with bypass_rls():
            record = self.candidate_records[0]
            program = Program.objects.create(
                organization=self.org,
                specialty_unit=record.program.specialty_unit,
                code="ANOTHER",
                name="Parallel",
                official_code="6004002",
            )
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2026)
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=record.student,
                program=program,
                curriculum=curriculum,
                group=record.group,
                admission_year=2026,
            )
        with self.assertRaisesMessage(RepairError, "unique_active_current_account_and_record_required"):
            self.execute()

    def test_unreviewed_mark_change_from_any_nested_writer_rolls_back_every_move(self):
        before = self.snapshot()
        original = repair.transfer.transfer_student_group
        calls = []

        def changed(**kwargs):
            result = original(**kwargs)
            if not calls:
                LessonMark.objects.filter(enrollment__student=self.candidate_records[0].student).update(score=2)
            calls.append(1)
            return result

        with patch.object(repair.transfer, "transfer_student_group", side_effect=changed):
            with self.assertRaisesMessage(RepairError, "academic_content_changed"):
                self.execute()
        self.assertEqual(self.snapshot(), before)

    def test_extra_account_profile_is_fully_protected_without_exporting_private_fields(self):
        original = repair.transfer.transfer_student_group
        calls = []
        extra = self.extras[0].student
        with bypass_rls():
            before = UserProfile.objects.get(user=extra).patronymic

        def changed(**kwargs):
            result = original(**kwargs)
            if not calls:
                UserProfile.objects.filter(user=extra).update(patronymic="Unreviewed change")
            calls.append(1)
            return result

        with patch.object(repair.transfer, "transfer_student_group", side_effect=changed):
            with self.assertRaisesMessage(RepairError, "account_profile_or_credential_changed"):
                self.execute()
        with bypass_rls():
            self.assertEqual(UserProfile.objects.get(user=extra).patronymic, before)

    def test_later_academic_write_blocks_undo(self):
        result = self.applied()
        with bypass_rls():
            LessonMark.objects.filter(enrollment__student=self.candidate_records[0].student).update(score=10)
        with self.assertRaisesMessage(RepairError, "undo_requires_unchanged_receipt"):
            self.execute(undo=result["batch"])

    def test_initial_target_child_without_prior_receipt_is_not_silently_accepted(self):
        from apps.registrar.public import transfer

        with bypass_rls():
            transfer.transfer_student_group(
                record=self.candidate_records[0],
                new_group=self.children[contract.BI.name][2],
                period=self.period,
                by_user=self.actor,
                reason="outside transfer",
            )
        with self.assertRaisesMessage(RepairError, "current_full_identity_program_year_or_group_changed"):
            self.execute()


class BiMuUndoTransactionTests(TransactionTestCase):
    def setUp(self):
        BiMuRosterTests.setUpTestData.__func__(type(self))
        BiMuRosterTests.setUp(self)

    execute = BiMuRosterTests.execute
    snapshot = BiMuRosterTests.snapshot
    applied = BiMuRosterTests.applied

    def test_undo_preserves_marks_and_restores_parent_groups_without_deleting_history(self):
        result = self.applied()
        with bypass_rls():
            old_mark_ids = set(LessonMark.objects.values_list("pk", flat=True))
        dry = self.execute(undo=result["batch"])
        undone = self.execute(undo=result["batch"], apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(undone["restored_students"], 41)
        with bypass_rls():
            self.assertEqual(set(LessonMark.objects.values_list("pk", flat=True)), old_mark_ids)
            for record in self.candidate_records:
                record.refresh_from_db()
                self.assertIn(str(record.group_id), {contract.BI.parent, contract.MU.parent})
            self.assertEqual(AuditLog.objects.filter(resource_type=contract.RESOURCE).count(), 2)


def model_count(label):
    from django.apps import apps

    return apps.get_model(label).objects.count()
