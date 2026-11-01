"""PG: two distinct original flows, legitimate extra students, no outcome/body moves."""

import copy
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.registrar.public import teacher_journal_list
from apps.workload.services import reviewed_aida_catalog_repair as repair
from apps.workload.services import reviewed_aida_catalog_spec as spec
from apps.workload.services import reviewed_aida_catalog_state as state
from apps.workload.services import reviewed_two_catalog_schema as schema
from apps.workload.services import reviewed_two_catalog_spec as two_spec
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError, digest, normal
from apps.workload.tests import test_reviewed_two_catalog as fixtures


class AidaCatalogTests(TestCase):
    setUpTestData = classmethod(fixtures.TwoCatalogTests.setUpTestData.__func__)

    def setUp(self):
        fixtures.TwoCatalogTests.setUp(self)
        Offering = apps.get_model("registrar", "CourseOffering")
        Enrollment = apps.get_model("registrar", "Enrollment")
        LegacyMap = apps.get_model("legacy_import", "LegacyEntityMap")
        # The real53/2038 source aliases both have ECTS5; model that authority,
        # rather than borrowing the generic fixture's unrelated catalogue fallback.
        type(self.rows[0].subject).objects.filter(pk=self.rows[0].subject_id).update(ects=self.filled[0].subject.ects)
        pin = copy.deepcopy(two_spec.CASES[0])
        source = self.syllabi[0][1].sections.get(section_id="week")
        source.data = {
            "rows": [
                {
                    "topic": f"Own original source topic{idx}",
                    "lecture": 2,
                    "seminar": 2 if idx < 6 else 1 if idx == 6 else 0,
                }
                for idx in range(15)
            ]
        }
        source.save()
        pin["donor"]["body_sha256"] = state.common.content_fingerprints(
            {section.section_id: section.data for section in self.syllabi[0][1].sections.all()}
        )["canonical_body_sha256"]

        king_group = self.stacks[1]["group"]
        self.rows[0].groups.add(king_group)
        self.king = Offering.objects.create(
            organization=self.org,
            period=self.period,
            group=king_group,
            subject=self.rows[0].subject,
            instructor=self.teacher,
            lesson_hours=45,
        )
        # Original King journal is independently filled; never merged with IT canonical.
        enrs = []
        for enr in Enrollment.objects.filter(offering=self.filled[1])[:2]:
            enrs.append(Enrollment.objects.create(organization=self.org, offering=self.king, student=enr.student))
        self.king_lesson = apps.get_model("registrar", "Lesson").objects.create(
            organization=self.org,
            offering=self.king,
            date="2026-09-18",
            hours=2,
            kind="lecture",
            topic="Original King source class",
        )
        self.king_mark = apps.get_model("registrar", "LessonMark").objects.create(
            organization=self.org,
            lesson=self.king_lesson,
            enrollment=enrs[0],
            score=0,
            status="present",
            entered_by=self.teacher,
        )
        self.extras = {}
        original_run = LegacyMap.objects.first().created_run
        for idx in range(3):
            student = get_user_model().objects.create_user(f"retained-aida-source-extra-{idx}")
            fixtures.fixtures.activate_member(self.org, student, "student", permissions=["course.view", "grade.view"])
            Enrollment.objects.create(
                organization=self.org,
                offering=self.filled[0],
                student=student,
                source_group=king_group,
                added_by=self.actor,
            )
            legacy = 90000 + idx
            LegacyMap.objects.create(
                organization=self.org,
                source_system="myedu_mariadb",
                entity_type="student",
                legacy_pk=str(legacy),
                target_pk=str(student.pk),
                target_model_label="auth.user",
                state="migrated",
                source_row_hash="c" * 64,
                transform_version="fixture_v1",
                created_run=original_run,
            )
            self.extras[str(student.pk)] = {
                "legacy_id": legacy,
                "source_group_id": str(king_group.pk),
                "source_points": 1,
            }
        pin["offerings"][str(self.king.pk)] = normal(
            {
                k: getattr(self.king, k)
                for k in ("id", "group_id", "period_id", "subject_id", "instructor_id", "is_active", "lesson_hours")
            }
        )
        offers = [self.empty[0], self.filled[0], self.king]
        pin["counts"] = {
            r["offering_id"]: r for r in normal(state.common.snapshots.offering_counts([o.pk for o in offers]))
        }
        roster = {
            str(o.pk): sorted(
                Enrollment.objects.filter(offering=o, status="enrolled").values_list("student_id", flat=True)
            )
            for o in offers
        }
        row = normal(type(self.rows[0]).objects.filter(pk=self.rows[0].pk).values().get())
        task = normal(type(self.task).objects.filter(pk=self.task.pk).values().get())
        config = dict(
            source={
                "original_source_rows": 523,
                "official_budget": 45,
                "missing_source_seminar_hours": 2,
                "existing_own_approved_share_authorized": True,
            },
            row_fields={k: v for k, v in row.items() if k not in ("id", "subject_id")},
            task={k: task[k] for k in ("id", "chair_id", "academic_year", "status", "revision")},
            assignments=pin["assignments"],
            extra_students=self.extras,
            groups={
                str(g.pk): normal(
                    {
                        k: getattr(g, k)
                        for k in ("id", "code", "name", "parent_id", "unit_type", "settings", "is_active")
                    }
                )
                for g in (self.stacks[0]["group"], king_group)
            },
            rosters={oid: {"count": len(ids), "sha256": digest(ids)} for oid, ids in roster.items()},
        )
        for key, value in dict(
            ORG=str(self.org.pk),
            PERIOD=str(self.period.pk),
            YEAR=self.period.academic_year,
            CASE=pin,
            ROW=str(self.rows[0].pk),
            KING=str(self.king.pk),
            PINS=config,
            SCHEMA=schema.fingerprints(),
        ).items():
            self.patches.enter_context(patch.object(spec, key, copy.deepcopy(value)))
        self.exam = apps.get_model("exams", "Exam").objects.create(
            organization=self.org, author=self.teacher, subject=self.rows[0].subject, title="Original King linked exam"
        )
        self.exam.journal_offerings.add(self.king)
        self.attempt = apps.get_model("exams", "ExamAttempt").objects.create(
            exam=self.exam,
            user=enrs[0].student,
            status="submitted",
            correct_count=0,
            wrong_count=20,
        )
        question = apps.get_model("exams", "ExamQuestion").objects.create(
            exam=self.exam, text="Preserve original question"
        )
        self.answer = apps.get_model("exams", "ExamAnswer").objects.create(
            attempt=self.attempt, question=question, is_correct=False
        )

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, actor=self.actor, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_two_fk_apply_repeat_exact_undo_preserves_all_three_flows_extras_and_exam(self):
        before = state.snapshot(self.org)
        assignments = copy.deepcopy(before["assignments"])
        total = sum(a["hours"] for a in assignments)
        old_subject = self.exam.subject_id
        result = self.apply()
        after = state.snapshot(self.org)
        self.assertEqual(state.protected(before), state.protected(after))
        self.assertEqual(after["assignments"], assignments)
        self.assertEqual(sum(a["hours"] for a in after["assignments"]), total)
        self.assertEqual(len(after["academic"]["exams.ExamAnswer"]), 1)
        self.assertEqual(len(after["shares"]), 1)
        self.assertEqual(after["shares"][0]["syllabus_id"], spec.CASE["donor"]["id"])
        self.exam.refresh_from_db()
        self.answer.refresh_from_db()
        self.king.refresh_from_db()
        self.assertEqual(self.exam.subject_id, old_subject)
        self.assertEqual(list(self.exam.journal_offerings.values_list("pk", flat=True)), [self.king.pk])
        self.assertFalse(self.answer.is_correct)
        self.assertEqual(self.king.subject_id, self.filled[0].subject_id)
        self.assertEqual(self.run_repair(apply=True)["status"], "already_applied")
        dry = self.run_repair(undo=result["receipt"])
        self.run_repair(undo=result["receipt"], apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org), before)

    def test_teacher_current_journals_are_two_distinct_filled_flows_without_new_rights(self):
        ids = [self.empty[0].pk, self.filled[0].pk, self.king.pk]
        qs = type(self.king).objects.filter(pk__in=ids, organization=self.org)
        self.apply()
        visible = teacher_journal_list.project(qs, self.teacher, self.org)
        current = set(visible.filter(journal_is_current_load=True).values_list("pk", flat=True))
        self.assertEqual(current, {self.king.pk, self.filled[0].pk})
        self.assertNotIn(self.empty[0].pk, current)

    def test_stale_exam_body_and_outcome_after_apply_blocks_undo(self):
        result = self.apply()
        type(self.answer).objects.filter(pk=self.answer.pk).update(is_correct=True)
        with self.assertRaisesRegex(RepairError, "undo_state_changed"):
            self.run_repair(undo=result["receipt"])

    def test_changed_official_budget_or_partial_alias_refused(self):
        type(self.rows[0]).objects.filter(pk=self.rows[0].pk).update(lecture_total=29)
        with self.assertRaisesRegex(RepairError, "budget_or_credit_changed"):
            self.run_repair()
        type(self.rows[0]).objects.filter(pk=self.rows[0].pk).update(lecture_total=30, subject=self.filled[0].subject)
        with self.assertRaisesRegex(RepairError, "partial_alias_state"):
            self.run_repair()

    def test_source_extra_student_mapping_or_enrollment_drift_refused(self):
        uid = next(iter(self.extras))
        changed = copy.deepcopy(spec.PINS)
        changed["extra_students"][uid]["source_group_id"] = str(self.stacks[2]["group"].pk)
        with patch.object(spec, "PINS", changed):
            with self.assertRaisesRegex(RepairError, "provenance_changed"):
                self.run_repair()

    def test_new_relation_or_canonical_king_collision_refused(self):
        with patch.object(schema, "fingerprints", return_value={}):
            with self.assertRaisesRegex(RepairError, "unreviewed_relation_schema"):
                self.run_repair()
        type(self.king).objects.create(
            organization=self.org,
            group=self.king.group,
            period=self.period,
            instructor=self.teacher,
            subject=self.filled[0].subject,
            lesson_hours=45,
        )
        with self.assertRaisesRegex(RepairError, "existing_canonical_king"):
            self.run_repair()

    def test_new_king_human_syllabus_is_held_not_rewritten(self):
        apps.get_model("syllabus", "Syllabus").objects.create(
            organization=self.org,
            offering=self.king,
            subject=self.king.subject,
            period=self.period,
            author=self.teacher,
            chair_unit=self.task.chair,
        )
        with self.assertRaisesRegex(RepairError, "new_king_syllabus"):
            self.run_repair()

    def test_failure_after_first_fk_rolls_back_whole_source_scope(self):
        before = state.snapshot(self.org)
        dry = self.run_repair()
        with patch.object(state, "snapshot", side_effect=[before, RepairError("forced_post_guard")]):
            with self.assertRaisesRegex(RepairError, "forced_post_guard"):
                self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org), before)

    def test_parent_identity_guard_remains_enabled_and_scoped_context_is_cleared(self):
        from django.db import IntegrityError, connection, transaction

        self.apply()
        with connection.cursor() as cur:
            cur.execute(
                "SELECT current_setting('app.registrar_subject_merge_from',true), current_setting('app.registrar_subject_merge_to',true)"
            )
            self.assertEqual(cur.fetchone(), ("", ""))
        with self.assertRaises(IntegrityError), transaction.atomic():
            type(self.king).objects.filter(pk=self.king.pk).update(subject=self.empty[0].subject)
        self.king.refresh_from_db()
        self.assertEqual(self.king.subject_id, self.filled[0].subject_id)

    def test_changed_own_source_body_and_schedule_conflicts_are_not_overwritten(self):
        Slot = apps.get_model("registrar", "ScheduleSlot")
        slot = Slot.objects.create(
            organization=self.org,
            offering=self.king,
            weekday=5,
            start_time="16:00",
            end_time="17:30",
            kind="lecture",
            room="Preserve room",
        )
        with patch.object(state.common.schedule_conflicts, "detect", return_value=[{"conflict": True}]):
            with self.assertRaisesRegex(RepairError, "target_schedule_conflict"):
                self.run_repair()
        slot.refresh_from_db()
        self.assertFalse(slot.is_parked)
        source = self.syllabi[0][1].sections.first()
        type(source).objects.filter(pk=source.pk).update(data={"description": "Different own approved body"})
        with self.assertRaisesRegex(RepairError, "approved_source_body_changed"):
            self.run_repair()

    def test_cli_default_dry_cannot_change_contact_hours_or_enrollments(self):
        from io import StringIO

        from django.core.management import call_command

        before = state.snapshot(self.org)
        output = StringIO()
        call_command("repair_reviewed_aida_catalog", actor=self.actor.username, stdout=output)
        self.assertTrue(output.getvalue().startswith("reviewed_aida_catalog: status=dry_run rows=2 applied=0 "))
        self.assertEqual(state.snapshot(self.org), before)

    def test_alias_cannot_silently_lower_effective_student_credit(self):
        # Catalogue is the fallback for this fixture; curricular drift is not an alias permission.
        subject = self.rows[0].subject
        type(subject).objects.filter(pk=subject.pk).update(ects=99)
        before = state.snapshot(self.org)
        dry = self.run_repair()
        with self.assertRaisesRegex(RepairError, "effective_student_credits_changed"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org), before)

    def test_exact43_of_declared45_approved_source_restores_without_new_version_or_invented_hours(self):
        Version = apps.get_model("syllabus", "SyllabusVersion")
        counts = Version.objects.count()
        version = self.syllabi[0][1]
        original = {s.section_id: copy.deepcopy(s.data) for s in version.sections.all()}
        self.apply()
        self.king.refresh_from_db()
        selected = state.common.syllabus_for_offering(
            organization=self.org,
            offering_id=self.king.pk,
            subject_id=self.king.subject_id,
            period_id=self.period.pk,
            instructor_id=self.teacher.pk,
        )
        approved = state.common.approved_version_for(selected)
        self.assertEqual(str(selected.pk), spec.CASE["donor"]["id"])
        self.assertEqual(approved.pk, version.pk)
        self.assertEqual(Version.objects.count(), counts)
        actual = {s.section_id: s.data for s in approved.sections.all()}
        self.assertEqual(actual, original)
        topic = state.common.content_fingerprints(actual)["topic_summary"]
        self.assertEqual(topic["nonempty_topic_count"], 15)
        self.assertEqual(topic["hours_by_kind"], {"lecture": 30, "seminar": 13, "lab": 0, "practical": 0})
        self.assertEqual(self.king.lesson_hours, 45)

    def test_shared_standard_metadata_independently_exposes_only_new_own_source_link(self):
        from apps.workload.services.scoped_snapshot import data

        before = data.collect(student_secret=b"x" * 32)["syllabus_shares"]
        self.assertEqual(before, [])
        self.apply()
        after = data.collect(student_secret=b"x" * 32)["syllabus_shares"]
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]["offering_id"], self.king.pk)
        self.assertEqual(str(after[0]["syllabus_id"]), spec.CASE["donor"]["id"])
        self.assertEqual(after[0]["source"], "legacy")
        self.assertEqual(after[0]["created_by_id"], self.actor.pk)
