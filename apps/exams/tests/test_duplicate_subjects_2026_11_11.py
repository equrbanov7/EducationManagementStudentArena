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
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.models import AuditLog
from apps.exams.models import ExamAnswer, ExamAttempt
from apps.exams.services import journal_missing_takers
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.organizations.models import Membership, OrgUnit
from apps.registrar import duplicate_journal_merge_2026_11_11 as journal_merge
from apps.registrar import duplicate_subjects_2026_11_11 as duplicates
from apps.registrar import exam_bridge
from apps.registrar import exam_taker_placement_2026_11_11 as taker_placement
from apps.registrar import interim_components, services
from apps.registrar.exam_journal_link import enrollment_coverage
from apps.registrar.models import (
    ComponentScore,
    CourseOffering,
    Enrollment,
    FinalGrade,
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
D4 = datetime.date(2026, 10, 15)
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
            # D4: hədəfdə balsız «iştirak» (açıq xana), mənbədə eyni tələbənin BALI var → bal hədəfə yazılmalıdır
            self.t_open = self._mark(self._lesson(self.offering, D4, LessonKind.SEMINAR), self.enrollment, "present")
            self._mark(self._lesson(self.source, D4, LessonKind.SEMINAR), self.w1, "present", 7)
            # dondurulmuş tələbə (yalnız mənbədə) + köhnə sistemin q/b kəsilməsi — hədəfə EYNİ statusla keçməlidir
            self.s4 = self._student("dup_s4", self.group)
            self.w4 = Enrollment.objects.create(
                organization=self.org, student=self.s4, offering=self.source, status="suspended", legacy_qb_fail=True
            )
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
        self.lines = out.getvalue().splitlines()
        for line in self.lines:
            self.assertRegex(line, r"^twin_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            for item in line.split()[1:]:
                key, value = item.split("=")
                if key == "batch":
                    batch = value
                elif not line.startswith(("twin_merge: pair=", "twin_merge: exam=")):
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

    def test_command_is_wired_into_prod_data_ops_and_plan_is_conservative(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - merge_duplicate_subjects_20261111\n", text)
        self.assertIn("            merge_duplicate_subjects_20261111)\n", text)
        self.assertIn('[ "$COMMAND" = "merge_duplicate_subjects_20261111" ] ||', text)
        self.assertIn("apply üçün açıq addım verin", text)  # boş batch + apply rədd olunur
        import json

        real = json.loads((pathlib.Path(duplicates.__file__).with_suffix(".json")).read_text(encoding="utf-8"))
        self.assertEqual(real["format"], duplicates.FORMAT)
        self.assertIs(real["auto_catalogue"], False)  # avtomatik kataloq birləşməsi yalnız açıq bayraqla

    def test_dry_run_writes_nothing_and_apply_needs_an_explicit_step(self):
        counts, batch = self._call()
        self.assertEqual((counts["mode"], batch), ("dry_run", ""))
        self.assertEqual(counts["pairs_merged"], "1")
        with self.assertRaisesMessage(CommandError, "duplicate_subjects_apply_needs_explicit_step"):
            self._call("--apply")
        with self.assertRaisesMessage(CommandError, "duplicate_subjects_apply_needs_explicit_step"):
            self._call("--only", "report", "--apply")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.source.pk).is_active)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 3)
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
        self.assertEqual(counts["marks_score_filled"], "1")
        self.assertEqual((counts["lessons_deduplicated"], counts["lessons_created"]), ("3", "1"))
        with bypass_rls():
            after = self._target_cells()
            receipt = self._receipt().changes
            marks = {item["source_mark"]: item for item in receipt["conflicts"] if item["type"] == "mark"}
            self.assertEqual(list(marks), [str(self.conflict_mark.pk)])  # balsız «iştirak» + bal münaqişə DEYİL
            for key, value in before.items():  # hədəfin öz xanaları dəyişməyib (açıq xanaya yalnız bal əlavə olunub)
                expected = ("present", Decimal("7")) if key[0] == D4 else value
                self.assertEqual(after[key], expected)
            for day, kind, student, status, score in source_cells:  # mənbənin heç bir xanası itməyib
                if after[(day, kind, student)] != (status, score):
                    self.assertEqual((day, student), (D1, self.student.pk))
            self.assertEqual(receipt["manifest"]["marks_score_filled"], [[str(self.t_open.pk), "7.00"]])
            kept = marks[str(self.conflict_mark.pk)]
            self.assertEqual(
                (kept["source_value"], kept["target_value"], kept["kept"]),
                (["absent", None], ["present", None], "target"),
            )
            self.assertTrue(LessonMark.objects.filter(pk=self.conflict_mark.pk, status="absent").exists())
            self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 4)
            self.assertEqual(Lesson.objects.get(pk=self.t_lecture.pk).topic, "Giriş")  # boş mövzu mənbədən
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="registrar.grade.mark", resource_id=str(self.offering.pk)
                ).exists()
            )
            # tələbə bir kart görür, mənbə jurnal passivdir (silinməyib)
            self.assertFalse(CourseOffering.objects.get(pk=self.source.pk).is_active)
            self.assertEqual(Lesson.objects.filter(offering=self.source).count(), 4)
            cards = services.get_student_semester_enrollments(record=self.record, period=self.period)
            self.assertEqual([row.offering_id for row in cards], [self.offering.pk])
            found = duplicates.duplicate_cards(self.org, self.period)
            self.assertEqual((len(found["twin"]), len(found["same"])), (0, 0))
            self.assertTrue(
                Enrollment.objects.filter(offering=self.offering, student=self.s2, status="enrolled").exists()
            )
            # dondurulmuş tələbə passiv jurnalda qalmır: hədəfdə EYNİ statusla, q/b kəsilməsi ilə
            moved = Enrollment.objects.get(offering=self.offering, student=self.s4)
            self.assertEqual((moved.status, moved.legacy_qb_fail), ("suspended", True))
            self.assertEqual(Enrollment.objects.get(pk=self.w4.pk).status, "dropped")

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

    def test_steps_run_separately_and_undo_is_all_or_nothing_in_reverse_order(self):
        with bypass_rls():
            chair = OrgUnit.objects.create(
                organization=self.org, name="Kaf", slug="dup-kaf", unit_type=OrgUnitType.CHAIR
            )
            syllabus = Syllabus.objects.create(
                organization=self.org, subject=self.twin, offering=self.source, period=self.period, chair_unit=chair
            )
        counts, journals = self._call("--only", "journals", "--apply")
        self.assertEqual(counts["syllabi_moved"], "1")
        counts, catalogue = self._call("--only", "catalogue", "--apply")
        self.assertEqual(counts["catalogue_groups_merged"], "1")
        counts, codes = self._call("--only", "codes", "--apply")
        self.assertEqual((counts["codes_recoded"], counts["guard_twin_card_pairs"]), ("1", "0"))
        self.assertEqual(len({journals, catalogue, codes}), 3)  # hər addım öz paketi
        with bypass_rls():
            syllabus.refresh_from_db()
            self.assertEqual((syllabus.offering_id, syllabus.subject_id), (self.offering.pk, self.subject.pk))
            twin, keeper = Subject.objects.get(pk=self.twin.pk), Subject.objects.get(pk=self.subject.pk)
            self.assertTrue(twin.is_archived)
            self.assertEqual(keeper.code, "QKU-78")  # CS101 → növbəti boş QKU-N
            self.exam.refresh_from_db()
            self.assertEqual(self.exam.subject_id, keeper.pk)
            # K4: passiv dublikat jurnal arxiv kartda tarixçə kimi qalır
            self.assertEqual(CourseOffering.objects.get(pk=self.source.pk).subject_id, twin.pk)
        again, _ = self._call("--only", "journals", "--apply")  # idempotent
        self.assertEqual((again.get("pairs_merged", "0"), again["already_merged"]), ("0", "1"))
        # Jurnal paketi kataloq paketindən ƏVVƏL geri qaytarıla bilməz — heç nə yazılmır, paket «geri qaytarılıb» olmur.
        with self.assertRaisesMessage(CommandError, "duplicate_subjects_undo_blocked_source_card_archived"):
            self._call("--undo", "--batch", journals, "--apply")
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.source.pk).is_active)
            self.assertFalse(AuditLog.objects.filter(changes__kind=f"{duplicates.KIND}_undo").exists())
        self.assertEqual(self._call("--undo", "--batch", codes, "--apply")[0]["undo_codes"], "1")
        self.assertEqual(self._call("--undo", "--batch", catalogue, "--apply")[0]["undo_catalogue_groups"], "1")
        undone, _ = self._call("--undo", "--batch", journals, "--apply")
        self.assertEqual((undone["undo_pairs"], undone["undo_exams_resynced"]), ("1", "1"))
        with self.assertRaisesMessage(CommandError, "duplicate_subjects_batch_already_undone"):
            self._call("--undo", "--batch", journals, "--apply")
        with bypass_rls():
            self.assertFalse(Subject.objects.get(pk=self.twin.pk).is_archived)
            self.assertEqual(Subject.objects.get(pk=self.subject.pk).code, "CS101")
            syllabus.refresh_from_db()
            self.assertEqual((syllabus.offering_id, syllabus.subject_id), (self.source.pk, self.twin.pk))
            self.assertTrue(CourseOffering.objects.get(pk=self.source.pk).is_active)
            self.assertEqual(Enrollment.objects.filter(offering=self.source, status="enrolled").count(), 2)
            self.assertEqual(Enrollment.objects.get(pk=self.w4.pk).status, "suspended")
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 3)
            self.assertIsNone(LessonMark.objects.get(pk=self.t_open.pk).score)  # yazılan bal geri götürülüb
            self.assertEqual(Lesson.objects.get(pk=self.t_lecture.pk).topic, "")  # doldurulan mövzu geri qayıdıb
            self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 3)
            self.assertFalse(Enrollment.objects.filter(offering=self.offering, student__in=[self.s2, self.s4]).exists())
            self.assertEqual(self._score_row().score, Decimal("12"))
            self.assertEqual(list(self.exam.journal_offerings.values_list("pk", flat=True)), [self.source.pk])
            self.exam.refresh_from_db()
            self.assertEqual(self.exam.subject_id, self.twin.pk)

    def test_undo_refuses_when_teacher_wrote_after_the_merge(self):
        _counts, batch = self._call("--only", "journals", "--apply")
        with bypass_rls():
            late = self._lesson(self.offering, datetime.date(2026, 11, 2), LessonKind.LECTURE)
            self._mark(late, self.enrollment, "present")
        with self.assertRaisesMessage(CommandError, "duplicate_subjects_undo_blocked_post_merge_data"):
            self._call("--undo", "--batch", batch, "--apply")
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.get(pk=self.source.pk).is_active)

    def test_blocked_pairs_instructor_name_and_finished_target(self):
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
            Subject.objects.filter(pk=self.twin.pk).update(name="Proqram laşdırma")
            FinalGrade.objects.create(organization=self.org, enrollment=self.enrollment, exam_score=Decimal("30"))
        counts, _ = self._call("--only", "journals", "--apply")  # bitmiş semestrin hədəf jurnalına toxunulmur
        self.assertEqual(counts["target_has_final_results"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.source.pk).is_active)
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.offering).count(), 3)

    def test_auto_pairs_touch_past_periods_only_for_empty_shells(self):
        """Cari dövr qutusu tam birləşir; keçmiş dövrdə YALNIZ boş qabıq passiv olur (2-ci dövrə, 2026-11-11)."""
        with bypass_rls():
            past = type(self.period).objects.create(
                organization=self.org,
                name="Keçmiş",
                period_type=self.period.period_type,
                academic_year="2025/2026",
                start_date=datetime.date(2025, 9, 1),
                end_date=datetime.date(2026, 1, 31),
            )
            shells = [
                CourseOffering.objects.create(organization=self.org, subject=subject, group=self.group, period=past)
                for subject in (self.subject, self.twin)
            ]
            other = OrgUnit.objects.create(
                organization=self.org, name="JBGP", slug="jb-gp", unit_type=OrgUnitType.GROUP
            )
            busy = []
            for subject in (self.subject, self.twin):  # keçmiş dövrdə HƏR İKİ tərəfi datalı qutu
                offering = CourseOffering.objects.create(
                    organization=self.org, subject=subject, group=other, period=past
                )
                Lesson.objects.create(
                    organization=self.org, offering=offering, date=datetime.date(2025, 10, 1), kind="lecture", hours=2
                )
                busy.append(offering)
            self.plan["groups"][0]["pairs"] = []
        counts, _ = self._call("--only", "journals")
        self.assertEqual(counts["pairs_merged"], "2")  # cari qutu + keçmiş boş qabıq
        self.assertEqual(sum(1 for line in self.lines if line.startswith("twin_merge: pair=")), 2)
        self._call("--only", "journals", "--apply")
        with bypass_rls():
            self.assertEqual(
                [CourseOffering.objects.get(pk=row.pk).is_active for row in shells], [True, False]
            )  # mənbə kartın qabığı passiv
            self.assertEqual(CourseOffering.objects.filter(pk__in=[row.pk for row in busy], is_active=True).count(), 2)

    def test_auto_catalogue_is_opt_in_and_never_merges_across_chairs(self):
        with bypass_rls():
            chairs = [
                OrgUnit.objects.create(organization=self.org, name=name, slug=name, unit_type=OrgUnitType.CHAIR)
                for name in ("kaf-a", "kaf-b")
            ]
            same = [
                Subject.objects.create(organization=self.org, code=code, name=name, chair_unit=chairs[0])
                for code, name in (("QKU-91", "Fizika"), ("QKU-92", "fizika"))
            ]
            split = [
                Subject.objects.create(organization=self.org, code=code, name="Etika", chair_unit=chair)
                for code, chair in (("QKU-93", chairs[0]), ("QKU-94", chairs[1]))
            ]
            self.plan["groups"] = []
        counts, _ = self._call("--only", "catalogue", "--apply")  # defolt: yalnız plandakı açıq qruplar
        self.assertNotIn("catalogue_groups_merged", counts)
        counts, _ = self._call("--only", "catalogue", "--auto-catalogue", "--apply")
        self.assertEqual(counts["catalogue_groups_merged"], "1")
        self.assertEqual(counts["same_name_review_chair_differs"], "1")
        self.assertEqual(counts["catalogue_blocked_offering"], "1")  # iki aktiv jurnallı cüt avtomatik birləşmir
        with bypass_rls():
            self.assertEqual(
                [Subject.objects.get(pk=row.pk).is_archived for row in same], [False, True]
            )  # ən kiçik nömrə qalır
            self.assertFalse(Subject.objects.filter(pk__in=[row.pk for row in split], is_archived=True).exists())
            self.assertFalse(Subject.objects.get(pk=self.twin.pk).is_archived)

    def test_report_guard_counts_duplicate_cards_and_codes(self):
        counts, _ = self._call("--only", "report")
        self.assertEqual((counts["guard_twin_card_pairs"], counts["guard_twin_card_students"]), ("1", "1"))
        self.assertEqual(counts["guard_same_name_card_groups"], "1")
        self.assertEqual(counts["guard_codes_nonstandard"], "1")

    def _unlinked_card(self, **fields):
        """Bağlantısız dublikat kart: tələbənin jurnalı ``self.subject``-dədir, kartın açılışı başqa qrupdadır."""
        other = OrgUnit.objects.create(organization=self.org, name="JBG2", slug="jb-g2", unit_type=OrgUnitType.GROUP)
        Enrollment.objects.filter(offering=self.source).update(status="dropped")
        CourseOffering.objects.filter(pk=self.source.pk).update(is_active=False)
        card = Subject.objects.create(organization=self.org, code="QKU-90", name="PROQRAMLAŞDIRMA", **fields)
        CourseOffering.objects.create(organization=self.org, subject=card, group=other, period=self.period)
        return card

    def test_bridge_uses_duplicate_card_journal_when_subject_has_no_enrollment(self):
        """Sahib: «Fənnin jurnalında olmayan tələbə: 35 / 35» — imtahan əkiz kartla yaradılıb, bağlantı yoxdur."""
        with bypass_rls():
            card = self._unlinked_card()
            found = exam_bridge.resolve_enrollment(student=self.student, subject_id=card.pk, organization=self.org)
            self.assertEqual(found.pk, self.enrollment.pk)
            coverage = enrollment_coverage(self.org, card.pk, [self.student.pk], self.period)
            self.assertEqual((coverage["ok"], coverage["none"]), (1, []))
            # buraxılış qapısı ehtiyatı İŞLƏTMİR: bağlantısız əkiz jurnalın qayıbı tələbəni imtahandan kəsməsin
            gate = exam_bridge.exam_eligibility(student=self.student, subject_id=card.pk, organization=self.org)
            self.assertEqual(gate, {"linked": False, "barred": False, "reason": ""})
            # qrupun ailəsində imtahanın ÖZ fənninin jurnalı varsa əkiz qəbul edilmir (fail-closed)
            CourseOffering.objects.create(organization=self.org, subject=card, group=self.group, period=self.period)
            self.assertIsNone(
                exam_bridge.resolve_enrollment(student=self.student, subject_id=card.pk, organization=self.org)
            )

    def test_bridge_fallback_needs_equal_credit_and_kind(self):
        with bypass_rls():
            card = self._unlinked_card(ects=self.subject.ects + 1)  # eyni ad, FƏRQLİ kredit — ayrı fənn ola bilər
            self.assertIsNone(
                exam_bridge.resolve_enrollment(student=self.student, subject_id=card.pk, organization=self.org)
            )
            self.assertEqual(enrollment_coverage(self.org, card.pk, [self.student.pk], self.period)["ok"], 0)

    def test_bridge_fallback_never_overwrites_a_manual_midterm_score(self):
        with bypass_rls():
            card = self._unlinked_card()
            exam, options = self._exam(title="Unlinked MT")
            exam.subject = card
            exam.save(update_fields=["subject"])
        self._finish(exam, options, correct=3)
        self.assertEqual(self._score_row().score, Decimal("12"))  # müəllimin əl ilə yazdığı bal qalır
        with bypass_rls(), journal_unlock():
            ComponentScore.objects.filter(pk=self._score_row().pk).delete()
            second, options = self._exam(title="Unlinked MT 2")
            second.subject = card
            second.save(update_fields=["subject"])
        attempt = self._finish(second, options, correct=3)  # boş xanaya isə yazılır
        self.assertEqual(self._score_row().exam_source["attempt_id"], attempt.pk)

    # ── imtahan verib jurnalda olmayanlar ─────────────────────────────────
    def _missing_taker(self):
        other = OrgUnit.objects.create(organization=self.org, name="JBG2", slug="jb-g2", unit_type=OrgUnitType.GROUP)
        student = self._student("dup_s3", other)
        exam, options = self._exam(title="Taker MT")
        exam.journal_offerings.add(self.offering)
        attempt = ExamAttempt.objects.create(user=student, exam=exam, status="in_progress")
        for question, right, _wrong in options:
            ExamAnswer.objects.create(attempt=attempt, question=question).selected_options.add(right)
        with self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")
        self.assertFalse(Enrollment.objects.filter(student=student).exists())
        return student, exam, attempt, other

    def test_exam_with_mass_missing_takers_is_skipped_unless_listed_in_the_plan(self):
        self.assertTrue(journal_missing_takers.mass_missing(6, 100))
        self.assertTrue(journal_missing_takers.mass_missing(3, 10))
        self.assertFalse(journal_missing_takers.mass_missing(2, 10))
        with bypass_rls():
            student, exam, _attempt, _other = self._missing_taker()
        counts, _ = self._call("--only", "takers", "--apply")  # 1 / 1 itkin = imtahanın hamısı → atlanır
        self.assertEqual(counts["takers_exams_skipped_mass_missing"], "1")
        self.assertIn(f"twin_merge: exam={exam.pk} checked=1 missing=1 skipped=mass_missing", self.lines)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student=student).exists())

    def test_listed_exam_taker_is_placed_without_document_and_untouched_placement_is_undone(self):
        with bypass_rls():
            student, exam, attempt, other = self._missing_taker()
        self.plan["takers_exams"] = [exam.pk]
        counts, batch = self._call("--only", "takers", "--apply")
        self.assertEqual((counts["takers_missing_from_journal"], counts["taker_placed_as_subgroup"]), ("1", "1"))
        self.assertIn(f"twin_merge: exam={exam.pk} checked=1 missing=1 placed=1 refused=0", self.lines)
        with bypass_rls():
            row = Enrollment.objects.get(student=student, offering=self.offering)
            self.assertEqual((row.status, row.source_group_id), ("enrolled", other.pk))
            event = SubgroupPlacementEvent.objects.get(enrollment=row)
            self.assertIn("sənəd sonradan yüklənəcək", event.reason)
            score = ComponentScore.objects.get(component=self._midterm(), enrollment=row)
            self.assertEqual((score.score, score.exam_source["attempt_id"]), (Decimal("30"), attempt.pk))
            receipt = AuditLog.objects.get(resource_type=taker_placement.RESOURCE, resource_id=batch)
            self.assertEqual(receipt.changes["placements"][0]["enrollment"], str(row.pk))
        again, _ = self._call("--only", "takers", "--apply")
        self.assertEqual(again.get("takers_missing_from_journal", "0"), "0")
        undone, _ = self._call("--undo", "--batch", batch, "--apply")
        self.assertEqual(undone["takers_undo_released"], "1")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=row.pk).status, "dropped")

    def test_db_guard_error_for_one_taker_is_counted_not_fatal(self):
        """2026-11-11 prod dry-run: DB qoruyucusu (aktiv üzvlük yoxdur) bütün qaçışı dayandırırdı."""
        from unittest import mock

        from django.db import IntegrityError

        with bypass_rls():
            student, exam, _attempt, _other = self._missing_taker()
        self.plan["takers_exams"] = [exam.pk]
        with (
            mock.patch("apps.registrar.subgroup_placement.place_in_subgroup", side_effect=IntegrityError("guard")),
            mock.patch(
                "apps.registrar.exam_taker_placement_2026_11_11.place_in_subgroup", side_effect=IntegrityError("guard")
            ),
        ):
            counts, _ = self._call("--only", "takers", "--apply")
        self.assertEqual(counts["taker_subgroup_blocked_integrity"], "1")
        self.assertIn(f"twin_merge: exam={exam.pk} checked=1 missing=1 placed=0 refused=1", self.lines)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student=student, offering=self.offering).exists())

    def test_touched_taker_placement_is_not_undone(self):
        with bypass_rls():
            student, exam, _attempt, _other = self._missing_taker()
        self.plan["takers_exams"] = [exam.pk]
        _counts, batch = self._call("--only", "takers", "--apply")
        with bypass_rls():
            row = Enrollment.objects.get(student=student, offering=self.offering)
            self._mark(self.t_lecture, row, "present")  # müəllim tələbə ilə işləyib
        undone, _ = self._call("--undo", "--batch", batch, "--apply")
        self.assertEqual(undone["takers_undo_blocked_touched"], "1")
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=row.pk).status, "enrolled")
        with self.assertRaisesMessage(CommandError, "duplicate_subjects_batch_unknown"):
            self._call("--undo", "--batch", "dupsubj-20261111-000000-ffff", "--apply")

    def test_retake_attempt_is_not_a_missing_taker(self):
        with bypass_rls():
            student, exam, _attempt, _other = self._missing_taker()
        self.plan["takers_exams"] = [exam.pk]
        with mock.patch.object(taker_placement, "is_retake_attempt", return_value=True):
            counts, _ = self._call("--only", "takers", "--apply")
        self.assertEqual(counts["takers_retake_attempt_skipped"], "1")
        self.assertNotIn("takers_missing_from_journal", counts)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student=student).exists())
