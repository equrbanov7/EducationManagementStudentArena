"""Sərbəst iş BAL modeli — sorğu büdcələri keçiddən əvvəlki səviyyədə qalır.

``BASELINE`` keçiddən ƏVVƏLKİ kod üzərində (2026-09-25) bu faylın özü ilə
ölçülüb (eyni fikstura — :mod:`selfwork_points_fixture`).  Keçiddən sonra hər
səth ən çox həmin sayda sorğu edə bilər: sərbəst iş cəmi hələ də TƏK aqreqat
sorğudur, lövhə sətir sayından asılı deyil, sillabus strukturu yalnız lazım
olanda (mövzu yoxdursa / köhnə mövzular) oxunur.

Üç vəziyyət ölçülür:

* ``plain`` — sillabus yoxdur (köhnə çeklist jurnalı);
* ``legacy_syllabus`` — köhnə (qiymətli) çeklist mövzuları + təsdiqlənmiş 2×5
  sillabus (yeni kodda «struktur uyğunsuzluğu» zolağı);
* ``fresh_syllabus`` — mövzusuz açılış + təsdiqlənmiş 2×5 sillabus.
"""

from __future__ import annotations

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.registrar import analytics, finals, journal_extras
from apps.registrar.models import Enrollment
from apps.registrar.tests.selfwork_points_fixture import SelfWorkLegacyFixture, approve_syllabus
from core.rls import bypass_rls

#: Keçiddən ƏVVƏL (köhnə kod, 2026-09-25) bu faylın özü ilə ölçülmüş sorğu sayları.
BASELINE = {
    "plain": {
        "board": 4,
        "journal_selfwork_tab": 64,
        "journal_final_tab": 93,
        "offering_results": 14,
        "period_analytics": 12,
        "academic_summary": 12,
        "student_journal_detail": 38,
        "student_subjects": 46,
    },
    "legacy_syllabus": {"board": 4, "journal_selfwork_tab": 68, "student_journal_detail": 38},
    "fresh_syllabus": {"board": 4, "journal_selfwork_tab": 67, "student_journal_detail": 37},
}

#: Lövhə qurucusu TƏK BAŞINA (memo-suz) çağırılanda sillabus strukturu yalnız mövzu yoxdursa /
#: köhnə mövzular varsa oxunur: dosye (1) + ``self`` bölməsi (1). Jurnal səhifəsində dosye
#: per-request memo-dadır, bölmələr versiya obyektinə PREFETCH olunur və jurnalın mövzu
#: mənbəyi eyni keşdən oxuyur — ona görə ``journal_selfwork_tab`` baseline-dən AŞAĞIDIR.
BOARD_SYLLABUS_ALLOWANCE = 2


class SelfWorkQueryBudgetTest(SelfWorkLegacyFixture, TestCase):
    def _count(self, func):
        with CaptureQueriesContext(connection) as ctx:
            func()
        return len(ctx.captured_queries)

    def _tab(self, offering, tab):
        client = self._client(self.teacher)
        url = reverse("registrar:journal_detail", args=[offering.id])
        client.get(f"{url}?jt={tab}")  # isinmə (sessiya/keş)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(f"{url}?jt={tab}")
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def _student_detail(self, enrollment):
        from apps.registrar.public import build_student_journal_context

        request = RequestFactory().get("/", {"subject": str(enrollment.id)})
        request.user = enrollment.student
        with bypass_rls():
            return self._count(lambda: build_student_journal_context(request, organization=self.org))

    def _measure_plain(self) -> dict:
        from apps.accounts import academic_summary
        from apps.accounts.academic_records import _new_acc
        from apps.registrar.public import build_student_subjects_context

        counts = {}
        with bypass_rls():
            counts["board"] = self._count(lambda: journal_extras.get_selfwork_board(self.o1))
            counts["offering_results"] = self._count(lambda: finals.get_offering_results(offering=self.o1))
            counts["period_analytics"] = self._count(
                lambda: analytics.build_period_analytics(organization=self.org, period=self.period)
            )
            qs = Enrollment.objects.filter(organization=self.org, offering__period=self.period)
            counts["academic_summary"] = self._count(
                lambda: academic_summary.accumulate_summary(self.org, qs, _new_acc())
            )
            request = RequestFactory().get("/")
            request.user = self.records["swp_s0"].student
            counts["student_subjects"] = self._count(
                lambda: build_student_subjects_context(request, organization=self.org)
            )
        counts["student_journal_detail"] = self._student_detail(self.e1["swp_s0"])
        counts["journal_selfwork_tab"] = self._tab(self.o1, "serbest")
        counts["journal_final_tab"] = self._tab(self.o1, "yekun")
        return counts

    def _measure_offering(self, offering, enrollment) -> dict:
        with bypass_rls():
            board = self._count(lambda: journal_extras.get_selfwork_board(offering))
        return {
            "board": board,
            "journal_selfwork_tab": self._tab(offering, "serbest"),
            "student_journal_detail": self._student_detail(enrollment),
        }

    def test_query_budgets_do_not_grow(self):
        measured = {"plain": self._measure_plain()}
        with bypass_rls():
            approve_syllabus(self.o1, self.teacher, option="2x5")
        measured["legacy_syllabus"] = self._measure_offering(self.o1, self.e1["swp_s0"])
        offering, enrollments = self._fresh_offering()
        measured["fresh_syllabus"] = self._measure_offering(offering, enrollments["swp_s0"])
        print("\nSWPOINTS_BUDGET", measured)
        for state, counts in measured.items():
            for key, value in counts.items():
                limit = BASELINE[state][key] + (BOARD_SYLLABUS_ALLOWANCE if key == "board" else 0)
                self.assertLessEqual(value, limit, f"{state}/{key}: {value} > {limit}")

    def test_structured_board_reads_no_syllabus(self):
        """Qurulmuş (2 × 5) strukturda lövhə sillabusa baxmır — köhnə 4 sorğu."""
        from apps.registrar import selfwork_structure

        offering, _enrollments = self._fresh_offering()
        with bypass_rls():
            self.assertTrue(selfwork_structure.ensure_structure(offering).applied)
            count = self._count(lambda: journal_extras.get_selfwork_board(offering))
        self.assertEqual(count, BASELINE["fresh_syllabus"]["board"])
        self.assertLessEqual(self._tab(offering, "serbest"), BASELINE["fresh_syllabus"]["journal_selfwork_tab"])
