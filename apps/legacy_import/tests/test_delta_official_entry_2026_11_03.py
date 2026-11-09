"""SYS-1 (2026-11-03): tarixi giriş balı köhnə sistemin RƏSMİ bal vərəqinə (``balvereqi_logs``) bərabərləşdirilir.

Yoxlanılır: vərəq HTML-inin oxunuşu; hədəf qaydası (Yekun − sayılan imtahan, yoxsa çap olunmuş Giriş); vərəq
cədvəlinin jurnal ailəsinə bağlanması (imtahanla semestr seçimi, qrup dəyişəndə tələbə ilə tutuşdurma, ambiqü);
faza: dry-run heç nə yazmır, yalnız arxiv xanası dəyişir, keçid/kəsr sayılır, audit sətri yazılır, müəllimin
yazdığı xanaya toxunulmur, ikinci qaçış 0 yazı, paket adi fazalarla RƏDD olunur.
"""

import datetime as dt
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.audit.models import AuditLog
from apps.legacy_import.services.delta.apply import execute
from apps.legacy_import.services.delta.official_entry import OfficialEntryPhaseMismatch
from apps.legacy_import.services.delta.official_entry_extract import JournalIndex
from apps.legacy_import.services.delta.official_entry_sheets import SheetRow, SheetTable, parse_export, target_entry
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    AssessmentComponent,
    ComponentScore,
    CourseOffering,
    Enrollment,
    FinalGrade,
    ResitRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()
D = Decimal


def _sheet_row(sid, entry, exam, total, resit="", attendance="9.46 bal"):
    cell = '<td style="vnd.ms-excel.numberformat:0.0;">{}</td>'
    return (
        f'<tr class="user_{sid}"><td>1</td><td>Ad Soyad</td><td>{attendance}</td><td>8</td>'
        + cell.format("29 &mdash; 0")
        + f'<td class="total_point_1" id="t_{sid}">{entry}</td>'
        + cell.format(exam)
        + cell.format("0 / 0")
        + f'<td class="a{sid}">{total}</td>'
        + cell.format(resit)
        + "<td></td><td></td></tr>"
    )


def _export(rows, *, group=669, subject="Hava və suyun keyfiyyəti ,&amp;ccedil;irklənməsi", teacher="&amp;Uuml;lkər Q"):
    body = (
        f'<table data-id="{group}" id="export_table_to_excel_{group}" data-name="234 EKO ing"><thead><tr><td>'
        f"Müəllim:  {teacher} <br>Fənn:       {subject}<br>Qrup: 234 EKO ing<br></td></tr></thead><tbody>"
        + "".join(rows)
        + "<tr><td>Seçilmiş dərs saatı: 75</td></tr></tbody></table>"
    )
    # ``balvereqi_logs.data`` HTML-i bir dəfə entity-qaçırılmış saxlayır.
    return body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class SheetParsingTests(SimpleTestCase):
    def test_parse_export_reads_group_subject_and_rows(self):
        tables = parse_export(
            _export([_sheet_row(7131, 34, 17, 51), _sheet_row(7129, 47, 25, 71, attendance="2 bal  (Kəsr)")])
        )
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual((table.group_id, table.hours), (669, 75))
        self.assertEqual(table.subject, "Hava və suyun keyfiyyəti ,çirklənməsi")
        self.assertEqual(table.teacher, "Ülkər Q")
        first, second = table.rows
        self.assertEqual(
            (first.student_id, first.entry, first.exam, first.total, first.resit), (7131, D(34), D(17), D(51), None)
        )
        self.assertFalse(first.attendance_fail)
        self.assertTrue(second.attendance_fail)

    def test_target_prefers_total_minus_counted_exam(self):
        self.assertEqual(target_entry({"entry": "34", "exam": "17", "total": "51"}), (D(34), "total"))
        # Çap olunmuş Giriş yuvarlaqlaşdırma ilə 1 yuxarı: rəsmi yekun 71 qalsın deyə hədəf 46.
        self.assertEqual(target_entry({"entry": "47", "exam": "25", "total": "71"}), (D(46), "total"))
        # T.imtahan yekunu izah edir.
        self.assertEqual(target_entry({"entry": "24", "exam": "15", "total": "51", "resit": "27"}), (D(24), "total"))
        # T.imtahan = 0 → təkrar imtahan yoxdur.
        self.assertEqual(target_entry({"entry": "24", "exam": "46", "total": "70", "resit": "0"}), (D(24), "total"))

    def test_target_falls_back_to_printed_entry(self):
        self.assertEqual(target_entry({"entry": "40", "exam": None, "total": None}), (D(40), "entry"))
        self.assertEqual(
            target_entry({"entry": "30", "exam": "15", "total": "45", "concession": "0 / 2"}), (D(30), "total")
        )
        self.assertEqual(target_entry({"entry": "30", "exam": "15", "total": "60"}), (D(30), "entry"))

    def test_target_refuses_out_of_range(self):
        self.assertEqual(target_entry({"entry": "-3", "exam": None, "total": None}), (None, "out_of_range"))
        self.assertEqual(target_entry({"entry": None}), (None, "no_entry"))


