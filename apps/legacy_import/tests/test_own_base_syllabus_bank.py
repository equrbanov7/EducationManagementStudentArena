"""Fixed own BASE bank: fresh skip, explicit share, unchanged academic IDs and exact undo."""

import copy
import hashlib
import json
import tempfile
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.legacy_import.services import exact_syllabus_recovery as core
from apps.legacy_import.services import own_base_syllabus_bank as bank
from apps.legacy_import.services import own_base_syllabus_source as source
from apps.legacy_import.services import own_base_syllabus_spec as spec
from apps.legacy_import.services.delta.syllabi import document_for
from apps.legacy_import.services.rehearsal_syllabus_targets import build_section_data
from apps.legacy_import.tests import test_workload_syllabi as fixtures
from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.syllabus.models import Syllabus, SyllabusShare, SyllabusVersion
from apps.syllabus.public import import_migrated_version, section_data_map
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow


class OwnBaseBankTests(TestCase):
    setUpTestData = classmethod(fixtures.WorkloadSyllabusTests.setUpTestData.__func__)

    def setUp(self):
        super().setUp()
        self.org = type(self.org).objects.get(pk=self.org.pk)
        self.author.first_name, self.author.last_name = "Own", "Teacher"
        self.author.save()
        self.author.profile.organization = self.org
        self.author.profile.access_state = "active"
        self.author.profile.patronymic = "Father"
        self.author.profile.save()
        self.offering.lesson_hours = 30
        self.offering.save(update_fields=["lesson_hours"])
        self.offering.group.settings = {"education_form": "full_time"}
        self.offering.group.save()
        other = OrgUnit.objects.create(
            organization=self.org,
            name="own second",
            slug="own-second",
            unit_type="group",
            settings={"education_form": "full_time"},
        )
        self.second = CourseOffering.objects.create(
            organization=self.org,
            subject=self.subject,
            period=self.period,
            group=other,
            instructor=self.author,
            lesson_hours=30,
        )
        task = TeachingTask.objects.create(
            organization=self.org, academic_year="2026/2027", chair=self.offering.group, status="amended"
        )
        row = TeachingTaskRow.objects.create(
            organization=self.org,
            task=task,
            subject=self.subject,
            period=self.period,
            season="fall",
            lecture_plan=15,
            lecture_total=15,
            seminar_plan=15,
            seminar_total=30,
            subgroup_count=2,
        )
        row.groups.add(self.offering.group, other)
        assignments = [
            TeacherAssignment.objects.create(organization=self.org, row=row, teacher=self.author, activity=k, hours=h)
            for k, h in (("lecture", 15), ("seminar", 30))
        ]
        self.raw = fixtures.plan()["source"]
        original, _ = build_section_data(document_for(self.raw))
        common = dict(
            teacher_id=self.author.pk,
            username=self.author.username,
            teacher="Own Teacher Father",
            subject_code=self.subject.code,
            subject_name=self.subject.name,
            subject_id=str(self.subject.pk),
            period_id=str(self.period.pk),
            group_settings={"education_form": "full_time"},
            source_id=self.raw["id"],
            source_author=self.raw["teacher_id"],
            source_subject=self.raw["lesson_id"],
            uniqid=self.raw["uniqid"],
            source_digest=core.digest(self.raw),
            hours=30,
            contact_hours=[15, 15, 0, 0],
            source_contact_hours=[15, 15, 0, 0],
            topics=8,
            raw_topics=8,
            language="az",
            source_status=0,
            rows=[
                {
                    "id": str(row.pk),
                    "task_id": str(task.pk),
                    "credits": "",
                    "lecture_plan": 15,
                    "seminar_plan": 15,
                    "seminar_total": 30,
                }
            ],
            assignments=[
                {
                    "id": str(a.pk),
                    "teacher_id": self.author.pk,
                    "hours": a.hours,
                    "activity": a.activity,
                    "row_id": str(row.pk),
                }
                for a in assignments
            ],
            tasks=[{"id": str(task.pk), "status": "amended"}],
            row_groups=[{"id": str(row.pk), "groups__id": str(g.pk)} for g in (self.offering.group, other)],
        )
        rows = [dict(common, offering_id=str(o.pk), group_id=str(o.group_id)) for o in (self.offering, self.second)]
        sections, _, converted = source.visible_sections(self.raw, rows[0])
        for r in rows:
            r.update(body_digest=core.digest(sections), original_body_digest=converted)
        self.rows = rows
        self.loaded = {r["offering_id"]: (copy.deepcopy(sections), [], converted) for r in rows}
        self.patches = [patch.object(spec, "ROWS", tuple(rows)), patch.object(spec, "PERIOD", str(self.period.pk))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.academic_counts = tuple(m.objects.count() for m in (Lesson, LessonMark, Enrollment, TeacherAssignment))

    def run_bank(self, apply=False, baseline="", undo=""):
        return bank.run(
            organization=self.org,
            actor=self.actor,
            loaded=self.loaded,
            apply=apply,
            expected_baseline=baseline,
            undo=undo,
        )

    def apply_bank(self):
        d = self.run_bank()
        return self.run_bank(True, d["baseline"])

    def test_readonly_then_four_source_pattern_shared_and_idempotent_undo(self):
        d = self.run_bank()
        self.assertEqual(d["ready"], 2)
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())
        a = self.run_bank(True, d["baseline"])
        self.assertEqual((a["versions_created"], a["shares_created"]), (1, 1))
        s = Syllabus.objects.get(offering=self.offering)
        v = s.approved_version
        self.assertEqual((v.status, v.approval_source, v.approved_by_id), ("approved", "migration", None))
        self.assertEqual(section_data_map(v), self.loaded[str(self.offering.pk)][0])
        self.assertEqual(SyllabusShare.objects.get(offering=self.second).syllabus_id, s.pk)
        self.assertEqual(self.run_bank()["status"], "already_present")
        self.assertEqual(
            tuple(m.objects.count() for m in (Lesson, LessonMark, Enrollment, TeacherAssignment)), self.academic_counts
        )
        before = self.run_bank()
        u = self.run_bank(True, before["baseline"], a["receipt"])
        self.assertEqual(u["status"], "undone")
        s.refresh_from_db()
        self.assertFalse(s.is_active)
        self.assertFalse(SyllabusShare.objects.filter(offering=self.second).exists())
        fixtures.WorkloadSyllabusTests.assert_others_unchanged(self)

    def test_new_correct_approved_is_skipped_without_overwrite(self):
        _, v = import_migrated_version(
            organization=self.org,
            subject=self.subject,
            offering=self.offering,
            period=self.period,
            author=self.author,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "New live approved"}},
        )
        d = self.run_bank()
        self.assertEqual(d["skip_approved"], 1)
        a = self.run_bank(True, d["baseline"])
        self.assertEqual(a["versions_created"], 1)
        self.assertEqual(section_data_map(v)["desc"]["description"], "New live approved")

    def test_meaningful_draft_is_never_overwritten(self):
        s = Syllabus.objects.create(
            organization=self.org, subject=self.subject, offering=self.offering, period=self.period, author=self.author
        )
        SyllabusVersion.objects.create(organization=self.org, syllabus=s, major=1, minor=0, status="draft")
        d = self.run_bank()
        self.assertGreaterEqual(d["skip_existing"], 1)
        self.run_bank(True, d["baseline"])
        self.assertEqual(s.versions.count(), 1)

    def test_new_syllabus_after_dry_run_refuses_stale_baseline(self):
        d = self.run_bank()
        Syllabus.objects.create(
            organization=self.org, subject=self.subject, offering=self.offering, period=self.period, author=self.author
        )
        with self.assertRaisesRegex(core.RestoreError, "fresh_baseline"):
            self.run_bank(True, d["baseline"])

    def test_changed_assignment_or_teacher_rejected_before_write(self):
        TeacherAssignment.objects.filter(pk=self.rows[0]["assignments"][0]["id"]).update(hours=14)
        with self.assertRaisesRegex(core.RestoreError, "official_assignments_changed"):
            self.run_bank()
        self.assertFalse(Syllabus.objects.filter(offering=self.offering).exists())

    def test_wrong_tenant_rejected(self):
        with patch.object(spec, "ORG", "00000000-0000-0000-0000-000000000000"):
            with self.assertRaises(core.RestoreError):
                self.run_bank()

    def test_source_wrong_subject_teacher_hours_and_missing_tables_rejected(self):
        for key, value in (("lesson_id", 999), ("teacher_id", 998), ("ders_saati", 35), ("active", 0)):
            raw = copy.deepcopy(self.raw)
            raw[key] = value
            with self.assertRaises(core.RestoreError):
                source.visible_sections(raw, self.rows[0])
        raw = copy.deepcopy(self.raw)
        raw["sections"].pop("sillabus_derslikler")
        with self.assertRaises(core.RestoreError):
            source.visible_sections(raw, self.rows[0])

    def test_welcome_and_exam_notes_survive_in_visible_fields_and_extensions(self):
        sections, _, _ = source.visible_sections(self.raw, self.rows[0])
        self.assertIn(sections["info"]["welcome"], sections["desc"]["description"])
        for question in sections["assess"]["exam_questions"]:
            self.assertIn(question, sections["assess"]["note"])

    def test_tampered_loaded_body_rejected(self):
        self.loaded[str(self.offering.pk)][0]["desc"]["description"] = "wrong"
        d = self.run_bank()
        with self.assertRaisesRegex(core.RestoreError, "loaded_source_changed"):
            self.run_bank(True, d["baseline"])

    def test_academic_edit_after_apply_stops_undo(self):
        a = self.apply_bank()
        self.offering.lesson_hours = 31
        self.offering.save()
        with self.assertRaises(core.RestoreError):
            self.run_bank(True, a["baseline"], a["receipt"])

    def test_sealed_packet_enforces_exact_source_set_and_raw_status(self):
        packet = dict(
            format=spec.FORMAT,
            organization_id=spec.ORG,
            targets=[r["offering_id"] for r in self.rows],
            unique_sources={str(self.raw["id"]): self.raw},
            raw_legacy_status={str(self.raw["id"]): 0},
            legacy_source_approval_asserted=False,
            current_approval_authority="explicit_user_reviewed_own_active_base_recovery",
        )
        with tempfile.NamedTemporaryFile() as f:
            raw = json.dumps(packet).encode()
            f.write(raw)
            f.flush()
            sha = hashlib.sha256(raw).hexdigest()
            with patch.object(spec, "SOURCE_SHA", sha):
                self.assertEqual(len(source.load(f.name, sha)), 2)
            with self.assertRaises(core.RestoreError):
                source.load(f.name, "0" * 64)

    def test_design_original_practical_topics_visible_as_seminar_only(self):
        from apps.registrar.journal_topics import syllabus_week_rows

        chair = OrgUnit.objects.create(
            organization=self.org, name="Dizayn kafedrası", slug="design-bank", unit_type="chair"
        )
        self.subject.chair_unit = chair
        self.subject.save(update_fields=["chair_unit"])
        self.offering.seminar_is_practical = True
        self.offering.save(update_fields=["seminar_is_practical"])
        _, version = import_migrated_version(
            organization=self.org,
            subject=self.subject,
            offering=self.offering,
            period=self.period,
            author=self.author,
            approved_at=timezone.now(),
            section_data={
                "week": {
                    "rows": [
                        {"topic": "Original practical topic", "practical": 60, "lecture": 0, "seminar": 0, "lab": 0}
                    ]
                }
            },
        )
        obj = CourseOffering.objects.select_related("subject__chair_unit").get(pk=self.offering.pk)
        self.assertEqual(syllabus_week_rows(obj)[0]["kinds"], ("seminar",))
        self.assertEqual(section_data_map(version)["week"]["rows"][0]["practical"], 60)
        self.assertEqual(syllabus_week_rows(obj)[0]["title"], "Original practical topic")
        # Same practical flag and source body outside Design must never turn into seminar/lecture.
        chair.name = "Other chair"
        chair.save(update_fields=["name"])
        obj = CourseOffering.objects.select_related("subject__chair_unit").get(pk=self.offering.pk)
        self.assertEqual(syllabus_week_rows(obj)[0]["kinds"], ())
        self.assertNotIn("lecture", syllabus_week_rows(obj)[0]["kinds"])

    def test_non_design_bank_practical_alias_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[0].update(source_id=4164, source_contact_hours=[0, 0, 60, 0], contact_hours=[0, 60, 0, 0])
        with patch.object(spec, "ROWS", tuple(rows)):
            with self.assertRaisesRegex(core.RestoreError, "fixed_design_practical_alias_required"):
                self.run_bank()

    def test_fixed_ordinary_batch_not_blocked_by_unready_design_metadata(self):
        rows = copy.deepcopy(self.rows)
        rows[0]["source_id"], rows[1]["source_id"] = 7121, 8839
        design = dict(rows[0], source_id=4164, offering_id="00000000-0000-0000-0000-000000000099")
        rows.append(design)
        loaded = dict(self.loaded)
        loaded[design["offering_id"]] = copy.deepcopy(loaded[rows[0]["offering_id"]])
        with patch.object(spec, "ROWS", tuple(rows)):
            dry = bank.run(organization=self.org, actor=self.actor, loaded=loaded, batch="ordinary")
            self.assertEqual(dry["cases"], 2)
            applied = bank.run(
                organization=self.org,
                actor=self.actor,
                loaded=loaded,
                batch="ordinary",
                apply=True,
                expected_baseline=dry["baseline"],
            )
            self.assertEqual(applied["versions_created"], 2)
            self.assertFalse(Syllabus.objects.filter(offering_id=design["offering_id"]).exists())
        with self.assertRaisesRegex(core.RestoreError, "fixed_batch_required"):
            bank.run(organization=self.org, actor=self.actor, batch="free-course")
