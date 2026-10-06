"""Jurnal yazısının (``gradebook.save_marks``) sorğu/sətir büdcəsi — tutum 2026-10-06.

Əvvəl hər jurnal yazısı (müəllim BİR dərs günündə bir neçə xananı dəyişir)
açılışın BÜTÜN dərslərini və BÜTÜN işarələrini yükləyirdi, sonra xananı
xana-xana yazırdı (mövcud xanaya 2 sorğu: kimlik SELECT + UPDATE), axırda
hər toxunulmuş qeydiyyat üçün qayıb saatını ayrıca hesablayırdı (2 sorğu).
Bu test iki şeyi qıfıllayır:

* **Sorğu SAYI** kurs ölçüsündən (10 ↔ 40 dərs) və redaktə olunan xana
  sayından (5 ↔ 25) asılı deyil — sabit büdcə;
* **Yüklənən sətirlər** (Lesson/LessonMark/Enrollment instansiyaları) kurs
  ölçüsündən asılı deyil — yalnız redaktə olunan xanalara mütənasibdir.

Qaydaların özü (dərs günü, pəncərə, rəsmi düzəliş kilidi, audit, bildiriş,
qayıb həddi) ``test_gradebook`` / ``test_journal_rules`` / bu faylın sonundakı
davranış testlərində yoxlanır.
"""

from __future__ import annotations

