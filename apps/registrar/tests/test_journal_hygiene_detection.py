"""«Jurnal təmizliyi» — AŞKARLAMA (sahib 2026-10-10).

Kilidlənən qaydalar:

* (a) ayrılmış tələbə HƏR siqnalla tapılır (arxiv, xaric, akademik məzuniyyət, məzun, passiv qeyd, oxu müddəti
  bitib, qeyd yoxdur); oxuyan tələbə, keçmiş dövr, bağlı jurnal, ləğv olunmuş açılış, artıq dondurulmuş sətir
  siyahıya düşmür; qrupu dəyişmiş sətir etiketlənir; məlumatlı sətir «məlumat var» kimi işarələnir;
* (b) boş fənn: dövr bitib / jurnal bağlı / açılış ləğv / seçmə dəyişib; «güclü» = açılışda dərs yoxdur və
  qrupda heç kimin datası yoxdur, qalanı «yoxlanmalı»; MƏLUMATI OLAN sətir (bal, qayıb saatı, yekun bal,
  köçürmə sələfi) heç vaxt siyahıda olmur; alt qrup əlavəsi və ``dropped`` sətir də düşmür;
* süzgəclər allow-list-dir, yanlış id 500 vermir; saylar və səhifə sorğu sayı sətir sayından asılı deyil.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.registrar import journal_hygiene as hygiene
from apps.registrar import journal_hygiene_rows as rows_service
from apps.registrar.models import (
    AcademicStatus,
    CurriculumSubject,
    Enrollment,
    EnrollmentKind,
    FinalGrade,
    GroupElectiveChoice,
)
from core.rls import bypass_rls

from .journal_hygiene_fixture import HygieneBase


def domain_queries(ctx) -> list:
    """RLS konteksti (``set_config`` / ``current_setting``) xaric sorğular."""
    return [
        query["sql"][:120]
        for query in ctx.captured_queries
        if "set_config(" not in query["sql"] and "current_setting(" not in query["sql"]
    ]


def _by_user(queryset, field="jh_reason"):
    return {row.student.username: getattr(row, field) for row in queryset.select_related("student")}


class LeftStudentDetectionTest(HygieneBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            ended = cls.year_start - 5  # 4 illik proqram çoxdan bitib
            cls.students = {
                "jh_active": cls.make_student("jh_active"),
                "jh_expelled": cls.make_student("jh_expelled", status=AcademicStatus.EXPELLED),
                "jh_leave": cls.make_student("jh_leave", status=AcademicStatus.ACADEMIC_LEAVE),
                "jh_graduated": cls.make_student("jh_graduated", status=AcademicStatus.GRADUATED),
                "jh_inactive": cls.make_student("jh_inactive", is_active=False),
                "jh_archived": cls.make_student("jh_archived", archived=True),
                "jh_ended": cls.make_student("jh_ended", admission_year=ended),
                "jh_norecord": cls.make_student("jh_norecord", with_record=False),
            }
            cls.rows = {name: cls.enroll(user) for name, user in cls.students.items()}

    def _left(self, filters=None):
        with bypass_rls():
            return hygiene.candidates(self.org, hygiene.LEFT, filters)

    def test_every_signal_is_detected_and_studying_student_is_not(self):
        with bypass_rls():
            found = _by_user(self._left())
            strong = _by_user(self._left(), "jh_strong")
        self.assertEqual(
            found,
            {
                "jh_expelled": hygiene.REASON_EXPELLED,
                "jh_leave": hygiene.REASON_ACADEMIC_LEAVE,
                "jh_graduated": hygiene.REASON_GRADUATED,
                "jh_inactive": hygiene.REASON_INACTIVE,
                "jh_archived": hygiene.REASON_ARCHIVED,
                "jh_ended": hygiene.REASON_PERIOD_ENDED,
                "jh_norecord": hygiene.REASON_NO_RECORD,
            },
        )
        # Rəsmi/qəti siqnallar güclüdür; müddət və qeydsizlik yalnız yoxlama siqnalıdır.
        self.assertFalse(strong["jh_ended"])
        self.assertFalse(strong["jh_norecord"])
        self.assertTrue(all(strong[name] for name in ("jh_expelled", "jh_archived", "jh_inactive")))
        with bypass_rls():
            totals = hygiene.counts(self._left(), hygiene.LEFT)
        self.assertEqual(totals["total"], 7)
        self.assertEqual(totals["strong"], 5)
        self.assertEqual(totals[hygiene.REASON_EXPELLED], 1)
        self.assertEqual(totals["empty"], 7)

    def test_archived_profile_wins_over_an_enrolled_record(self):
        with bypass_rls():
            self.assertEqual(_by_user(self._left())["jh_archived"], hygiene.REASON_ARCHIVED)

    def test_scope_is_open_unpublished_active_enrolled_rows(self):
        expelled = self.students["jh_expelled"]
        with bypass_rls():
            past = self.enroll(expelled, self._offering(self.subject, self.past))
            future = self.enroll(expelled, self._offering(self.subject, self.future))
            closed_offering = self._offering(self.subject_b, self.current)
            closed = self.enroll(expelled, closed_offering)
            self.close_journal(closed_offering)
            cancelled = self.enroll(expelled, self._offering(self.subject_c, self.current, is_active=False))
            suspended = self.enroll(
                expelled, self._offering(self.subject_c, self.future), status=Enrollment.Status.SUSPENDED
            )
            ids = set(self._left().filter(student=expelled).values_list("pk", flat=True))
        self.assertIn(future.pk, ids)  # gələcək semestrin açıq jurnalı da təmizlənir
        self.assertIn(self.rows["jh_expelled"].pk, ids)
        for row in (past, closed, cancelled, suspended):
            self.assertNotIn(row.pk, ids)

    def test_group_change_tag_and_evidence_flag(self):
        with bypass_rls():
            moved = self.make_student("jh_moved", status=AcademicStatus.EXPELLED, group=self.group2)
            moved_row = self.enroll(moved)
            self.mark(self.rows["jh_expelled"])
            flags = {
                row.pk: (row.jh_group_changed, row.jh_has_evidence)
                for row in self._left().filter(pk__in=[moved_row.pk, self.rows["jh_expelled"].pk])
            }
            totals = hygiene.counts(self._left(), hygiene.LEFT)
        self.assertEqual(flags[moved_row.pk], (True, False))
        self.assertEqual(flags[self.rows["jh_expelled"].pk], (False, True))
        self.assertEqual(totals[hygiene.TAG_GROUP_CHANGED], 1)
        self.assertEqual(totals["empty"], totals["total"] - 1)

    def test_filters_are_allow_listed_and_never_fail(self):
        with bypass_rls():
            self.assertEqual(self._left({"category": hygiene.REASON_EXPELLED}).count(), 1)
            self.assertEqual(self._left({"category": hygiene.STRENGTH_REVIEW}).count(), 2)
            self.assertEqual(self._left({"category": "unknown-code"}).count(), 7)
            self.assertEqual(self._left({"period": "not-a-uuid", "group": "x", "faculty": "y"}).count(), 7)
            self.assertEqual(self._left({"period": str(self.past.pk)}).count(), 0)
            self.assertEqual(self._left({"faculty": str(self.faculty.pk)}).count(), 7)
            self.assertEqual(self._left({"group": str(self.group2.pk)}).count(), 0)
            self.assertEqual(self._left({"q": "jh_leave"}).count(), 1)

    def test_rows_page_shape(self):
        with bypass_rls():
            queryset = self._left({"category": hygiene.REASON_EXPELLED})
            page = rows_service.page(queryset, hygiene.LEFT, number=1, size=50, total=1)
        row = page["results"][0]
        self.assertEqual(row["id"], str(self.rows["jh_expelled"].pk))
        self.assertEqual(row["reason"], hygiene.REASON_EXPELLED)
        self.assertEqual(row["reason_label"], hygiene.label(hygiene.REASON_EXPELLED))
        self.assertEqual(row["group"], "JH-101")
        self.assertIn("JH-1", row["subject"])
        self.assertTrue(row["strong"])
        self.assertFalse(row["has_evidence"])
        self.assertEqual((page["page"], page["num_pages"], page["total"]), (1, 1, 1))

    def test_query_count_does_not_grow_with_rows(self):
        def run():
            with CaptureQueriesContext(connection) as ctx, bypass_rls():
                queryset = hygiene.candidates(self.org, hygiene.LEFT)
                totals = hygiene.counts(queryset, hygiene.LEFT)
                rows_service.page(queryset, hygiene.LEFT, number=1, size=50, total=totals["total"])
            return domain_queries(ctx), totals["total"]

        small, total_small = run()
        with bypass_rls():
            for index in range(6):
                self.enroll(self.make_student(f"jh_more{index}", status=AcademicStatus.EXPELLED))
        large, total_large = run()
        self.assertEqual(total_large, total_small + 6)
        self.assertEqual(len(small), len(large))
        self.assertEqual(len(large), 2, large)  # bir aqreqat + bir səhifə sorğusu


class EmptySubjectDetectionTest(HygieneBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.alice = cls.make_student("jh_alice")
            cls.bob = cls.make_student("jh_bob")
            # Keçmiş dövr, tədris planında olmayan fənn, dərs yoxdur, heç kimdə data yoxdur → GÜCLÜ.
            cls.ghost = cls._offering(cls.subject_c, cls.past)
            cls.ghost_rows = [cls.enroll(cls.alice, cls.ghost), cls.enroll(cls.bob, cls.ghost)]
            # Keçmiş dövr, keçirilmiş dərslər: Alice-in balı var, Bob boşdur → yalnız Bob, «yoxlanmalı».
            cls.taught = cls._offering(cls.subject, cls.past)
            cls.alice_taught = cls.enroll(cls.alice, cls.taught)
            cls.bob_taught = cls.enroll(cls.bob, cls.taught)
            cls.mark(cls.alice_taught)

    def _empty(self, filters=None):
        with bypass_rls():
            return hygiene.candidates(self.org, hygiene.EMPTY, filters)

    def _ids(self, filters=None):
        with bypass_rls():
            return set(self._empty(filters).values_list("pk", flat=True))

    def test_strong_and_review_ranking(self):
        with bypass_rls():
            strength = {row.pk: row.jh_strong for row in self._empty()}
            first = self._empty().first()
        self.assertEqual(strength, {**{row.pk: True for row in self.ghost_rows}, self.bob_taught.pk: False})
        self.assertTrue(first.jh_strong)  # güclü siqnal əvvəl gəlir
        self.assertNotIn(self.alice_taught.pk, strength)  # məlumatlı sətir heç vaxt siyahıda deyil

    def test_source_tags(self):
        with bypass_rls():
            tags = {
                row["id"]: {tag["code"] for tag in row["tags"]}
                for row in rows_service.rows_for(self._empty(), "empty_subject")
            }
        self.assertEqual(tags[str(self.ghost_rows[0].pk)], {hygiene.SOURCE_NOT_IN_CURRICULUM})
        self.assertEqual(tags[str(self.bob_taught.pk)], {hygiene.SOURCE_UNEXPLAINED})

    def test_rows_with_any_data_are_never_listed(self):
        with bypass_rls():
            absent = self.enroll(self.make_student("jh_absent"), self.ghost, absence_hours=4)
            graded = self.enroll(self.make_student("jh_graded"), self.ghost)
            FinalGrade.objects.create(organization=self.org, enrollment=graded, exam_score=30)
            blank_final = self.enroll(self.make_student("jh_blankfinal"), self.ghost)
            FinalGrade.objects.create(organization=self.org, enrollment=blank_final)  # yalnız yaradılıb — sübut deyil
            guest = self.enroll(self.make_student("jh_guest", group=self.group2), self.ghost, source_group=self.group2)
            dropped = self.enroll(self.make_student("jh_dropped"), self.ghost, status=Enrollment.Status.DROPPED)
            ids = self._ids()
        self.assertIn(blank_final.pk, ids)
        for row in (absent, graded, guest, dropped):
            self.assertNotIn(row.pk, ids)

    def test_transfer_successor_is_not_a_phantom(self):
        with bypass_rls():
            student = self.make_student("jh_transfer")
            successor = self.enroll(student, self.ghost)
            source = self.enroll(student, self._offering(self.subject_c, self.past, group=self.group2))
            Enrollment.objects.filter(pk=source.pk).update(status=Enrollment.Status.DROPPED, superseded_by=successor)
            self.assertNotIn(successor.pk, self._ids())

    def test_running_semester_is_not_listed_but_cancelled_offering_is(self):
        with bypass_rls():
            running = self.enroll(self.alice)  # cari, açıq, ləğv olunmamış — hələ boşdur, normaldır
            cancelled_offering = self._offering(self.subject_b, self.current, is_active=False)
            cancelled = self.enroll(self.alice, cancelled_offering)
            closed_offering = self._offering(self.subject_c, self.current)
            closed = self.enroll(self.alice, closed_offering)
            self.close_journal(closed_offering)
            rows = {row.pk: row for row in self._empty()}
        self.assertNotIn(running.pk, rows)
        self.assertTrue(rows[cancelled.pk].jh_cancelled)
        self.assertTrue(rows[cancelled.pk].jh_strong)
        self.assertIn(closed.pk, rows)

    def test_replaced_elective_is_tagged(self):
        with bypass_rls():
            CurriculumSubject.objects.create(
                organization=self.org,
                curriculum=self.curriculum,
                subject=self.subject_c,
                semester_number=1,
                is_elective=True,
                elective_group="SB1",
            )
            GroupElectiveChoice.objects.create(
                organization=self.org,
                group=self.group,
                period=self.current,
                elective_group="SB1",
                chosen_subject=self.subject_b,
            )
            old = self.enroll(self.alice, self._offering(self.subject_c, self.current), kind=EnrollmentKind.ELECTIVE)
            rows = {row.pk: row for row in self._empty({"category": hygiene.SOURCE_REPLACED})}
            totals = hygiene.counts(self._empty(), hygiene.EMPTY)
        self.assertEqual(set(rows), {old.pk})
        self.assertEqual(totals[hygiene.SOURCE_REPLACED], 1)
        self.assertEqual(totals["total"], 4)
        self.assertEqual(totals["strong"], 3)

    def test_counts_match_category_totals(self):
        with bypass_rls():
            chips = hygiene.counts(self._empty(), hygiene.EMPTY)
        self.assertEqual(chips["total"], 3)
        self.assertEqual(rows_service.page_total(chips, hygiene.STRENGTH_REVIEW), 1)
        self.assertEqual(rows_service.page_total(chips, hygiene.STRENGTH_STRONG), 2)
        self.assertEqual(rows_service.page_total(chips, hygiene.SOURCE_NOT_IN_CURRICULUM), 2)
        self.assertEqual(rows_service.page_total(chips, ""), 3)
        self.assertEqual(len(self._ids({"category": hygiene.SOURCE_UNEXPLAINED})), 1)
