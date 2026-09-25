"""Sərbəst iş BAL modelinə keçid — KÖHNƏ (çeklist) data üzrə rəqəm pariteti.

Sahib 2026-09-25: sərbəst iş sillabus strukturuna (1×10 / 2×5 / 10×1) keçir və
real bal daşıyır.  Bu keçid hər tələbənin giriş balının hesablanma yolunu
dəyişir, ona görə KÖHNƏ datada (``max_points=1``, ``points=NULL``) BÜTÜN sayma
yerlərinin rəqəmi BAYT-BAYT EYNİ qalmalıdır.

Bu fayl QƏSDƏN yalnız keçiddən ƏVVƏL mövcud olan sahələrlə/API-lərlə yazılıb:
eyni fayl köhnə kod üzərində də işlədilib (2026-09-25, keçiddən əvvəl) və
aşağıdakı ``EXPECTED`` snapshot-u həmin qaçışın nəticəsidir — yəni test
«əvvəl ↔ sonra» bərabərliyini kilidləyir.

Fikstura bütün sayma yerlərinin qollarını əhatə edir:

* O1 — dərs cəmi rejimi: 10 mövzu (``add_selfwork_topic``), 7 / 3 (+ geri
  alınmış işarə, ``done=False`` sətri) / 0 / 10 təhvil, seminar + kollokvium;
* O2 — generic komponent rejimi + QEYRİ-STANDART SELF_WORK komponenti
  (``max_score=5``), 12 mövzu (10-luq tavan yan keçilib), 11 təhvil (10 bal
  tavanı), YALNIZ 11-12-ci mövzularda təhvil (lövhənin 10 slotundan kənar) və
  köçürülmüş «arxiv» balı (``ComponentScore``, giriş balına ƏLAVƏ OLUNMUR).

⚠️ O2-də iki yol arasında ƏVVƏLDƏN mövcud olan fərq qəsdən sənədləşdirilir
(``entry_score_for`` SELF_WORK komponentinin öz tavanı ilə, ``analytics``
güzgüsü isə 10 ilə kəsir): keçid bu fərqi nə yaradır, nə də «düzəldir» — rəqəm
dəyişmir.  Birləşdirmə ayrıca qərardır (bax brif hesabatı).
"""

from __future__ import annotations

from decimal import Decimal

from django.test import RequestFactory, TestCase

from apps.registrar import analytics, analytics_fast, finals, finals_batch, gradebook, journal_extras
from apps.registrar import transcript as transcript_service
from apps.registrar.models import Enrollment
from apps.registrar.tests.selfwork_points_fixture import STUDENTS, SelfWorkLegacyFixture
from core.rls import bypass_rls

#: Keçiddən ƏVVƏLKİ kod üzərində ölçülmüş rəqəmlər (bax modul docstring-i).
EXPECTED = {
    # gradebook.entry_score_for (tək sətir) — (O1, O2)
    "entry_single": {
        "swp_s0": ("33", "30"),
        "swp_s1": ("12", "16"),
        "swp_s2": ("9", "7"),
        "swp_s3": ("40", "20"),
    },
    # analytics._selfwork_map (hər yazılış üçün; açarı olmayan = yox)
    "analytics_selfwork": {
        "swp_s0": ("7", "10"),
        "swp_s1": ("3", "4"),
        "swp_s2": (None, "2"),
        "swp_s3": ("10", None),
    },
    # analytics.evaluate_enrollment → total (güzgü; O2/s0-da 35 ≠ 30 — köhnə fərq)
    "analytics_total": {
        "swp_s0": ("73", "65"),
        "swp_s1": ("32", "51"),
        "swp_s2": ("9", "7"),
        "swp_s3": ("85", "20"),
    },
    # finals.compute_final_result → total (kanonik)
    "final_total": {
        "swp_s0": ("73", "60"),
        "swp_s1": ("32", "51"),
        "swp_s2": ("9", "7"),
        "swp_s3": ("85", "20"),
    },
    # Dövr analitikası: (graded, passed, failed, avg_total)
    "period_totals": (5, 4, 1, Decimal("61.20")),
    # Akademik-qeyd xülasəsi: (credits_earned, fails, ungraded, quality_points, gpa_credits)
    "academic_summary": (22, 1, 3, Decimal("1720"), 28),
    # Sərbəst iş lövhəsi: (checklist_total, archive_score, total)
    "board": {
        "swp_s0": ((7, None, 7), (10, None, 10)),
        "swp_s1": ((3, None, 3), (4, None, 4)),
        "swp_s2": ((0, None, 0), (0, None, 0)),
        "swp_s3": ((10, None, 10), (0, 7, 7)),
    },
}


