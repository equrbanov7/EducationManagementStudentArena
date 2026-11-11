"""Sahib 2026-11-11: dublikat fənlərin köklü həlli — ``merge_duplicate_subjects_20261111``.

Heç bir xana / bal itmir (mənbənin hər xanası ya hədəfdədir, ya da hər iki dəyəri ilə manifestdədir); eyni tarix +
saat + növ dərsi bir dərs olur; imtahan bağı və Midterm hədəf jurnala keçir; tələbə BİR kart görür; kataloq kartı
birləşir (passiv jurnal arxiv kartda qalır); kodlar ``QKU-N`` olur; geri qaytarma hər şeyi bərpa edir; imtahan verib
jurnalda olmayan tələbə alt qrup tələbəsi kimi (sənədsiz) əlavə olunur və nəticəsi yazılır.
"""

import datetime
import io
import pathlib
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.audit.models import AuditLog
from apps.exams.models import ExamAnswer, ExamAttempt
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.organizations.models import Membership, OrgUnit
from apps.registrar import duplicate_journal_merge_2026_11_11 as journal_merge
from apps.registrar import duplicate_subjects_2026_11_11 as duplicates
from apps.registrar import exam_bridge, interim_components, services
from apps.registrar.exam_journal_link import enrollment_coverage
from apps.registrar.models import (
    ComponentScore,
    CourseOffering,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    StudentAcademicRecord,
    SubgroupPlacementEvent,
    Subject,
)
from apps.syllabus.models import Syllabus
from core.constants import OrgUnitType
from core.rls import bypass_rls, journal_unlock