def _journal(pk, uniqid, *, semestr, group=669, lesson=1, teacher=1, parent=0, students='["7131"]', added="2026-02-03"):
    return {
        "id": pk,
        "uniqid": uniqid,
        "parent_id": parent,
        "lesson_id": lesson,
        "teacher_id": teacher,
        "groups_id": f'["{group}"]',
        "students_id": students,
        "semestr": semestr,
        "added_date": f"{added}T10:00:00",
        "fake": 0,
        "sonra_sil": 0,
        "fenn_saati": 75,
    }


EXAM_17 = D(17)


def _table(*, group=669, exam=EXAM_17, resit=None, teacher="Ülkər Q"):
    row = SheetRow(
        student_id=7131, entry=D(34), exam=exam, total=D(51), resit=resit, concession="0 / 0", attendance_fail=False
    )
    return SheetTable(group_id=group, subject="Fizika", teacher=teacher, hours=75, rows=(row,))


class JournalMatchingTests(SimpleTestCase):
    lessons = [{"id": 1, "name": "Fizika"}]
    workers = [{"id": 1, "first_name": "Ülkər", "last_name": "Q", "father_name": ""}]

    def test_exam_scores_pick_the_autumn_journal_over_a_newer_spring_one(self):
        journals = [_journal(1, "autumn", semestr=11, added="2025-09-12"), _journal(2, "spring", semestr=12)]
        finals = [{"journal_uniqid": "autumn", "student_id": 7131, "point": "17"}]
        index = JournalIndex(journals, self.lessons, self.workers, finals)
        self.assertEqual(index.choose(_table(), "2026-02-10 12:00:00"), (1, "matched"))

    def test_split_journals_form_one_family(self):
        journals = [_journal(10, "seminar", semestr=12), _journal(11, "lecture", semestr=12, parent=10, teacher=2)]
        index = JournalIndex(journals, self.lessons, self.workers, [])
        root, outcome = index.choose(_table(), "2026-07-06 12:00:00")
        self.assertEqual((root, outcome), (10, "matched"))
        self.assertEqual(index.uniqids(root), ["lecture", "seminar"])

    def test_changed_group_matches_by_students(self):
        index = JournalIndex([_journal(1, "j", semestr=12, group=700)], self.lessons, self.workers, [])
        self.assertEqual(index.choose(_table(group=669), "2026-07-06 12:00:00"), (1, "matched_by_students"))

    def test_identical_rivals_in_two_semesters_are_ambiguous(self):
        journals = [_journal(1, "a", semestr=11, added="2025-09-12"), _journal(2, "b", semestr=12, added="2025-09-12")]
        index = JournalIndex(journals, self.lessons, self.workers, [])
        self.assertEqual(index.choose(_table(), "2026-07-06 12:00:00"), (None, "ambiguous"))

    def test_retake_sheet_goes_to_the_retake_course_not_the_old_attempt(self):
        journals = [
            _journal(1, "old", semestr=4, added="2023-02-01"),
            _journal(2, "retake", semestr=12, group=700, added="2026-02-03"),
        ]
        finals = [{"journal_uniqid": "retake", "student_id": 7131, "point": "26"}]
        index = JournalIndex(journals, self.lessons, self.workers, finals)
        table = _table(exam=D(26))
        table_root, _outcome = index.choose(table, "2026-07-06 12:00:00")
        self.assertEqual(table_root, 1)  # qrup köhnə jurnalı göstərir
        self.assertEqual(
            index.choose_row(table, table.rows[0], table_root, "2026-07-06 12:00:00"), (2, "row.moved_family")
        )

    def test_old_sheet_reprinted_later_stays_with_its_exam(self):
        journals = [
            _journal(1, "old", semestr=4, added="2023-02-01"),
            _journal(2, "retake", semestr=12, group=700, added="2026-02-03"),
        ]
        finals = [{"journal_uniqid": "old", "student_id": 7131, "point": "17"}]
        index = JournalIndex(journals, self.lessons, self.workers, finals)
        table = _table()
        self.assertEqual(index.choose_row(table, table.rows[0], 1, "2026-07-06 12:00:00"), (1, "row.own_family"))

    def test_family_holding_the_students_exam_counts_as_own(self):
        journals = [
            _journal(1, "old", semestr=6, added="2023-09-15"),
            _journal(2, "retake", semestr=9, group=700, added="2025-02-03", students="[]"),
        ]
        finals = [
            {"journal_uniqid": "old", "student_id": 7131, "point": "11"},
            {"journal_uniqid": "retake", "student_id": 7131, "point": "21"},
        ]
        index = JournalIndex(journals, self.lessons, self.workers, finals)
        table = _table(exam=D(21))
        self.assertEqual(index.choose_row(table, table.rows[0], 1, "2025-10-17 12:00:00"), (2, "row.moved_family"))

    def test_sheet_with_a_different_exam_is_not_attached(self):
        journals = [_journal(1, "old", semestr=6, added="2023-09-15")]
        finals = [{"journal_uniqid": "old", "student_id": 7131, "point": "11"}]
        index = JournalIndex(journals, self.lessons, self.workers, finals)
        table = _table(exam=D(21))
        self.assertEqual(index.choose_row(table, table.rows[0], 1, "2025-10-17 12:00:00"), (None, "row.exam_conflict"))

    def test_result_copied_onto_a_retake_sheet_stays_with_the_attempt_holding_the_exam(self):
        from collections import Counter

        from apps.legacy_import.services.delta.official_entry_extract import _drop_copied_results

        journals = [
            _journal(1, "old", semestr=3, added="2022-09-15"),
            _journal(2, "retake", semestr=12, group=700, added="2026-02-03"),
        ]
        index = JournalIndex(
            journals, self.lessons, self.workers, [{"journal_uniqid": "old", "student_id": 7131, "point": "13"}]
        )
        row = _table(exam=D(13)).rows[0]
        best = {
            (1, 7131): ((True, "2025-09-05", 1), 1, "2025-09-05", row),
            (2, 7131): ((True, "2026-07-01", 2), 2, "2026-07-01", row),
        }
        stats = Counter()
        _drop_copied_results(best, index, stats)
        self.assertEqual(list(best), [(1, 7131)])
        self.assertEqual(stats["rows.copied_result_dropped"], 1)

    def test_unknown_subject_has_no_candidate(self):
        index = JournalIndex(
            [_journal(1, "j", semestr=12, lesson=2)], self.lessons + [{"id": 2, "name": "Kimya"}], [], []
        )
        self.assertEqual(index.choose(_table(), "2026-07-06 12:00:00"), (None, "no_candidate"))


