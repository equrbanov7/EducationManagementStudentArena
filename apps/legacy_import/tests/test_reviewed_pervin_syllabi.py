"""Original source60/current official45, two approvals and unchanged live academic closure."""

import copy
import hashlib
import json
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationRun
from apps.legacy_import.services import exact_syllabus_recovery as core
from apps.legacy_import.services import reviewed_pervin_syllabus_recovery as recovery
from apps.legacy_import.services import reviewed_pervin_syllabus_source as source_loader
from apps.legacy_import.services import reviewed_pervin_syllabus_spec as spec
from apps.legacy_import.services import reviewed_pervin_syllabus_state as state
from apps.legacy_import.services.delta.syllabi import document_for
from apps.legacy_import.services.rehearsal_syllabus_targets import build_section_data
from apps.legacy_import.tests import test_workload_syllabi as fixtures
from apps.legacy_import.tests.test_workload_syllabi import plan
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.syllabus.models import Syllabus, SyllabusVersion
from apps.syllabus.public import content_fingerprints, import_migrated_version, section_data_map
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow


def fixture_source():
    source = plan()["source"]
    source.update(id=8573, teacher_id=213, lesson_id=2125, uniqid="pervin-exact-source", ders_saati=60, language="en")
    source["week"] = [
        dict(
            id=1000 + i,
            uniqid=source["uniqid"],
            movzu=f"Exact own original topic {i}",
            muh_saat="2" if i % 2 == 0 else "0",
            sem_saat="2" if i % 2 else "0",
            praktiki_saat="0",
            lab_saat="0",
            qeyd="original note",
        )
        for i in range(30)
    ]
    source["sections"]["sillabus_serbest_is"] = [[i, f"Own selfwork {i}"] for i in range(10)]
    for table in (
        "sillabus_certificates",
        "sillabus_qarsilama_mesaji",
        "sillabus_elmi_maraq",
        "sillabus_imtahan_suallari",
    ):
        source["sections"][table] = [[55, ""]]
    return source


