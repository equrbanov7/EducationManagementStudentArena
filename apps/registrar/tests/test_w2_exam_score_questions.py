"""W2 `w2paper` (2026-09-14) — kağız imtahanının SUAL-SUAL balları, apellyasiya növü, «Dəyişən nəticələr» (servis qatı).

Sahibin tələbi: «İmtahandan max bal 50, hər sualdan max 10, yekun bal 100-dən
çox ola bilməz — hamısına nəzarət et; apellyasiyadan sonra DƏYİŞƏN nəticələr
izlənsin.» Burada yoxlanır:

* validasiya matrisi (sual > tavan, cəm > 50, sayı > sual sayı, tam olmayan,
  giriş + imtahan > 100) — hamısı fail-closed, dəqiq mesajla;
* ``record_exam_score`` sual balları ilə: cəm ``FinalGrade.exam_score``-a düşür,
  sətirdə ``question_scores`` qalır; eyni cəm + fərqli bölgü = dəyişiklik;
* dəyişiklik növü ``appeal`` / ``correction`` (ilkin həmişə ``initial``);
* vərəq şəbəkəsi (``question_count`` / ``question_max``) yazını idarə edir;
  ``question_count = 0`` tək bal rejimidir;
* idxal: S1..Sn sütunları planda cəm olur; «Bal» olmadan da fayl qəbul olunur;
* «Dəyişən nəticələr»: yalnız ``kind != initial``, filtrlər, əhatə (yad qrup
  görünmür), CSV sətirləri.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q
from django.test import TestCase, override_settings

from apps.organizations.models import Membership, OrgUnit
from apps.registrar import exam_score_changes as changes
from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_import as importer
from apps.registrar import exam_score_questions as questions
from apps.registrar import exam_score_sheets as sheets
from apps.registrar.models import CorrectionReason, ExamScoreEntry, ExamScoreEntryKind, FinalGrade
from apps.registrar.models.exam_score_entry import ExamScoreSheetKind
from apps.registrar.tests import test_exam_score_entry as fixtures
from core.constants import OrgUnitType
from core.rls import bypass_rls

#: Etiket kataloqdan gəlir (fill skripti işlədilməmiş ola bilər) — literal yox.
PRACTICAL_LABEL = str(ExamScoreSheetKind.PRACTICAL.label)


def _pdf(name="teqdimat.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


class QuestionValidationMatrixTest(TestCase):
    """Təmiz funksiyalar — DB yoxdur."""

    def test_defaults_and_grid(self):
        self.assertEqual(questions.clean_question_grid("", ""), (5, 10))
        self.assertEqual(questions.clean_question_grid("0", "10"), (0, 10))
        self.assertEqual(questions.clean_question_grid("10", "7"), (10, 7))
        for count, max_ in (("11", "10"), ("-1", "10"), ("5", "0"), ("5", "101"), ("x", "10")):
            with self.assertRaises(ValidationError, msg=(count, max_)):
                questions.clean_question_grid(count, max_)

    def test_sum_and_blank_rules(self):
        scores, total = questions.clean_question_scores(
            ["10", "9", "", "8", "0"], question_count=5, question_max=10, cap=50
        )
        self.assertEqual(scores, [10, 9, 0, 8, 0])
        self.assertEqual(total, Decimal(27))
        self.assertEqual(
            questions.clean_question_scores(["", "", ""], question_count=5, question_max=10, cap=50), (None, None)
        )
        self.assertEqual(questions.clean_question_scores(None, question_count=5, question_max=10, cap=50), (None, None))

    def test_question_above_max_is_rejected_with_label(self):
        with self.assertRaises(ValidationError) as caught:
            questions.clean_question_scores(["10", "11"], question_count=5, question_max=10, cap=50)
        self.assertIn("S2", " ".join(caught.exception.messages))
        self.assertIn("10", " ".join(caught.exception.messages))

    def test_sum_above_cap_is_rejected(self):
        # 5 × 10 = 50 keçir; 6 sual · 9 = 54 > 50 rədd (cap sxemdən gəlir, burada 50).
        questions.clean_question_scores(["10"] * 5, question_count=5, question_max=10, cap=50)
        with self.assertRaises(ValidationError) as caught:
            questions.clean_question_scores(["9"] * 6, question_count=6, question_max=10, cap=50)
        self.assertIn("54", " ".join(caught.exception.messages))
        # Tavan 40 olan sxemdə 45 də rədd.
        with self.assertRaises(ValidationError):
            questions.clean_question_scores(["9"] * 5, question_count=5, question_max=10, cap=40)

    def test_count_mismatch_and_zero_count(self):
        with self.assertRaises(ValidationError) as caught:
            questions.clean_question_scores(["1", "1", "1"], question_count=2, question_max=10, cap=50)
        self.assertIn("2", " ".join(caught.exception.messages))
        with self.assertRaises(ValidationError):
            questions.clean_question_scores(["1"], question_count=0, question_max=10, cap=50)

    def test_non_integer_and_negative(self):
        for bad in (["7.5"], ["abc"], ["-1"], ["NaN"], ["1e3"]):
            with self.assertRaises(ValidationError, msg=bad):
                questions.clean_question_scores(bad, question_count=5, question_max=10, cap=50)
        scores, _total = questions.clean_question_scores(["7.0", "3,0"], question_count=5, question_max=10, cap=50)
        self.assertEqual(scores, [7, 3])

    def test_total_within_hundred(self):
        questions.assert_total_within_hundred(Decimal(50), Decimal(50))
        questions.assert_total_within_hundred(None, Decimal(50))
        with self.assertRaises(ValidationError):
            questions.assert_total_within_hundred(Decimal(51), Decimal(50))

    def test_same_question_scores(self):
        self.assertTrue(questions.same_question_scores(None, None))
        self.assertFalse(questions.same_question_scores(None, [1]))
        self.assertTrue(questions.same_question_scores([1, 2], ["1", "2"]))
        self.assertFalse(questions.same_question_scores([1, 2], [2, 1]))


@override_settings(MEDIA_ROOT=fixtures._MEDIA)
class QuestionScoreServiceTest(fixtures.ExamScoreEntryServiceTest):
    """Servis qatı — mövcud iki-qruplu fixture üzərində (``setUp`` miras alınır)."""

    # Mövcud testlər miras alınmasın deyə (onlar öz faylında işləyir) — yalnız yeni testlər.
    def _sheet(self, **grid):
        with bypass_rls():
            return sheets.create_sheet(offering=self.offering_a, by_user=self.center, **grid)

    def _enrollment(self, key="a1"):
        return self.students[key].enrollments.get(offering=self.offering_a)

    def test_question_scores_write_sum_and_keep_breakdown(self):
        sheet = self._sheet(question_count=5, question_max=10)
        with bypass_rls():
            entry = service.record_exam_score(
                enrollment=self._enrollment(),
                score="999",  # sual rejimində nəzərə alınmır — server cəmi hesablayır
                by_user=self.center,
                sheet=sheet,
                question_scores=["10", "8", "", "7", "5"],
            )
            self.assertEqual(entry.new_score, Decimal(30))
            self.assertEqual(entry.question_scores, [10, 8, 0, 7, 5])
            self.assertEqual(entry.kind, ExamScoreEntryKind.INITIAL)
            self.assertEqual(FinalGrade.objects.get(enrollment=entry.enrollment).exam_score, Decimal(30))

    def test_question_above_sheet_max_is_rejected_before_any_write(self):
        sheet = self._sheet(question_count=5, question_max=10)
        with bypass_rls():
            with self.assertRaises(ValidationError):
                service.record_exam_score(
                    enrollment=self._enrollment(),
                    score="",
                    by_user=self.center,
                    sheet=sheet,
                    question_scores=["11", "1"],
                )
            self.assertFalse(FinalGrade.objects.filter(enrollment=self._enrollment()).exists())
            self.assertFalse(ExamScoreEntry.objects.filter(enrollment=self._enrollment()).exists())

    def test_sum_above_scheme_cap_is_rejected(self):
        sheet = self._sheet(question_count=10, question_max=10)
        with bypass_rls():
            with self.assertRaises(ValidationError) as caught:
                service.record_exam_score(
                    enrollment=self._enrollment(),
                    score="",
                    by_user=self.center,
                    sheet=sheet,
                    question_scores=["10"] * 6,
                )
        self.assertIn("50", " ".join(caught.exception.messages))

    def test_more_questions_than_sheet_count_is_rejected(self):
        sheet = self._sheet(question_count=3, question_max=10)
        with bypass_rls():
            with self.assertRaises(ValidationError):
                service.record_exam_score(
                    enrollment=self._enrollment(),
                    score="",
                    by_user=self.center,
                    sheet=sheet,
                    question_scores=["1", "1", "1", "1"],
                )

    def test_zero_question_sheet_is_single_total_mode(self):
        sheet = self._sheet(question_count=0)
        with bypass_rls():
            with self.assertRaises(ValidationError):
                service.record_exam_score(
                    enrollment=self._enrollment(), score="", by_user=self.center, sheet=sheet, question_scores=["5"]
                )
            entry = service.record_exam_score(
                enrollment=self._enrollment(), score="41", by_user=self.center, sheet=sheet, question_scores=["", ""]
            )
            self.assertEqual(entry.new_score, Decimal(41))
            self.assertIsNone(entry.question_scores)

    def test_entry_plus_exam_above_hundred_is_rejected(self):
        with bypass_rls():
            with self.assertRaises(ValidationError) as caught:
                service.record_exam_score(
                    enrollment=self._enrollment(), score="50", by_user=self.center, entry_score=Decimal(51)
                )
        self.assertIn("100", " ".join(caught.exception.messages))
        with bypass_rls():
            self.assertFalse(FinalGrade.objects.filter(enrollment=self._enrollment()).exists())

    def test_same_sum_different_breakdown_is_a_documented_change(self):
        sheet = self._sheet(question_count=5, question_max=10)
        with bypass_rls():
            enrollment = self._enrollment()
            service.record_exam_score(
                enrollment=enrollment, score="", by_user=self.center, sheet=sheet, question_scores=["10", "10"]
            )
            # Eyni bölgü → idempotent.
            self.assertIsNone(
                service.record_exam_score(
                    enrollment=enrollment, score="", by_user=self.center, sheet=sheet, question_scores=["10", "10"]
                )
            )
            # Fərqli bölgü, eyni cəm → sənədsiz RƏDD, sənədlə yeni sətir (FinalGrade dəyişmir).
            with self.assertRaises(ValidationError):
                service.record_exam_score(
                    enrollment=enrollment, score="", by_user=self.center, sheet=sheet, question_scores=["5", "15"]
                )
            entry = service.record_exam_score(
                enrollment=enrollment,
                score="",
                by_user=self.center,
                sheet=sheet,
                question_scores=["10", "5", "5"],
                reason=CorrectionReason.TECHNICAL,
                note="bölgü səhv yazılmışdı",
                evidence=_pdf(),
                kind=ExamScoreEntryKind.APPEAL,
            )
            self.assertEqual(entry.kind, ExamScoreEntryKind.APPEAL)
            self.assertEqual(entry.old_score, Decimal(20))
            self.assertEqual(entry.new_score, Decimal(20))
            self.assertEqual(entry.question_scores, [10, 5, 5])
            self.assertEqual(FinalGrade.objects.get(enrollment=enrollment).exam_score, Decimal(20))

    def test_change_kind_appeal_and_unknown_kind_fallback(self):
        with bypass_rls():
            enrollment = self._enrollment()
            first = service.record_exam_score(enrollment=enrollment, score="40", by_user=self.center, kind="appeal")
            self.assertEqual(first.kind, ExamScoreEntryKind.INITIAL)  # ilkin həmişə initial
            appeal = service.record_exam_score(
                enrollment=enrollment,
                score="45",
                by_user=self.center,
                kind="appeal",
                reason=CorrectionReason.APPEAL,
                note="komissiya qərarı",
                evidence=_pdf(),
            )
            self.assertEqual(appeal.kind, ExamScoreEntryKind.APPEAL)
            other = service.record_exam_score(
                enrollment=enrollment,
                score="44",
                by_user=self.center,
                kind="bogus",
                reason=CorrectionReason.TECHNICAL,
                note="yenidən",
                evidence=_pdf(),
            )
            self.assertEqual(other.kind, ExamScoreEntryKind.CORRECTION)

    def test_roster_save_with_question_rows_uses_batch_entry_scores(self):
        sheet = self._sheet(question_count=5, question_max=10)
        rows = [
            {"enrollment_id": str(self._enrollment("a1").id), "score": "", "question_scores": ["10", "10", "10"]},
            {"enrollment_id": str(self._enrollment("a2").id), "score": "", "question_scores": ["10", "11"]},
        ]
        with bypass_rls():
            result = service.save_roster_scores(offering=self.offering_a, rows=rows, by_user=self.center, sheet=sheet)
            self.assertEqual((result["written"], result["failed"]), (1, 1))
            self.assertEqual(FinalGrade.objects.get(enrollment=self._enrollment("a1")).exam_score, Decimal(30))
            self.assertFalse(FinalGrade.objects.filter(enrollment=self._enrollment("a2")).exists())
        self.assertIn("S2", result["errors"][0][1])

    def test_sheet_metadata_carries_grid_and_defaults_from_last_sheet(self):
        meta = sheets.sheet_metadata_from_post(
            {"question_count": "3", "question_max": "8"}, {}, offering=self.offering_a
        )
        self.assertEqual((meta["question_count"], meta["question_max"]), (3, 8))
        with self.assertRaises(ValidationError):
            sheets.sheet_metadata_from_post({"question_count": "11"}, {}, offering=self.offering_a)
        self.assertEqual(sheets.latest_sheet_defaults([])["question_count"], 5)
        self._sheet(question_count=4, question_max=9, protocol_number="P-1", evidence=_pdf())
        with bypass_rls():
            defaults = sheets.latest_sheet_defaults(sheets.sheets_for_offering(offering=self.offering_a))
        self.assertEqual((defaults["question_count"], defaults["question_max"]), (4, 9))

    # ── idxal ────────────────────────────────────────────────────────────────
    def _roster(self):
        with bypass_rls():
            return service.roster_for_offering(offering=self.offering_a)

    def test_import_accepts_question_columns_without_total(self):
        csv = "username,S1,S2,S3\n%s,10,9,8\n%s,10,11,0\n" % (
            self.students["a1"].username,
            self.students["a2"].username,
        )
        rows = importer.read_rows(SimpleUploadedFile("ballar.csv", csv.encode()))
        self.assertEqual(rows[0]["questions"], {1: "10", 2: "9", 3: "8"})
        plan = importer.build_plan(roster=self._roster(), rows=rows)
        self.assertEqual([item["status"] for item in plan], ["new", "error"])
        self.assertEqual(plan[0]["score"], "27")
        self.assertEqual(plan[0]["question_scores"], [10, 9, 8])
        self.assertIn("S2", plan[1]["message"])
        self.assertEqual(importer.rows_for_service(plan)[0]["question_scores"], [10, 9, 8])

    def test_import_question_row_beats_total_column_and_respects_grid(self):
        csv = "username,Bal,Sual 1,Sual 2\n%s,50,3,4\n" % self.students["a1"].username
        rows = importer.read_rows(SimpleUploadedFile("ballar.csv", csv.encode()))
        plan = importer.build_plan(roster=self._roster(), rows=rows)
        self.assertEqual(plan[0]["score"], "7")
        plan = importer.build_plan(roster=self._roster(), rows=rows, question_count=1)
        self.assertEqual(plan[0]["status"], "error")

    def test_import_template_has_question_columns(self):
        columns = importer.template_columns(50, 3, 10)
        self.assertEqual([c for c in columns if c.startswith("S")], ["S1 (0–10)", "S2 (0–10)", "S3 (0–10)"])
        payload, _ctype, name = importer.build_template(roster=self._roster(), fmt="csv", question_count=2)
        self.assertTrue(name.endswith(".csv"))
        self.assertIn("S2 (0–10)", payload.decode("utf-8-sig").splitlines()[0])
        self.assertNotIn("S3", payload.decode("utf-8-sig").splitlines()[0])

    # ── «Dəyişən nəticələr» ──────────────────────────────────────────────────
    def _make_changes(self):
        with bypass_rls():
            a1, b1 = self._enrollment("a1"), self.students["b1"].enrollments.get()
            for enrollment in (a1, b1):
                service.record_exam_score(enrollment=enrollment, score="30", by_user=self.center)
            service.record_exam_score(
                enrollment=a1,
                score="35",
                by_user=self.center,
                kind="appeal",
                reason=CorrectionReason.APPEAL,
                note="apellyasiya",
                evidence=_pdf(),
            )
            service.record_exam_score(
                enrollment=b1,
                score="31",
                by_user=self.center,
                kind="correction",
                reason=CorrectionReason.TECHNICAL,
                note="texniki",
                evidence=_pdf(),
            )
        return a1, b1

    def test_changes_queryset_lists_only_non_initial_and_filters(self):
        a1, b1 = self._make_changes()
        scope = Q(organization=self.org)
        with bypass_rls():
            rows = [changes.change_row(e) for e in changes.changes_queryset(scope=scope)]
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["kind"] for r in rows}, {"appeal", "correction"})
            self.assertEqual({str(r["old"]) + "→" + str(r["new"]) for r in rows}, {"30→35", "30→31"})
            only_appeal = list(changes.changes_queryset(scope=scope, kind="appeal"))
            self.assertEqual([e.enrollment_id for e in only_appeal], [a1.id])
            by_group = list(changes.changes_queryset(scope=scope, group_id=str(self.group_b.id)))
            self.assertEqual([e.enrollment_id for e in by_group], [b1.id])
            by_search = list(changes.changes_queryset(scope=scope, search=self.students["b1"].username))
            self.assertEqual([e.enrollment_id for e in by_search], [b1.id])
            self.assertEqual(changes.changes_queryset(scope=scope, instructor_id=str(self.center.id)).count(), 0)
            self.assertEqual(changes.changes_queryset(scope=None).count(), 0)
            self.assertEqual(
                changes.changes_queryset(scope=scope, date_from=changes.parse_date("2099-01-01")).count(), 0
            )

    def test_changes_scope_hides_foreign_subtree(self):
        """Yad fakültənin dekanı (açar açıq verilsə belə) yalnız öz alt-ağacını görür."""
        self._make_changes()
        with bypass_rls():
            dean_role = self.org.roles.get(name="dean")
            permissions = list(dean_role.permissions or [])
            if service.ENTRY_PERMISSION not in permissions:
                dean_role.permissions = permissions + [service.ENTRY_PERMISSION]
                dean_role.save(update_fields=["permissions"])
            faculty = OrgUnit.objects.create(
                organization=self.org, name="B fakültəsi", slug="w2-fac-b", unit_type=OrgUnitType.FACULTY
            )
            self.group_b.parent = faculty
            self.group_b.save()
            dean = fixtures.User.objects.create_user("w2_dean", "w2_dean@qku.edu.az", "pw")
            Membership.objects.create(
                user=dean, organization=self.org, role=dean_role, scope_unit=faculty, is_primary=True, is_active=True
            )
            scope = changes.scope_q(dean, self.org, permission=service.ENTRY_PERMISSION)
            rows = list(changes.changes_queryset(scope=scope))
            self.assertEqual([e.enrollment.offering.group_id for e in rows], [self.group_b.id])
            self.assertIsNone(changes.scope_q(self.teacher, self.org, permission=service.ENTRY_PERMISSION))

    def test_csv_rows_match_table(self):
        self._make_changes()
        with bypass_rls():
            queryset = changes.changes_queryset(scope=Q(organization=self.org))
            rows = list(changes.csv_rows(queryset))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(rows[0]), len(changes.csv_header()))
        self.assertIn("35", rows[0] + rows[1])

    # ── ADDENDUM 2026-09-14: imtahan növü ────────────────────────────────────
    def test_clean_exam_kind_and_sheet_defaults(self):
        self.assertEqual(sheets.clean_exam_kind(""), "written")
        self.assertEqual(sheets.clean_exam_kind("practical"), "practical")
        with self.assertRaises(ValidationError):
            sheets.clean_exam_kind("oral")
        meta = sheets.sheet_metadata_from_post({"exam_kind": "practical"}, {}, offering=self.offering_a)
        self.assertEqual(meta["exam_kind"], "practical")
        self._sheet(exam_kind="practical")
        with bypass_rls():
            rows = sheets.sheets_for_offering(offering=self.offering_a)
            self.assertEqual(rows[0]["exam_kind_label"], PRACTICAL_LABEL)
            self.assertEqual(sheets.latest_sheet_defaults(rows)["exam_kind"], "practical")
            self.assertEqual(sheets.sheets_for_offering(offering=self.offering_a, exam_kind="written"), [])

    def test_exam_kind_filter_counts_legacy_rows_as_written(self):
        """Vərəqsiz (köhnə) sətir «yazılı» sayılır; praktiki filtr onu göstərmir."""
        a1, b1 = self._make_changes()  # vərəqsiz sətirlər
        practical = self._sheet(exam_kind="practical")
        with bypass_rls():
            service.record_exam_score(
                enrollment=a1,
                score="36",
                by_user=self.center,
                sheet=practical,
                kind="appeal",
                reason=CorrectionReason.APPEAL,
                note="praktiki",
                evidence=_pdf(),
            )
            scope = Q(organization=self.org)
            self.assertEqual(changes.changes_queryset(scope=scope).count(), 3)
            self.assertEqual(changes.changes_queryset(scope=scope, exam_kind="practical").count(), 1)
            self.assertEqual(changes.changes_queryset(scope=scope, exam_kind="written").count(), 2)
            row = changes.change_row(changes.changes_queryset(scope=scope, exam_kind="practical").first())
            self.assertEqual((row["exam_kind"], row["is_practical"]), ("practical", True))
            csv_row = next(changes.csv_rows(changes.changes_queryset(scope=scope, exam_kind="practical")))
            self.assertIn(PRACTICAL_LABEL, csv_row)

    def test_paper_kind_stats_are_per_kind_and_use_latest_entry(self):
        a1, b1 = self._make_changes()  # a1: 30 → 35 (appeal), b1: 30 → 31 (correction) — vərəqsiz = yazılı
        practical = self._sheet(exam_kind="practical")
        a2 = self._enrollment("a2")
        with bypass_rls():
            service.record_exam_score(enrollment=a2, score="10", by_user=self.center, sheet=practical)
            stats = {row["kind"]: row for row in changes.paper_kind_stats(organization=self.org)}
        self.assertEqual(stats["written"]["entries"], 4)
        self.assertEqual(stats["written"]["changes"], 2)
        self.assertEqual(stats["written"]["students"], 2)
        self.assertEqual(stats["written"]["avg"], 33.0)  # (35 + 31) / 2 — sonuncu daxiletmələr
        self.assertEqual(stats["written"]["sheets"], 0)
        self.assertEqual(
            (stats["practical"]["sheets"], stats["practical"]["entries"], stats["practical"]["avg"]), (1, 1, 10.0)
        )
        with bypass_rls():
            only = changes.paper_kind_stats(organization=self.org, exam_kind="practical")
            self.assertEqual([row["kind"] for row in only], ["practical"])
            none = changes.paper_kind_stats(organization=self.org, year_start=1999)
        self.assertEqual(sum(row["entries"] for row in none), 0)

    # ── Sahibin rəyi (2026-09-14, 2-ci dövrə): yoxlayan / nəzarətçi seçimi ─────
    def test_staff_selects_resolve_users_and_snapshot_names(self):
        teachers = service.teachers_for_organization(organization=self.org)
        self.assertIn(str(self.teacher.id), {row["id"] for row in teachers})
        self.assertNotIn(str(self.students["a1"].id), {row["id"] for row in teachers})
        meta = sheets.sheet_metadata_from_post(
            {"examiner": str(self.teacher.id), "invigilator": str(self.center.id)}, {}, offering=self.offering_a
        )
        self.assertEqual(meta["examiner"], self.teacher)
        self.assertEqual(meta["invigilator"], self.center)
        self.assertEqual(meta["invigilator_name"], self.center.get_full_name() or self.center.username)
        # Boş yoxlayan → açılışın müəllimi; köhnə sərbəst-mətn nəzarətçi fallback.
        meta = sheets.sheet_metadata_from_post({"invigilator_name": "Kənar nəzarətçi"}, {}, offering=self.offering_a)
        self.assertEqual(meta["examiner"], self.teacher)
        self.assertIsNone(meta["invigilator"])
        self.assertEqual(meta["invigilator_name"], "Kənar nəzarətçi")
        with bypass_rls():
            stranger = fixtures.User.objects.create_user("w2_stranger_reg", "w2_stranger_reg@qku.edu.az", "pw")
        for raw in (str(stranger.id), "abc", "999999999"):
            with self.assertRaises(ValidationError, msg=raw):
                sheets.sheet_metadata_from_post({"invigilator": raw}, {}, offering=self.offering_a)
        with bypass_rls():
            sheet = sheets.create_sheet(offering=self.offering_a, by_user=self.center, invigilator=self.center)
            self.assertEqual(sheet.invigilator_id, self.center.id)
            self.assertTrue(sheet.invigilator_name)
            row = sheets.sheet_row(sheet)
            self.assertEqual((row["examiner_id"], row["invigilator_id"]), (str(self.teacher.id), str(self.center.id)))
            defaults = sheets.latest_sheet_defaults([row])
            self.assertEqual(defaults["invigilator_id"], str(self.center.id))

    def test_roster_exposes_scale_and_pass_rules(self):
        roster = self._roster()
        self.assertEqual(roster["letter_bands"][0][:2], [91, "A"])
        self.assertEqual(roster["letter_bands"][-1][:2], [0, "F"])
        self.assertIn("pass_threshold", roster)
        self.assertIn("min_final_exam_score", roster)
        self.assertIn("failed", roster["rows"][0])
        self.assertIn("barred", roster["rows"][0])

    # Mövcud fixture sinfinin testləri bu modulda təkrar işləməsin.
    for _name in list(vars(fixtures.ExamScoreEntryServiceTest)):
        if _name.startswith("test_"):
            locals()[_name] = None
    del _name


class QuestionMaxCeilingTest(QuestionScoreServiceTest):
    """Sahibin qaydası (2026-09-14): bir sualın maksimumu 10-dan yuxarı ola bilməz."""

    def test_question_max_above_ten_is_rejected(self):
        from django.core.exceptions import ValidationError

        from apps.registrar import exam_score_questions as q

        with self.assertRaises(ValidationError):
            q.clean_question_grid("5", "11")
        self.assertEqual(q.clean_question_grid("5", "10"), (5, 10))
        self.assertEqual(q.clean_question_grid("10", "5"), (10, 5))