def _row(uniqid, sid, *, entry, exam, total, resit=None, semestr=12):
    return {
        "family": 1,
        "journals": [uniqid],
        "semestr": semestr,
        "student_id": sid,
        "export_id": 1,
        "export_time": "2026-07-06 12:20:14",
        "entry": entry,
        "exam": exam,
        "total": total,
        "resit": resit,
        "concession": "0 / 0",
        "attendance_fail": False,
    }


def _bundle(rows):
    empty = (
        "departments specialities groups subjects workers students journals lesson_dates points excuse_windows "
        "syllabi lesson_topics"
    ).split()
    return {
        "snapshot": {"sha256": "0" * 64, "full_semesters": [], "phases": ["official_entry"], "official_entry": {}},
        **{name: [] for name in empty},
        "periods": [],
        "official_entries": rows,
    }


class OfficialEntryPhaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("sys1_actor", "sys1@example.test", "x")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Sys1 Univ",
                slug="sys1-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            chair = OrgUnit.objects.create(organization=cls.org, name="Ekologiya", slug="s1-chair", unit_type="chair")
            period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Yaz",
                academic_year="2025/2026",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=dt.date(2026, 2, 1),
                end_date=dt.date(2026, 6, 30),
                is_current=False,
            )
            subject = Subject.objects.create(organization=cls.org, code="QKU-1498", name="Hava və su", chair_unit=chair)
            cls.offering = CourseOffering.objects.create(organization=cls.org, subject=subject, period=period)
            cls.archive = AssessmentComponent.objects.create(
                organization=cls.org,
                offering=cls.offering,
                name="Davamiyyət və sərbəst iş (arxiv)",
                kind="generic",
                max_score=50,
                order=0,
            )
            kollokvium = [
                AssessmentComponent.objects.create(
                    organization=cls.org,
                    offering=cls.offering,
                    name=f"Kollokvium {i}",
                    kind="kollokvium",
                    max_score=10,
                    order=i,
                )
                for i in (1, 2, 3)
            ]
            cls.students = {}
            for sid, archive_score, k_scores, exam in (
                (7131, "14", (6, 7, 6), "17"),  # 33 + 17 = 50 kəsr → rəsmi 34 + 17 = 51 keçib
                (7132, "20", (5, 5, 5), "30"),  # artıq rəsmi dəyərdədir (35)
                (7133, "10", (5, 5, 5), "20"),  # xananı müəllim yazıb → toxunulmur
                (7135, "14", (6, 7, 6), "17"),  # rəsmi yekun 25 % ilə (34+20=54), yeni sistemdə 25 % yoxdur
                (7136, "14", (6, 7, 6), "10"),  # yeni sistemdə imtahan FƏRQLİDİR (10 ≠ 17) → toxunulmur
                (7137, "14", (6, 7, 6), None),  # yeni sistemdə imtahan balı YOXDUR → rəsmi 17 doldurulur
                (7138, "15", (6, 7, 6), "17"),  # giriş düzdür (34), yalnız 25 % balı yoxdur: 34+17 → 34+20
                (7139, "5", (2, 2, 2), None),  # köhnə vərəqdə q/b kəsri, imtahan yoxdur (giriş mənfi çap olunub)
                (
                    7140,
                    "15",
                    (6, 7, 6),
                    "12",
                ),  # giriş düzdür (34), imtahan 12 ≠ rəsmi 17 → yekun 46 < rəsmi 51 (force: 17)
                (7141, "15", (6, 7, 6), "20"),  # giriş düzdür, yekun 54 > rəsmi 51 → toxunulmur (kept_higher)
                (7142, "15", (6, 7, 6), "10"),  # tamamlanmış 25 % (13) sayılır: 34+13=47 < rəsmi 52 → 25 % 18
            ):
                user = User.objects.create_user(
                    f"s{sid}", f"s{sid}@example.test", "x", first_name="T", last_name=str(sid)
                )
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
                enrollment = Enrollment.objects.create(organization=cls.org, student=user, offering=cls.offering)
                ComponentScore.objects.create(
                    organization=cls.org,
                    component=cls.archive,
                    enrollment=enrollment,
                    score=D(archive_score),
                    entered_by=cls.actor if sid == 7133 else None,
                )
                for component, score in zip(kollokvium, k_scores):
                    ComponentScore.objects.create(
                        organization=cls.org, component=component, enrollment=enrollment, score=score
                    )
                if exam is not None:
                    FinalGrade.objects.create(organization=cls.org, enrollment=enrollment, exam_score=D(exam))
                if sid == 7142:
                    ResitRecord.objects.create(
                        organization=cls.org,
                        enrollment=enrollment,
                        reason="total",
                        status="completed",
                        resit_score=D("13"),
                    )
                cls.students[sid] = enrollment

    def _rows(self):
        return [
            _row("ZMRpRj5xOW", 7131, entry="34", exam="17", total="51"),
            _row("ZMRpRj5xOW", 7132, entry="35", exam="30", total="65"),
            _row("ZMRpRj5xOW", 7133, entry="30", exam="20", total="50"),
            _row("ZMRpRj5xOW", 7135, entry="34", exam="17", total="54", resit="20"),
            _row("ZMRpRj5xOW", 7136, entry="34", exam="17", total="51"),
            _row("ZMRpRj5xOW", 7137, entry="34", exam="17", total="51"),
            _row("ZMRpRj5xOW", 7138, entry="34", exam="17", total="54", resit="20"),
            _row("ZMRpRj5xOW", 9999, entry="30", exam="20", total="50"),  # ledger-də yoxdur
            _row("ZMRpRj5xOW", 7134, entry="-2", exam=None, total=None),
        ]

    def _force_rows(self):
        return [
            _row("ZMRpRj5xOW", 7140, entry="34", exam="17", total="51"),
            _row("ZMRpRj5xOW", 7141, entry="34", exam="17", total="51"),
            _row("ZMRpRj5xOW", 7142, entry="34", exam="10", total="52", resit="18"),
            _row("ZMRpRj5xOW", 7136, entry="34", exam="17", total="51"),
        ]

    def _run(self, *, apply, bundle=None, phases=("official_entry",), force_total=False):
        ledger = {f"ZMRpRj5xOW:{sid}": str(enrollment.pk) for sid, enrollment in self.students.items()}

        def fake(_organization, entity_type, legacy_pks=None):
            found = ledger if entity_type == "journal_enrollment" else {}
            keys = {str(key) for key in legacy_pks or found}
            return {key: value for key, value in found.items() if key in keys}

        with mock.patch("apps.legacy_import.services.delta.resolve.ledger_map", fake), bypass_rls():
            return execute(
                organization=self.org,
                actor=self.actor,
                bundle=bundle or _bundle(self._rows()),
                apply=apply,
                until=dt.date(2026, 11, 3),
                tag="delta-sys1",
                phases=phases,
                setup=(lambda run: setattr(run, "force_official_total", True)) if force_total else None,
            )

    def _archive(self, sid):
        with bypass_rls():
            return ComponentScore.objects.get(component=self.archive, enrollment=self.students[sid]).score

    def test_dry_run_counts_but_writes_nothing(self):
        run = self._run(apply=False)
        self.assertEqual(run.counters["official_entry.sem12.written"], 3)
        # 7131 (giriş 33→34) və 7135 (25 % balı doldurulur) kəsr → keçib; 7137 «nəticə yoxdur» → keçib.
        self.assertEqual(run.counters["official_entry.fail_to_pass"], 2)
        self.assertEqual(run.counters["official_entry.open_to_pass"], 1)
        self.assertEqual(self._archive(7131), D("14"))
        with bypass_rls():
            self.assertFalse(ResitRecord.objects.filter(enrollment=self.students[7135]).exists())
            self.assertFalse(FinalGrade.objects.filter(enrollment=self.students[7137]).exists())

    def test_apply_raises_only_the_archive_cell_and_reports(self):
        run = self._run(apply=True)
        counters = run.counters
        self.assertEqual(counters["official_entry.sem12.written"], 3)
        self.assertEqual(counters["official_entry.sem12.written_from_total"], 3)
        self.assertEqual(counters["official_entry.sem12.fail_to_pass"], 2)
        self.assertEqual(counters["official_entry.sem12.same"], 2)
        self.assertEqual(counters["official_entry.sem12.skip_edited_kept"], 1)
        self.assertEqual(counters["official_entry.sem12.skip_enrollment_unresolved"], 1)
        self.assertEqual(counters["official_entry.sem12.skip_out_of_range"], 1)
        self.assertEqual(self._archive(7131), D("15"))
        self.assertEqual(self._archive(7132), D("20"))
        self.assertEqual(self._archive(7133), D("10"))
        with bypass_rls():
            kollokvium = ComponentScore.objects.filter(enrollment=self.students[7131], component__kind="kollokvium")
            self.assertEqual(sorted(cs.score for cs in kollokvium), [D(6), D(6), D(7)])
            audit = AuditLog.objects.get(resource_type="registrar.grade.component", resource_id=str(self.offering.pk))
        self.assertEqual(len(audit.changes), 3)
        self.assertEqual({(c["old"], c["new"]) for c in audit.changes}, {("14", "15")})
        self.assertIn("SYS-1", audit.new_values["reason"])
        flips = sorted(row[2] for row in run.name_rows if row[0] == "official_entry_fail_to_pass")
        self.assertEqual(len(flips), 2)
        self.assertIn("giriş 33→34 · yekun 50→51", flips[0])
        self.assertIn("giriş 33→34 · yekun 50→54", flips[1])

    def test_missing_resit_and_exam_are_filled_from_the_sheet(self):
        """«Kəsildi — 25 %» / «nəticə yoxdur» rəsmi vərəqdə keçən tələbədə görünməsin (sahib 2026-11-03)."""
        run = self._run(apply=True)
        self.assertEqual(run.counters["official_entry.sem12.filled_resit"], 2)
        self.assertEqual(run.counters["official_entry.sem12.filled_exam"], 1)
        with bypass_rls():
            resit = ResitRecord.objects.get(enrollment=self.students[7135])
            grade = FinalGrade.objects.get(enrollment=self.students[7137])
            self.assertEqual((resit.resit_score, resit.status, resit.reason), (D(20), "completed", "total"))
            self.assertEqual(grade.exam_score, D(17))
            self.assertTrue(AuditLog.objects.filter(resource_type="registrar.grade.resit").exists())
            self.assertTrue(AuditLog.objects.filter(resource_type="registrar.grade.final").exists())
        self.assertEqual(self._archive(7135), D("15"))
        self.assertEqual(self._archive(7137), D("15"))
        # Yalnız doldurma: giriş yerində qalır, nəticə yenə də hesabata/adlı siyahıya düşür.
        self.assertEqual(self._archive(7138), D("15"))
        only_fill = [row for row in run.name_rows if "doldurulub: resit" in row[2] and "giriş 34→34" in row[2]]
        self.assertEqual(len(only_fill), 1)
        self.assertEqual(only_fill[0][0], "official_entry_changed")

    def test_different_existing_exam_is_kept_and_listed(self):
        run = self._run(apply=True)
        self.assertEqual(run.counters["official_entry.sem12.skip_total_mismatch"], 1)
        self.assertEqual(self._archive(7136), D("14"))
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.students[7136]).exam_score, D(10))
        mismatch = [row for row in run.name_rows if row[0] == "official_entry_total_mismatch"]
        self.assertEqual(len(mismatch), 1)
        self.assertIn("rəsmi 51", mismatch[0][2])

    def test_second_run_writes_nothing(self):
        self._run(apply=True)
        run = self._run(apply=True)
        self.assertEqual(run.counters["official_entry.sem12.written"], 0)
        self.assertEqual(run.counters["official_entry.sem12.same"], 5)
        self.assertEqual(run.counters["official_entry.sem12.filled_exam"], 0)

    def test_conflicting_targets_for_one_enrollment_are_skipped(self):
        rows = [
            _row("ZMRpRj5xOW", 7131, entry="34", exam="17", total="51"),
            _row("ZMRpRj5xOW", 7131, entry="36", exam="17", total="53"),
        ]
        run = self._run(apply=True, bundle=_bundle(rows))
        self.assertEqual(run.counters["official_entry.sem12.skip_target_conflict"], 1)
        self.assertEqual(self._archive(7131), D("14"))

    def test_sheet_with_total_wins_over_entry_only_sheet(self):
        rows = [
            _row("ZMRpRj5xOW", 7131, entry="8", exam=None, total=None),
            _row("ZMRpRj5xOW", 7131, entry="34", exam="17", total="51"),
            _row("ZMRpRj5xOW", 7132, entry="35", exam="30", total="65"),
            _row("ZMRpRj5xOW", 7132, entry="12", exam=None, total=None),
        ]
        run = self._run(apply=True, bundle=_bundle(rows))
        self.assertEqual(run.counters["official_entry.sem12.skip_target_conflict"], 0)
        self.assertEqual(self._archive(7131), D("15"))
        self.assertEqual(run.counters["official_entry.sem12.same"], 1)

    def test_previous_attempt_result_printed_on_a_retake_sheet_is_not_copied(self):
        """Köhnə vərəq təkrar keçilən jurnalda əvvəlki cəhdin nəticəsini çap edib — yeni cəhdə köçürülmür."""
        with bypass_rls():
            old_period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Payız",
                academic_year="2022/2023",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=dt.date(2022, 9, 15),
                end_date=dt.date(2023, 1, 31),
            )
            old_offering = CourseOffering.objects.create(
                organization=self.org, subject=self.offering.subject, period=old_period
            )
            old = Enrollment.objects.create(
                organization=self.org, student=self.students[7137].student, offering=old_offering
            )
            FinalGrade.objects.create(organization=self.org, enrollment=old, exam_score=D(17))
        run = self._run(apply=True, bundle=_bundle([_row("ZMRpRj5xOW", 7137, entry="34", exam="17", total="51")]))
        self.assertEqual(run.counters["official_entry.sem12.skip_copied_attempt"], 1)
        with bypass_rls():
            self.assertFalse(FinalGrade.objects.filter(enrollment=self.students[7137]).exists())
        self.assertEqual(self._archive(7137), D("14"))

    def test_legacy_attendance_fail_is_recorded(self):
        row = _row("ZMRpRj5xOW", 7139, entry="-2", exam=None, total=None)
        row["attendance_fail"] = True
        run = self._run(apply=True, bundle=_bundle([row]))
        self.assertEqual(run.counters["official_entry.sem12.filled_qb"], 1)
        with bypass_rls():
            self.assertTrue(Enrollment.objects.get(pk=self.students[7139].pk).legacy_qb_fail)
        self.assertEqual(self._archive(7139), D("5"))  # giriş hədəfi yoxdur — arxiv toxunulmur

    def test_bundle_rejects_other_phases(self):
        with self.assertRaises(OfficialEntryPhaseMismatch):
            self._run(apply=False, phases=("official_entry", "lessons"))