User = get_user_model()
D1, D2, D3 = datetime.date(2026, 10, 5), datetime.date(2026, 10, 8), datetime.date(2026, 10, 12)
T1 = datetime.time(10, 10)
WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class DuplicateSubjectsTest(_MidtermSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.twin = Subject.objects.create(organization=self.org, code="QKU-77", name="Proqram laşdırma")
            self.source = CourseOffering.objects.create(
                organization=self.org, subject=self.twin, group=self.group, period=self.period, instructor=self.teacher
            )
            self.s2 = self._student("dup_s2", self.group)
            self.w1 = Enrollment.objects.create(organization=self.org, student=self.student, offering=self.source)
            self.w2 = Enrollment.objects.create(organization=self.org, student=self.s2, offering=self.source)
            self.t_lecture = self._lesson(self.offering, D1, LessonKind.LECTURE)
            self.t_seminar = self._lesson(self.offering, D2, LessonKind.SEMINAR)
            self._mark(self.t_lecture, self.enrollment, "present")
            self._mark(self.t_seminar, self.enrollment, "present", 10)
            w_lecture = self._lesson(self.source, D1, LessonKind.LECTURE, topic="Giriş")
            w_seminar = self._lesson(self.source, D2, LessonKind.SEMINAR)
            w_extra = self._lesson(self.source, D3, LessonKind.LECTURE)
            self.conflict_mark = self._mark(w_lecture, self.w1, "absent")  # T-də «present» — FƏRQLİ
            self._mark(w_lecture, self.w2, "present")
            self._mark(w_seminar, self.w1, "present", 10)  # T ilə EYNİ
            self._mark(w_seminar, self.w2, "present", 9)
            self._mark(w_extra, self.w1, "present")
            self._mark(w_extra, self.w2, "absent")
            self.exam, self.options = self._exam(title="Dup MT")
            self.exam.subject = self.twin
            self.exam.save(update_fields=["subject"])
            self.exam.journal_offerings.add(self.source)
            source_midterm = interim_components.ensure_kollokviums(self.source)[0]
            with journal_unlock():
                ComponentScore.objects.create(
                    organization=self.org,
                    component=source_midterm,
                    enrollment=self.w2,
                    score=20,
                    exam_source={"attempt_id": 1, "exam_id": self.exam.pk},
                )
                ComponentScore.objects.create(
                    organization=self.org,
                    component=source_midterm,
                    enrollment=self.w1,
                    score=15,
                    exam_source={"attempt_id": 2, "exam_id": self.exam.pk},
                )
                ComponentScore.objects.create(
                    organization=self.org, component=self._midterm(), enrollment=self.enrollment, score=12
                )
        self.plan = {
            "format": duplicates.FORMAT,
            "auto_catalogue": False,
            "groups": [
                {
                    "name": "test",
                    "keeper": str(self.subject.pk),
                    "sources": [str(self.twin.pk)],
                    "pairs": [{"source": str(self.source.pk), "target": str(self.offering.pk)}],
                }
            ],
        }
        patch = self._patch_plan()
        patch.start()
        self.addCleanup(patch.stop)

    # ── qurucular ─────────────────────────────────────────────────────────
    def _patch_plan(self):
        from unittest import mock

        return mock.patch.object(duplicates, "PLAN", self.plan)

    def _student(self, username, group):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user, organization=self.org, role=self.org.roles.get(name="student"), is_primary=True, is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=user,
            program=self.program,
            curriculum=self.curriculum,
            group=group,
            admission_year=2024,
        )
        return user

    def _lesson(self, offering, day, kind, topic=""):
        return Lesson.objects.create(
            organization=self.org, offering=offering, date=day, kind=kind, hours=2, start_time=T1, topic=topic
        )

    def _mark(self, lesson, enrollment, status, score=None):
        return LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score
        )

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "merge_duplicate_subjects_20261111",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            *extra,
            stdout=out,
        )
        counts, batch = {}, ""
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^twin_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            for item in line.split()[1:]:
                key, value = item.split("=")
                if key == "batch":
                    batch = value
                elif not line.startswith("twin_merge: pair="):
                    counts[key] = value
        return counts, batch

    def _target_cells(self):
        return {
            (lesson_date, kind, student): (status, score)
            for lesson_date, kind, student, status, score in LessonMark.objects.filter(
                lesson__offering=self.offering
            ).values_list("lesson__date", "lesson__kind", "enrollment__student_id", "status", "score")
        }

    def _receipt(self):
        return AuditLog.objects.get(resource_type=journal_merge.RESOURCE, changes__kind=journal_merge.KIND)

    # ── testlər ───────────────────────────────────────────────────────────
    def test_every_relation_is_classified(self):
        self.assertEqual(journal_merge.unclassified_relations(), set())

    def test_command_is_wired_into_prod_data_ops(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - merge_duplicate_subjects_20261111\n", text)
        self.assertIn("            merge_duplicate_subjects_20261111)\n", text)
        self.assertIn('[ "$COMMAND" = "merge_duplicate_subjects_20261111" ] ||', text)
        self.assertEqual(duplicates.PLAN["format"], duplicates.FORMAT)

    def test_dry_run_writes_nothing(self):
        counts, batch = self._call()
        self.assertEqual((counts["mode"], batch), ("dry_run", ""))
        self.assertEqual(counts["pairs_merged"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.source.pk).is_active)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 2)
            self.assertFalse(Subject.objects.get(pk=self.twin.pk).is_archived)
            self.assertFalse(AuditLog.objects.filter(resource_type=journal_merge.RESOURCE).exists())

    def test_journal_merge_loses_no_mark_and_keeps_both_conflict_values(self):
        with bypass_rls():
            before = self._target_cells()
            source_cells = list(
                LessonMark.objects.filter(lesson__offering=self.source).values_list(
                    "lesson__date", "lesson__kind", "enrollment__student_id", "status", "score"
                )
            )
        counts, _batch = self._call("--only", "journals", "--apply")
        self.assertEqual(counts["marks_copied"], "4")
        self.assertEqual(counts["marks_identical"], "1")
        self.assertEqual(counts["marks_conflict_target_kept"], "1")
        self.assertEqual((counts["lessons_deduplicated"], counts["lessons_created"]), ("2", "1"))
        with bypass_rls():
            after = self._target_cells()
            conflicts = self._receipt().changes["conflicts"]
            marks = {item["source_mark"]: item for item in conflicts if item["type"] == "mark"}
            for key, value in before.items():  # hədəfin öz xanaları dəyişməyib
                self.assertEqual(after[key], value)
            for day, kind, student, status, score in source_cells:  # mənbənin heç bir xanası itməyib
                if after[(day, kind, student)] != (status, score):
                    self.assertIn(str(self.conflict_mark.pk), marks)
                    self.assertEqual((day, student), (D1, self.student.pk))
            kept = marks[str(self.conflict_mark.pk)]
            self.assertEqual(
                (kept["source_value"], kept["target_value"], kept["kept"]),
                (["absent", None], ["present", None], "target"),
            )
            self.assertTrue(
                LessonMark.objects.filter(pk=self.conflict_mark.pk, status="absent").exists()
            )  # mənbədə qalır
            self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 3)
            self.assertEqual(Lesson.objects.get(pk=self.t_lecture.pk).topic, "Giriş")  # boş mövzu mənbədən
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="registrar.grade.mark", resource_id=str(self.offering.pk)
                ).exists()
            )
            # tələbə bir kart görür, mənbə jurnal passivdir (silinməyib)
            self.assertFalse(CourseOffering.objects.get(pk=self.source.pk).is_active)
            self.assertEqual(Lesson.objects.filter(offering=self.source).count(), 3)
            cards = services.get_student_semester_enrollments(record=self.record, period=self.period)
            self.assertEqual([row.offering_id for row in cards], [self.offering.pk])
            found = duplicates.duplicate_cards(self.org, self.period)
            self.assertEqual((len(found["twin"]), len(found["same"])), (0, 0))
            self.assertTrue(
                Enrollment.objects.filter(offering=self.offering, student=self.s2, status="enrolled").exists()
            )

    def test_scores_exam_result_wins_and_link_moves_then_bridge_writes(self):
        self._call("--only", "journals", "--apply")
        with bypass_rls():
            midterm = self._midterm()
            own = ComponentScore.objects.get(component=midterm, enrollment=self.enrollment)
            self.assertEqual((own.score, own.exam_source["attempt_id"]), (Decimal("15"), 2))  # imtahan nəticəsi qalır
            other = ComponentScore.objects.get(component=midterm, enrollment__student=self.s2)
            self.assertEqual((other.score, other.exam_source["attempt_id"]), (Decimal("20"), 1))
            scores = [item for item in self._receipt().changes["conflicts"] if item["type"] == "score"]
            self.assertEqual(
                [(item["source_value"], item["target_value"], item["kept"]) for item in scores],
                [("15.00", "12.00", "source_exam_result")],
            )
            self.assertEqual(list(self.exam.journal_offerings.values_list("pk", flat=True)), [self.offering.pk])
        attempt = self._finish(self.exam, self.options, correct=3)  # birləşmədən SONRA verilən midterm → hədəf jurnal
        self.assertEqual(self._score_row().score, Decimal("30"))
        self.assertEqual(self._score_row().exam_source["attempt_id"], attempt.pk)

    def test_full_run_merges_catalogue_recodes_and_undo_restores(self):
        with bypass_rls():
            chair = OrgUnit.objects.create(
                organization=self.org, name="Kaf", slug="dup-kaf", unit_type=OrgUnitType.CHAIR
            )
            syllabus = Syllabus.objects.create(
                organization=self.org, subject=self.twin, offering=self.source, period=self.period, chair_unit=chair
            )
        counts, batch = self._call("--apply")
        self.assertEqual(counts["syllabi_moved"], "1")
        with bypass_rls():
            syllabus.refresh_from_db()
            self.assertEqual((syllabus.offering_id, syllabus.subject_id), (self.offering.pk, self.subject.pk))
        self.assertRegex(batch, duplicates.BATCH_RE)
        self.assertEqual(counts["catalogue_groups_merged"], "1")
        self.assertEqual(counts["codes_recoded"], "1")
        self.assertEqual(counts["guard_twin_card_pairs"], "0")
        with bypass_rls():
            twin, keeper = Subject.objects.get(pk=self.twin.pk), Subject.objects.get(pk=self.subject.pk)
            self.assertTrue(twin.is_archived)
            self.assertEqual(keeper.code, "QKU-78")  # CS101 → növbəti boş QKU-N
            self.exam.refresh_from_db()
            self.assertEqual(self.exam.subject_id, keeper.pk)
            # K4: passiv dublikat jurnal arxiv kartda tarixçə kimi qalır
            self.assertEqual(CourseOffering.objects.get(pk=self.source.pk).subject_id, twin.pk)
        again, _ = self._call("--apply")  # idempotent
        self.assertEqual(again.get("pairs_merged", "0"), "0")
        self.assertEqual(again["already_merged"], "1")
        undone, _ = self._call("--undo", "--batch", batch, "--apply")
        self.assertEqual((undone["undo_pairs"], undone["undo_catalogue_groups"], undone["undo_codes"]), ("1", "1", "1"))
        with bypass_rls():
            self.assertFalse(Subject.objects.get(pk=self.twin.pk).is_archived)
            self.assertEqual(Subject.objects.get(pk=self.subject.pk).code, "CS101")
            syllabus.refresh_from_db()
            self.assertEqual((syllabus.offering_id, syllabus.subject_id), (self.source.pk, self.twin.pk))
            self.assertTrue(CourseOffering.objects.get(pk=self.source.pk).is_active)
            self.assertEqual(Enrollment.objects.filter(offering=self.source, status="enrolled").count(), 2)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 2)
            self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 2)
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, student=self.s2).exists())
            self.assertEqual(self._score_row().score, Decimal("12"))
            self.assertEqual(list(self.exam.journal_offerings.values_list("pk", flat=True)), [self.source.pk])
            self.exam.refresh_from_db()
            self.assertEqual(self.exam.subject_id, self.twin.pk)

    def test_different_instructors_or_names_block_the_pair(self):
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.source.pk).update(instructor=self.owner)
        counts, _ = self._call("--only", "journals", "--apply")
        self.assertEqual(counts["pair_instructors_differ"], "1")
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.source.pk).update(instructor=self.teacher)
            Subject.objects.filter(pk=self.twin.pk).update(name="Proqramlaşdırmanın əsasları")
        counts, _ = self._call("--only", "journals", "--apply")
        self.assertEqual(counts["pair_names_differ"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.source.pk).is_active)

    def test_report_guard_counts_duplicate_cards_and_codes(self):
        counts, _ = self._call("--only", "report")
        self.assertEqual((counts["guard_twin_card_pairs"], counts["guard_twin_card_students"]), ("1", "1"))
        self.assertEqual(counts["guard_same_name_card_groups"], "1")
        self.assertEqual(counts["guard_codes_nonstandard"], "1")

    def test_bridge_uses_duplicate_card_journal_when_subject_has_no_enrollment(self):
        """Sahib: «Fənnin jurnalında olmayan tələbə: 35 / 35» — imtahan əkiz kartla yaradılıb, bağlantı yoxdur."""
        with bypass_rls():
            other = OrgUnit.objects.create(
                organization=self.org, name="JBG2", slug="jb-g2", unit_type=OrgUnitType.GROUP
            )
            Enrollment.objects.filter(offering=self.source).update(status="dropped")
            CourseOffering.objects.filter(pk=self.source.pk).update(is_active=False)
            card = Subject.objects.create(organization=self.org, code="QKU-90", name="PROQRAMLAŞDIRMA")
            CourseOffering.objects.create(organization=self.org, subject=card, group=other, period=self.period)
            found = exam_bridge.resolve_enrollment(student=self.student, subject_id=card.pk, organization=self.org)
            self.assertEqual(found.pk, self.enrollment.pk)
            coverage = enrollment_coverage(self.org, card.pk, [self.student.pk], self.period)
            self.assertEqual((coverage["ok"], coverage["none"]), (1, []))
            # qrupun ailəsində imtahanın ÖZ fənninin jurnalı varsa əkiz qəbul edilmir (fail-closed)
            CourseOffering.objects.create(organization=self.org, subject=card, group=self.group, period=self.period)
            self.assertIsNone(
                exam_bridge.resolve_enrollment(student=self.student, subject_id=card.pk, organization=self.org)
            )

    def test_exam_taker_missing_from_journal_is_placed_as_subgroup_without_document(self):
        with bypass_rls():
            other = OrgUnit.objects.create(
                organization=self.org, name="JBG2", slug="jb-g2", unit_type=OrgUnitType.GROUP
            )
            s3 = self._student("dup_s3", other)
            exam, options = self._exam(title="Taker MT")
            exam.journal_offerings.add(self.offering)
            attempt = ExamAttempt.objects.create(user=s3, exam=exam, status="in_progress")
            for question, right, _wrong in options:
                ExamAnswer.objects.create(attempt=attempt, question=question).selected_options.add(right)
            with self.captureOnCommitCallbacks(execute=True):
                attempt.mark_finished(status="submitted")
            self.assertFalse(Enrollment.objects.filter(student=s3).exists())
        counts, _ = self._call("--only", "takers", "--apply")
        self.assertEqual(counts["takers_missing_from_journal"], "1")
        self.assertEqual(counts["taker_placed_as_subgroup"], "1")
        with bypass_rls():
            row = Enrollment.objects.get(student=s3, offering=self.offering)
            self.assertEqual((row.status, row.source_group_id), ("enrolled", other.pk))
            event = SubgroupPlacementEvent.objects.get(enrollment=row)
            self.assertIn("sənəd sonradan yüklənəcək", event.reason)
            score = ComponentScore.objects.get(component=self._midterm(), enrollment=row)
            self.assertEqual((score.score, score.exam_source["attempt_id"]), (Decimal("30"), attempt.pk))
        again, _ = self._call("--only", "takers", "--apply")
        self.assertEqual(again.get("takers_missing_from_journal", "0"), "0")