class ReviewedPervinTests(TestCase):
    setUpTestData = classmethod(fixtures.WorkloadSyllabusTests.setUpTestData.__func__)

    def assert_others_unchanged(self):
        fixtures.WorkloadSyllabusTests.assert_others_unchanged(self)

    def setUp(self):
        super().setUp()
        self.subject.code = "QKU-219"
        self.subject.save(update_fields=["code"])
        self.offering.lesson_hours = 45
        self.offering.save(update_fields=["lesson_hours"])
        second = OrgUnit.objects.create(organization=self.org, name="334F2", slug="pervin-f2", unit_type="group")
        self.second = CourseOffering.objects.create(
            organization=self.org,
            subject=self.subject,
            period=self.period,
            group=second,
            instructor=self.author,
            lesson_hours=45,
        )
        self.task = TeachingTask.objects.create(
            organization=self.org, academic_year="2026/2027", chair=self.offering.group, status="amended"
        )
        self.row = TeachingTaskRow.objects.create(
            organization=self.org,
            task=self.task,
            subject=self.subject,
            period=self.period,
            season="fall",
            lecture_plan=15,
            lecture_total=15,
            seminar_plan=30,
            seminar_total=30,
            total_hours=45,
        )
        self.row.groups.add(self.offering.group, second)
        assignments = []
        for activity, hours in (("lecture", 15), ("seminar", 30)):
            assignments.append(
                TeacherAssignment.objects.create(
                    organization=self.org, row=self.row, teacher=self.author, activity=activity, hours=hours
                )
            )
        self.lesson = Lesson.objects.create(
            organization=self.org, offering=self.offering, date=self.period.start_date, kind="lecture", hours=1
        )
        fields = ("entity_type", "legacy_pk", "source_row_hash", "state", "target_model_label", "target_pk")
        bridges = []
        run = LegacyMigrationRun.objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode="profile",
        )
        LegacyMigrationRun.objects.filter(pk=run.pk).update(status="running", started_at=timezone.now())

        for entity, old, label, target in (
            ("worker", "213", "auth.user", self.author.pk),
            ("group_unit", "739", "organizations.orgunit", self.offering.group_id),
            ("group_unit", "740", "organizations.orgunit", second.pk),
            ("lesson_subject", "219", "registrar.subject", self.subject.pk),
        ):
            record = LegacyEntityMap.objects.create(
                created_run=run,
                transform_version="v1",
                organization=self.org,
                source_system="myedu_mariadb",
                entity_type=entity,
                legacy_pk=old,
                target_model_label=label,
                target_pk=str(target),
                state="migrated",
                source_row_hash="a" * 64,
            )
            bridges.append({k: getattr(record, k) for k in fields})

        self.pins = copy.deepcopy(spec.PINS)
        self.pins.update(
            organization_id=str(self.org.pk),
            period_id=str(self.period.pk),
            teacher=self.author.pk,
            subject=str(self.subject.pk),
            row_id=str(self.row.pk),
            row_fields={
                "subject_id": str(self.subject.pk),
                "lecture_plan": 15,
                "lecture_total": 15,
                "seminar_plan": 30,
                "seminar_total": 30,
                "total_hours": 45,
            },
            task={"id": str(self.task.pk), "academic_year": "2026/2027", "status": "amended"},
            assignments={
                str(a.pk): {
                    "row_id": str(self.row.pk),
                    "teacher_id": self.author.pk,
                    "activity": a.activity,
                    "hours": a.hours,
                }
                for a in assignments
            },
            offerings={str(o.pk): {"group_id": str(o.group_id)} for o in (self.offering, self.second)},
            bridges=bridges,
            schema=state.reviewed_catalog_schema.fingerprints(),
            rosters={str(o.pk): [] for o in (self.offering, self.second)},
            counts={
                str(self.offering.pk): {"enrollments": 0, "lessons": 1, "marks": 0},
                str(self.second.pk): {"enrollments": 0, "lessons": 0, "marks": 0},
            },
        )
        src = fixture_source()
        sections, codes = build_section_data(document_for(src))
        self.sections = sections
        self.codes = codes
        self.journal = dict(
            id=14133,
            teacher_id=213,
            lesson_id=219,
            sillabus_id=8573,
            semestr=14,
            groups_id='["739","740"]',
            name="2026/2027 Payız",
        )
        self.package = dict(
            format="reviewed-pervin-own60-syllabus/1",
            organization_id=str(self.org.pk),
            selected_targets=list(self.pins["offerings"]),
            source=src,
            source_journal=self.journal,
            source_subject_alias={
                "journal_subject": 219,
                "syllabus_subject": 2125,
                "scope": "fixed direct pointer14133→8573 only; no global alias authority",
            },
            legacy_source_approval_asserted=False,
            current_approval_authority="explicit_user_reviewed_own_source_recovery",
            official_current_hours={"lecture": 15, "seminar": 30, "total": 45},
            preserved_source_hours={"lecture": 30, "seminar": 30, "total": 60},
        )
        self.raw = json.dumps(self.package, sort_keys=True).encode()
        self.source_sha = hashlib.sha256(self.raw).hexdigest()
        for name, value in (
            ("PINS", self.pins),
            ("COURSES", tuple(self.pins["offerings"])),
            ("ORG", str(self.org.pk)),
            ("PERIOD", str(self.period.pk)),
            ("SOURCE_SHA", self.source_sha),
            ("SOURCE_DIGEST", core.digest(src)),
            ("JOURNAL_DIGEST", core.digest(self.journal)),
            ("BODY_SHA", content_fingerprints(sections)["canonical_body_sha256"]),
        ):
            manager = patch.object(spec, name, value)
            manager.start()
            self.addCleanup(manager.stop)
        date = patch.object(state.timezone, "localdate", return_value=self.period.start_date)
        date.start()
        self.addCleanup(date.stop)

    def call(self, **kwargs):
        return recovery.run(organization=self.org, actor=self.actor, loaded=(self.sections, self.codes), **kwargs)

    def test_actual_source_loader_keeps_all60_hours_and_reviewed_lossless_warnings(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(self.raw)
            f.flush()
            sections, codes = source_loader.load(f.name, self.source_sha)
            self.assertEqual(sections, self.sections)
            self.assertEqual(
                set(codes),
                {
                    "legacy_syllabus_week_rows_exceed_plan",
                    "legacy_syllabus_assessment_note_unsurfaced",
                    "legacy_syllabus_blank_row_dropped",
                },
            )
            self.assertEqual(len(sections["week"]["rows"]), 30)
            self.assertEqual(sections["info"]["lesson_hours"], 60)
            changed = self.raw.replace(b"original topic", b"changed topic")
            f.seek(0)
            f.truncate()
            f.write(changed)
            f.flush()
            with self.assertRaisesMessage(core.RestoreError, "pervin_exact_source_packet_required"):
                source_loader.load(f.name, self.source_sha)

    def test_apply_repeat_and_undo_preserve_original60_official45_and_existing_lesson(self):
        before = core.metadata_digest(self.lesson)
        dry = self.call()
        self.assertEqual(dry["status"], "dry_run")
        self.assertFalse(Syllabus.objects.filter(offering_id__in=spec.COURSES).exists())
        result = self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(result["versions_created"], 2)
        self.assertEqual(self.call()["status"], "already_present")
        for obj in (self.offering, self.second):
            obj.refresh_from_db()
            self.assertEqual(obj.lesson_hours, 45)
            syl = Syllabus.objects.get(offering=obj)
            v = syl.current_version
            self.assertEqual(v.plan_hours, {"lecture": 30, "seminar": 30, "practical": 0, "lab": 0})
            self.assertEqual(section_data_map(v), self.sections)
            self.assertEqual(v.status, "approved")
            self.assertEqual(v.approval_source, "migration")
            self.assertIsNone(v.approved_by_id)
            self.assertIn("45", v.decision_reason)
            self.assertIn("60", v.decision_reason)
        self.lesson.refresh_from_db()
        self.assertEqual(core.metadata_digest(self.lesson), before)
        undo = self.call(undo=result["receipt"])
        self.assertEqual(
            self.call(undo=result["receipt"], apply=True, expected_baseline=undo["baseline"])["versions_archived"], 2
        )
        self.assertEqual(self.call(undo=result["receipt"])["status"], "already_undone")
        self.assert_others_unchanged()

    def test_stale_dry_and_late_lesson_on_undo_are_not_ignored(self):
        dry = self.call()
        self.lesson.topic = "new teacher note"
        self.lesson.save(update_fields=["topic"])
        with self.assertRaisesMessage(core.RestoreError, "pervin_fresh_baseline_required"):
            self.call(apply=True, expected_baseline=dry["baseline"])
        result = self.call(apply=True, expected_baseline=self.call()["baseline"])
        self.lesson.topic = "later teacher note"
        self.lesson.save(update_fields=["topic"])
        with self.assertRaisesMessage(core.RestoreError, "pervin_post_restore_graph_changed"):
            self.call(undo=result["receipt"])

    def test_new_human_syllabus_is_never_overwritten(self):
        import_migrated_version(
            organization=self.org,
            subject=self.subject,
            offering=self.second,
            period=self.period,
            author=self.author,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "real teacher content"}},
        )
        with self.assertRaisesMessage(core.RestoreError, "pervin_existing_syllabus_no_overwrite"):
            self.call()
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_official_budget_source_schema_and_group_drift_hold(self):
        self.row.lecture_plan = 30
        self.row.save(update_fields=["lecture_plan"])
        with self.assertRaisesMessage(core.RestoreError, "pervin_fixed_identity_or_allocation_changed"):
            self.call()
        self.row.lecture_plan = 15
        self.row.save(update_fields=["lecture_plan"])
        with patch.object(state.reviewed_catalog_schema, "fingerprints", return_value={}):
            with self.assertRaisesMessage(core.RestoreError, "pervin_unreviewed_relation_schema"):
                self.call()
        self.second.lesson_hours = 60
        self.second.save(update_fields=["lesson_hours"])
        with self.assertRaisesMessage(core.RestoreError, "pervin_official45_current_period_required"):
            self.call()

    def test_partial_second_import_failure_rolls_back_first(self):
        original = recovery.import_migrated_version
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise core.RestoreError("pervin_source_import_changed")
            return original(**kwargs)

        dry = self.call()
        with patch.object(recovery, "import_migrated_version", side_effect=fail_second):
            with self.assertRaisesMessage(core.RestoreError, "pervin_source_import_changed"):
                self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertFalse(Syllabus.objects.filter(offering_id__in=spec.COURSES).exists())

    def test_own_source_modified_body_or_extra_version_blocks_repeat_and_undo(self):
        result = self.call(apply=True, expected_baseline=self.call()["baseline"])
        syllabus = Syllabus.objects.get(offering=self.second)
        row = syllabus.current_version.sections.get(section_id="desc")
        row.data = {"description": "later human content"}
        row.save(update_fields=["data"])
        with self.assertRaisesMessage(core.RestoreError, "pervin_exact_original60_approved_body_changed"):
            self.call(undo=result["receipt"])
        self.assertEqual(SyllabusVersion.objects.filter(syllabus=syllabus, status="approved").count(), 1)

    def test_zero_absence_excused_and_present_marks_are_preserved_and_late_grade_holds_undo(self):
        marks = []
        for index, (status, score) in enumerate(
            (("present", 0), ("absent", None), ("excused", None), ("present", None))
        ):
            student = get_user_model().objects.create_user(id=300001 + index, username=f"pervin-student-{index}")
            core.model("accounts.UserProfile").objects.filter(user=student).update(organization=self.org)
            Membership.objects.create(user=student, organization=self.org, role=self.org.roles.get(name="student"))
            enrollment = Enrollment.objects.create(organization=self.org, offering=self.offering, student=student)
            marks.append(
                LessonMark.objects.create(
                    organization=self.org,
                    lesson=self.lesson,
                    enrollment=enrollment,
                    status=status,
                    score=score,
                    entered_by=self.author,
                )
            )
        self.pins["rosters"][str(self.offering.pk)] = [m.enrollment.student_id for m in marks]
        self.pins["counts"][str(self.offering.pk)].update(enrollments=4, marks=4)
        before = state.e.bounded(LessonMark.objects.filter(pk__in=[m.pk for m in marks]))
        result = self.call(apply=True, expected_baseline=self.call()["baseline"])
        self.assertEqual(before, state.e.bounded(LessonMark.objects.filter(pk__in=[m.pk for m in marks])))
        self.assertEqual(self.call()["status"], "already_present")
        marks[0].score = 1
        marks[0].save(update_fields=["score"])
        with self.assertRaisesMessage(core.RestoreError, "pervin_post_restore_graph_changed"):
            self.call(undo=result["receipt"])