def _dec(value):
    """Rəqəmin kanonik mətni (``Decimal("30.00")`` → ``"30"``, ``7.5`` → ``"7.5"``)."""
    if value is None:
        return None
    return format(Decimal(value).normalize(), "f")


class SelfWorkLegacyParityTest(SelfWorkLegacyFixture, TestCase):
    """Köhnə çeklist datası — bütün sayma yerləri keçiddən əvvəlki rəqəmləri verir."""

    # ── 1. kanonik giriş balı: tək sətir == toplu dəst == snapshot ─────────
    def test_entry_score_single_and_batch_match_snapshot(self):
        with bypass_rls():
            enrollments = self._all_enrollments()
            batch = finals_batch.entry_batch(enrollments)
            for username, e1, e2 in self._pairs():
                single = tuple(_dec(gradebook.entry_score_for(e, 50)) for e in (e1, e2))
                batched = tuple(_dec(gradebook.entry_score_for(e, 50, **batch.entry_kwargs(e))) for e in (e1, e2))
                self.assertEqual(single, EXPECTED["entry_single"][username], username)
                self.assertEqual(batched, single, f"toplu ↔ tək: {username}")

    # ── 2. analitika güzgüsü (yavaş + sürətli + akademik xülasə) ───────────
    def test_analytics_selfwork_maps_match_snapshot(self):
        from apps.accounts import academic_summary

        with bypass_rls():
            ids = [e.id for e in self._all_enrollments()]
            slow = analytics._selfwork_map(ids)
            ids_qs = Enrollment.objects.filter(pk__in=ids).values("id")
            fast = analytics_fast._selfwork_map(ids_qs)
            summary = academic_summary._selfwork_map(ids_qs)
            text_key = {
                str(pk): key
                for pk, key in Enrollment.objects.filter(pk__in=ids)
                .annotate(k=analytics_fast._text("id"))
                .values_list("id", "k")
            }
        for username, e1, e2 in self._pairs():
            got = tuple(_dec(slow.get(e.id)) if e.id in slow else None for e in (e1, e2))
            self.assertEqual(got, EXPECTED["analytics_selfwork"][username], username)
            for mirror in (fast, summary):
                mirrored = tuple(
                    _dec(mirror[text_key[str(e.id)]]) if text_key[str(e.id)] in mirror else None for e in (e1, e2)
                )
                self.assertEqual(mirrored, got, f"sürətli güzgü fərqlidir: {username}")

    def test_analytics_totals_match_snapshot(self):
        with bypass_rls():
            enrollments = list(
                Enrollment.objects.filter(pk__in=[e.id for e in self._all_enrollments()]).select_related(
                    "offering", "offering__subject"
                )
            )
            maps = analytics.build_evaluation_maps(self.org, enrollments)
            by_id = {e.id: analytics.evaluate_enrollment(e, maps) for e in enrollments}
        for username, e1, e2 in self._pairs():
            got = tuple(_dec(by_id[e.id]["total"]) for e in (e1, e2))
            self.assertEqual(got, EXPECTED["analytics_total"][username], username)

    def test_period_analytics_fast_path_matches_slow_path(self):
        from apps.registrar.tests.test_analytics_fast_path import _legacy_period_analytics

        with bypass_rls():
            fast = analytics.build_period_analytics(organization=self.org, period=self.period)
            slow = _legacy_period_analytics(self.org, self.period)
        for key in ("totals", "programs", "groups", "at_risk"):
            self.assertEqual(fast[key], slow[key], key)
        totals = fast["totals"]
        # Qiymətləndirilmiş 5 yazılış: 73, 32, 85 (O1) + 65, 51 (O2, analitika güzgüsü).
        self.assertEqual(
            (totals["graded"], totals["passed"], totals["failed"], totals["avg_total"]),
            EXPECTED["period_totals"],
        )

    def test_academic_summary_fast_path_matches_slow_accumulator(self):
        from apps.accounts import academic_records, academic_summary

        with bypass_rls():
            qs = Enrollment.objects.filter(organization=self.org, offering__period=self.period)
            fast = academic_records._new_acc()
            academic_summary.accumulate_summary(self.org, qs, fast)
            slow = academic_records._new_acc()
            for _enrollment, result in academic_records._evaluate_all(self.org, qs):
                academic_records._accumulate(slow, result)
        self.assertEqual(fast, slow)
        self.assertEqual(
            (fast["credits_earned"], fast["fails"], fast["ungraded"], fast["quality_points"], fast["gpa_credits"]),
            EXPECTED["academic_summary"],
        )

    # ── 3. yekun nəticə (tək + toplu) ──────────────────────────────────────
    def test_final_results_match_snapshot(self):
        with bypass_rls():
            batch = finals_batch.build(self._all_enrollments())
            for username, e1, e2 in self._pairs():
                single = tuple(_dec(finals.compute_final_result(enrollment=e)["total"]) for e in (e1, e2))
                batched = tuple(
                    _dec(finals.compute_final_result(enrollment=e, batch=batch)["total"]) for e in (e1, e2)
                )
                self.assertEqual(single, EXPECTED["final_total"][username], username)
                self.assertEqual(batched, single, username)
            rows = {r["student"].username: r["result"] for r in finals.get_offering_results(offering=self.o2)["rows"]}
        self.assertEqual(_dec(rows["swp_s0"]["entry_score"]), "30")

    # ── 4. lövhə + «Yekun» tab sütunu ──────────────────────────────────────
    def test_board_rows_match_snapshot(self):
        with bypass_rls():
            boards = [journal_extras.get_selfwork_board(o) for o in (self.o1, self.o2)]
        for index, board in enumerate(boards):
            rows = {r["student"].username: r for r in board["rows"]}
            for username in STUDENTS:
                row = rows[username]
                self.assertEqual(
                    (row["checklist_total"], row["archive_score"], row["total"]),
                    EXPECTED["board"][username][index],
                    f"O{index + 1}/{username}",
                )
        self.assertTrue(boards[1]["has_archive"])
        self.assertFalse(boards[0]["has_archive"])

    def test_final_breakdown_selfwork_and_entry_columns(self):
        with bypass_rls():
            b1 = {r["student"].username: r for r in journal_extras.get_final_breakdown(self.o1)["rows"]}
            b2 = {r["student"].username: r for r in journal_extras.get_final_breakdown(self.o2)["rows"]}
        for username in STUDENTS:
            self.assertEqual(b1[username]["selfwork"], EXPECTED["board"][username][0][2])
            self.assertEqual(b2[username]["selfwork"], EXPECTED["board"][username][1][2])
            self.assertEqual(
                (_dec(b1[username]["entry"]), _dec(b2[username]["entry"])), EXPECTED["entry_single"][username]
            )

    # ── 5. jurnal qridi + tələbə səthləri + transkript ─────────────────────
    def test_journal_grid_and_student_surfaces(self):
        with bypass_rls():
            grid = gradebook.get_offering_journal(offering=self.o1)
            grid_entry = {r["student"].username: _dec(r["entry_score"]) for r in grid["rows"]}
            summary = gradebook.get_student_journal_summary(
                record=self.records["swp_s0"], period=self.period, semester_number=1
            )
            cabinet = {row["enrollment"].offering_id: _dec(row["journal"]["entry_score"]) for row in summary["subjects"]}
            data = transcript_service.build_student_transcript(
                student=self.records["swp_s1"].student, organization=self.org
            )
            transcript_totals = {
                row["enrollment"].offering_id: _dec(row["result"]["total"])
                for semester in data["semesters"]
                for row in semester["rows"]
            }
        self.assertEqual(grid_entry, {u: EXPECTED["entry_single"][u][0] for u in STUDENTS})
        self.assertEqual(cabinet, {self.o1.id: "33", self.o2.id: "30"})
        self.assertEqual(transcript_totals, {self.o1.id: "32", self.o2.id: "51"})

    def test_student_journal_detail_parts(self):
        from apps.registrar.public import build_student_journal_context

        request = RequestFactory().get("/", {"subject": str(self.e1["swp_s0"].id)})
        request.user = self.records["swp_s0"].student
        with bypass_rls():
            ctx = build_student_journal_context(request, organization=self.org)
        detail = ctx["journal_student_section"]["detail"]
        self.assertEqual(_dec(detail["entry_score"]), "33")
        self.assertEqual(detail["parts"]["selfwork"], 7)
        self.assertEqual(_dec(detail["parts"]["lesson_sum"]), "18")
        self.assertEqual(detail["selfwork_row"]["total"], 7)

        request = RequestFactory().get("/", {"subject": str(self.e2["swp_s3"].id)})
        request.user = self.records["swp_s3"].student
        with bypass_rls():
            ctx = build_student_journal_context(request, organization=self.org)
        detail = ctx["journal_student_section"]["detail"]
        # Arxiv balı: CƏMİ-də görünür, giriş balına daxil DEYİL (qalıq 20 − 0 − 7 → 13).
        self.assertEqual(_dec(detail["entry_score"]), "20")
        self.assertEqual(detail["parts"]["selfwork"], 7)
        self.assertEqual(_dec(detail["parts"]["lesson_sum"]), "13")