class OfficialTotalForceTests(OfficialEntryPhaseTests):
    """Sahib 2026-11-09: köhnə bazadakı rəsmi yekun (maksimum) tələbənin nəticəsidir — imtahan/25 % balı ona çatdırılır."""

    def test_without_flag_lower_totals_stay_listed_only(self):
        run = self._run(apply=True, bundle=_bundle(self._force_rows()))
        self.assertEqual(run.counters["official_entry.sem12.same"], 3)
        self.assertEqual(run.counters["official_entry.sem12.skip_total_mismatch"], 1)
        self.assertFalse(any(key.startswith("official_entry.total_fix") for key in run.counters))
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.students[7140]).exam_score, D(12))

    def test_force_raises_counted_exam_or_resit_to_the_official_total(self):
        run = self._run(apply=True, bundle=_bundle(self._force_rows()), force_total=True)
        counters = run.counters
        self.assertEqual(counters["official_entry.total_fix_exam"], 2)  # 7140 (giriş eyni) + 7136 (giriş 33→34)
        self.assertEqual(counters["official_entry.total_fix_resit"], 1)  # 7142
        self.assertEqual(counters["official_entry.total_fix_kept_higher"], 1)  # 7141
        self.assertEqual(counters["official_entry.sem12.skip_total_mismatch"], 0)
        self.assertEqual(counters["official_entry.sem12.written"], 1)  # 7136 giriş + imtahan
        self.assertEqual(counters["official_entry.fail_to_pass"], 3)
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.students[7140]).exam_score, D(17))
            self.assertEqual(FinalGrade.objects.get(enrollment=self.students[7141]).exam_score, D(20))
            self.assertEqual(FinalGrade.objects.get(enrollment=self.students[7136]).exam_score, D(17))
            self.assertEqual(FinalGrade.objects.get(enrollment=self.students[7142]).exam_score, D(10))
            self.assertEqual(ResitRecord.objects.get(enrollment=self.students[7142]).resit_score, D(18))
            audit = AuditLog.objects.filter(resource_type="registrar.grade.final", resource_id=str(self.offering.pk))
            self.assertTrue(audit.exists())
            self.assertTrue(any("rəsmi yekuna" in (str(a.new_values) + str(a.changes)) for a in audit))
        self.assertEqual(self._archive(7136), D("15"))
        forced = [row for row in run.name_rows if row[0] == "official_entry_total_forced"]
        self.assertEqual(len(forced), 3)
        self.assertTrue(any("yekun 46→51" in row[2] for row in forced))
        self.assertTrue(any("yekun 47→52" in row[2] for row in forced))

    def test_force_is_idempotent(self):
        self._run(apply=True, bundle=_bundle(self._force_rows()), force_total=True)
        again = self._run(apply=True, bundle=_bundle(self._force_rows()), force_total=True)
        self.assertEqual(again.counters["official_entry.sem12.same"], 4)
        self.assertEqual(again.counters.get("official_entry.total_fix_exam", 0), 0)
        self.assertEqual(again.counters.get("official_entry.total_fix_resit", 0), 0)