import datetime
from collections import Counter

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models.signals import post_init
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services
from apps.registrar.models import (
    AttendanceStatus,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

STUDENTS = 25
#: Sabit büdcə: kilid (sxem + FOR UPDATE), 3 hədəfli oxu (dərs/qeydiyyat/xana),
#: düzəliş dəsti, toplu INSERT/UPDATE, toplu qayıb aqreqatı + qeydiyyat UPDATE-i,
#: hədd (lazım olanda), audit (savepoint + INSERT). Əvvəl 25 xanalıq yazı ~100+ idi.
MAX_QUERIES = 20

_TRACKED = (Lesson, LessonMark, Enrollment)


class _RowCounter:
    """``post_init`` siqnalı ilə yaradılan (DB-dən yüklənən + yeni) model instansiyalarını sayır."""

    def __init__(self):
        self.counts: Counter = Counter()

    def _receiver(self, sender, **kwargs):
        if sender in _TRACKED:
            self.counts[sender.__name__] += 1

    def __enter__(self):
        post_init.connect(self._receiver, weak=False)
        return self

    def __exit__(self, *exc):
        post_init.disconnect(self._receiver)
        return False


class SaveMarksQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.owner = User.objects.create_user("smq_owner", "smq_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SMQ Univ",
                slug="smq-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            specialty = OrgUnit.objects.create(
                organization=cls.org, name="CS", slug="smq-cs", unit_type=OrgUnitType.SPECIALTY
            )
            group = OrgUnit.objects.create(
                organization=cls.org, name="SMQ-101", slug="smq-101", unit_type=OrgUnitType.GROUP, parent=specialty
            )
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="SMQ semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=120),
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
            )
            program = Program.objects.create(
                organization=cls.org, code="SMQ", name="SMQ proqram", absence_limit_percent=25
            )
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
            small_subject = Subject.objects.create(organization=cls.org, code="SMQ10", name="Kiçik fənn")
            large_subject = Subject.objects.create(organization=cls.org, code="SMQ40", name="Böyük fənn")
            for subject in (small_subject, large_subject):
                CurriculumSubject.objects.create(
                    organization=cls.org, curriculum=curriculum, subject=subject, semester_number=1
                )
            cls.teacher = User.objects.create_user("smq_teacher", "smq_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            student_role = cls.org.roles.get(name="student")
            for idx in range(STUDENTS):
                student = User.objects.create_user(f"smq_s{idx:02d}", f"smq_s{idx:02d}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=student, organization=cls.org, role=student_role, is_primary=True, is_active=True
                )
                record = StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=student,
                    program=program,
                    curriculum=curriculum,
                    group=group,
                    admission_year=2026,
                )
                services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
            # Proses-səviyyəli keşlər (audit sxem introspeksiyası) ölçüyə düşməsin — isti-tut.
            AuditLog.objects.exists()
            cls.small = cls._prepare_offering(small_subject, history_lessons=10)
            cls.large = cls._prepare_offering(large_subject, history_lessons=40)

    @classmethod
    def _prepare_offering(cls, subject, *, history_lessons):
        """Keçmiş ``history_lessons`` dərs (hər birində 25 xana, bir qismi q/b) + bu günün seminarı."""
        today = timezone.localdate()
        offering = subject.offerings.get()
        offering.instructor = cls.teacher
        offering.lesson_hours = 2 * (history_lessons + 1)
        offering.save(update_fields=["instructor", "lesson_hours"])
        enrollments = list(offering.enrollments.order_by("student__username"))
        lessons = Lesson.objects.bulk_create(
            [
                Lesson(
                    organization=cls.org,
                    offering=offering,
                    date=today - datetime.timedelta(days=history_lessons - idx),
                    kind=LessonKind.SEMINAR if idx % 2 else LessonKind.LECTURE,
                    hours=2,
                )
                for idx in range(history_lessons)
            ]
        )
        LessonMark.objects.bulk_create(
            [
                LessonMark(
                    organization=cls.org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status=AttendanceStatus.ABSENT if (l_idx + e_idx) % 9 == 0 else AttendanceStatus.PRESENT,
                    score=7 if lesson.kind == LessonKind.SEMINAR and (l_idx + e_idx) % 9 else None,
                )
                for l_idx, lesson in enumerate(lessons)
                for e_idx, enrollment in enumerate(enrollments)
            ]
        )
        for enrollment in enrollments:
            gradebook.recompute_absence_hours(enrollment=enrollment)
        gradebook.ensure_assessment_scheme(offering=offering)  # ilk yazının sxem INSERT-i ölçüyə düşməsin
        today_lesson = Lesson.objects.create(
            organization=cls.org, offering=offering, date=today, kind=LessonKind.SEMINAR, hours=2
        )
        return {"offering": offering, "enrollments": enrollments, "today": today_lesson}

    # ── köməkçilər ─────────────────────────────────────────────────────────────
    @staticmethod
    def _entries(lesson, enrollments, *, absent_every=5, score="8"):
        entries = []
        for idx, enrollment in enumerate(enrollments):
            absent = idx % absent_every == 0
            entries.append(
                {
                    "lesson_id": str(lesson.id),
                    "enrollment_id": str(enrollment.id),
                    "status": AttendanceStatus.ABSENT if absent else AttendanceStatus.PRESENT,
                    "score": "" if absent else score,
                }
            )
        return entries

    def _measure(self, offering, entries):
        with bypass_rls(), _RowCounter() as rows, CaptureQueriesContext(connection) as ctx:
            result = gradebook.save_marks(offering=offering, entries=entries, by_user=self.teacher, report=True)
        return len(ctx.captured_queries), dict(rows.counts), result

    # ── büdcə ───────────────────────────────────────────────────────────────────
    def test_first_write_of_the_day_is_constant_in_course_size(self):
        """Bu günün dərsinə 25 yeni xana: 10 və 40 dərslik kursda EYNİ sorğu/sətir sayı."""
        small_q, small_rows, small_res = self._measure(
            self.small["offering"], self._entries(self.small["today"], self.small["enrollments"])
        )
        large_q, large_rows, large_res = self._measure(
            self.large["offering"], self._entries(self.large["today"], self.large["enrollments"])
        )
        print(
            f"\n[save_marks budget] first write 25 cells: 10 lessons={small_q} q {small_rows}; "
            f"40 lessons={large_q} q {large_rows}"
        )
        self.assertEqual(small_res, {"written": STUDENTS, "rejected": 0})
        self.assertEqual(large_res, {"written": STUDENTS, "rejected": 0})
        self.assertEqual(small_q, large_q, "sorğu sayı kurs ölçüsü ilə böyüyür")
        self.assertEqual(small_rows, large_rows, "yüklənən sətirlər kurs ölçüsü ilə böyüyür")
        self.assertLessEqual(large_q, MAX_QUERIES)

    def test_regrid_edit_is_constant_in_course_size_and_cell_count(self):
        """Grid bütün yazıla bilən xanaları geri göndərir; 5 xana dəyişir — sabit büdcə."""
        for case in (self.small, self.large):
            with bypass_rls():
                gradebook.save_marks(
                    offering=case["offering"],
                    entries=self._entries(case["today"], case["enrollments"]),
                    by_user=self.teacher,
                )
        counts = {}
        for name, case in (("small", self.small), ("large", self.large)):
            # Eyni xanalar, 5-i fərqli: i/e → q/b (qayıb sayğacı + bildiriş yolu).
            entries = self._entries(case["today"], case["enrollments"], absent_every=4)
            counts[name] = self._measure(case["offering"], entries)
        print(
            f"\n[save_marks budget] re-post 25 cells (edit window): 10 lessons={counts['small'][0]} q "
            f"{counts['small'][1]}; 40 lessons={counts['large'][0]} q {counts['large'][1]}"
        )
        self.assertEqual(counts["small"][0], counts["large"][0])
        self.assertEqual(counts["small"][1], counts["large"][1])
        self.assertLessEqual(counts["large"][0], MAX_QUERIES)

    def test_query_count_does_not_grow_with_edited_cells(self):
        """5 xana ↔ 25 xana — sorğu sayı eyni (toplu INSERT/UPDATE, toplu aqreqat)."""
        few_q, _rows, few_res = self._measure(
            self.small["offering"], self._entries(self.small["today"], self.small["enrollments"][:5])
        )
        many_q, _rows, many_res = self._measure(
            self.large["offering"], self._entries(self.large["today"], self.large["enrollments"])
        )
        print(f"\n[save_marks budget] 5 cells={few_q} q; 25 cells={many_q} q")
        self.assertEqual(few_res["written"], 5)
        self.assertEqual(many_res["written"], STUDENTS)
        self.assertEqual(few_q, many_q)

    def test_no_query_scans_the_whole_offering(self):
        """Heç bir oxu açılışın bütün dərs/xanalarını (``lesson__offering`` JOIN-i) süzmür."""
        entries = self._entries(self.large["today"], self.large["enrollments"])
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            gradebook.save_marks(offering=self.large["offering"], entries=entries, by_user=self.teacher)
        mark_reads = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].lstrip().upper().startswith("SELECT") and 'FROM "registrar_lessonmark"' in q["sql"]
        ]
        for sql in mark_reads:
            self.assertIn(" IN (", sql, f"xana oxusu hədəfli deyil: {sql[:200]}")
        lesson_reads = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].lstrip().upper().startswith("SELECT") and 'FROM "registrar_lesson"' in q["sql"]
        ]
        for sql in lesson_reads:
            self.assertIn(" IN (", sql, f"dərs oxusu hədəfli deyil: {sql[:200]}")

    # ── davranış (toplu yol qaydaları saxlayır) ──────────────────────────────────
    def test_bulk_path_keeps_audit_and_absence_counter(self):
        case = self.small
        enrollment = case["enrollments"][3]
        before = Enrollment.objects.get(pk=enrollment.pk).absence_hours
        entries = [
            {
                "lesson_id": str(case["today"].id),
                "enrollment_id": str(enrollment.id),
                "status": AttendanceStatus.ABSENT,
                "score": "",
            }
        ]
        audit_before = AuditLog.objects.filter(resource_type="registrar.grade.mark").count()
        with bypass_rls():
            written = gradebook.save_marks(offering=case["offering"], entries=entries, by_user=self.teacher)
        self.assertEqual(written, 1)
        self.assertEqual(Enrollment.objects.get(pk=enrollment.pk).absence_hours, before + 2)
        self.assertEqual(AuditLog.objects.filter(resource_type="registrar.grade.mark").count(), audit_before + 1)
        mark = LessonMark.objects.get(lesson=case["today"], enrollment=enrollment)
        self.assertEqual(mark.entered_by_id, self.teacher.id)

    def test_unchanged_repost_writes_no_rows_and_no_audit(self):
        case = self.small
        entries = self._entries(case["today"], case["enrollments"])
        with bypass_rls():
            gradebook.save_marks(offering=case["offering"], entries=entries, by_user=self.teacher)
        audit_before = AuditLog.objects.filter(resource_type="registrar.grade.mark").count()
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            written = gradebook.save_marks(offering=case["offering"], entries=entries, by_user=self.teacher)
        self.assertEqual(written, STUDENTS)  # «N xana yadda saxlanıldı» semantikası dəyişmir
        writes = [q["sql"] for q in ctx.captured_queries if q["sql"].lstrip().upper().startswith("UPDATE")]
        mark_writes = [sql for sql in writes if '"registrar_lessonmark"' in sql]
        self.assertEqual(len(mark_writes), 0, "dəyişməyən xanalar yenidən yazılır")
        self.assertEqual(AuditLog.objects.filter(resource_type="registrar.grade.mark").count(), audit_before)

    def test_invalid_and_foreign_ids_are_ignored(self):
        case = self.small
        foreign_lesson = self.large["today"]
        entries = [
            {"lesson_id": "not-a-uuid", "enrollment_id": str(case["enrollments"][0].id), "status": "present"},
            {"lesson_id": str(case["today"].id), "enrollment_id": "", "status": "present"},
            {"lesson_id": None, "enrollment_id": None, "status": "present"},
            {"lesson_id": str(foreign_lesson.id), "enrollment_id": str(case["enrollments"][0].id), "status": "present"},
            {
                "lesson_id": str(case["today"].id),
                "enrollment_id": str(self.large["enrollments"][0].id),
                "status": "present",
            },
            {"lesson_id": case["today"].id, "enrollment_id": case["enrollments"][1].id, "status": "present"},
        ]
        with bypass_rls():
            written = gradebook.save_marks(offering=case["offering"], entries=entries, by_user=self.teacher)
        self.assertEqual(written, 1)
        self.assertFalse(LessonMark.objects.filter(lesson=foreign_lesson).exists())
