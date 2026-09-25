"""«Sorğu nəticələri» — DB-siz saf məntiq: ikinci dərəcəli gizlətmə, dərc qaydası,
açar sözlər, dövr seçimi, sıralama, paylanma köməkçiləri."""

from __future__ import annotations

import datetime
import uuid

from django.test import SimpleTestCase

from apps.surveys.services.analytics_extra import buckets_for, hide_row, secondary_suppress
from apps.surveys.services.analytics_publish import _publishable
from apps.surveys.services.analytics_text import keyword_frequency, normalize, stem
from apps.surveys.views.results_filters import campaign_label, parse_query, period_options, resolve_period
from apps.surveys.views.results_panel import delta_info
from apps.surveys.views.results_teachers import sort_rows


def _row(teacher, n, department="A", faculty="F"):
    return {"teacher_id": teacher, "teacher_department_id": department, "faculty_id": faculty, "c": n}


class SecondarySuppressTest(SimpleTestCase):
    def test_small_remainder_hides_smallest_visible_rows(self):
        rows = [
            {"label": "x", "n": 10, "suppressed": False, "avg_overall": 8.0},
            {"label": "y", "n": 8, "suppressed": False, "avg_overall": 7.0},
            {"label": "z", "n": 2, "suppressed": True, "avg_overall": None},
        ]
        secondary_suppress(rows, k=3, total_n=20)
        self.assertFalse(rows[0]["suppressed"])
        self.assertTrue(rows[1]["suppressed"])
        self.assertTrue(rows[1]["secondary"])
        self.assertIsNone(rows[1]["avg_overall"])
        self.assertEqual(rows[1]["n"], 8)  # say qalır

    def test_zero_or_large_remainder_and_hidden_total_change_nothing(self):
        for total, rows in (
            (18, [{"label": "x", "n": 10}, {"label": "y", "n": 8}]),
            (30, [{"label": "x", "n": 10}, {"label": "y", "n": 8}, {"label": "z", "n": 12, "suppressed": True}]),
            (None, [{"label": "x", "n": 10}, {"label": "z", "n": 1, "suppressed": True}]),
        ):
            secondary_suppress(rows, k=3, total_n=total)
            self.assertFalse(rows[0].get("suppressed"), (total, rows))

    def test_rows_not_listed_count_as_hidden_remainder(self):
        rows = [{"label": "x", "n": 10}, {"label": "y", "n": 5}]
        secondary_suppress(rows, k=3, total_n=16)  # 1 cavab siyahıda deyil (məs. müəllimsiz)
        self.assertTrue(rows[1]["suppressed"])
        self.assertFalse(rows[0].get("suppressed"))

    def test_hide_row_keeps_count(self):
        row = hide_row({"n": 4, "avg_overall": 5.0, "delta_org_overall": 1.0, "label": "x"}, secondary=True)
        self.assertEqual((row["n"], row["avg_overall"], row["delta_org_overall"]), (4, None, None))


class PublishableTeachersTest(SimpleTestCase):
    def test_department_remainder_hides_smallest_candidate(self):
        rows = [_row(1, 6), _row(2, 3), _row(3, 2), _row(4, 5, department="B")]
        self.assertEqual(_publishable(rows, 3), {1, 4})

    def test_faculty_and_org_levels(self):
        # Kafedra B yalnız kiçik müəllimdən ibarətdir (2) → fakültə qalığı 2 < 3 → C (ən kiçik) dərc olunmur.
        rows = [_row(1, 9), _row(2, 4), _row(3, 1, department="B")]
        self.assertEqual(_publishable(rows, 3), {1})
        # Müəllimsiz cavablar təşkilat qalığıdır.
        rows = [
            _row(1, 9, department="A", faculty="F"),
            _row(2, 7, department="B", faculty="G"),
            _row(None, 1, None, None),
        ]
        self.assertEqual(_publishable(rows, 3), {1})

    def test_clean_org_publishes_every_candidate(self):
        rows = [_row(1, 3), _row(2, 3, department="B"), _row(3, 5, department="C", faculty="G")]
        self.assertEqual(_publishable(rows, 3), {1, 2, 3})


class KeywordTest(SimpleTestCase):
    def test_document_frequency_stems_and_stopwords(self):
        texts = [
            "Kitabxanada Wi-Fi zəifdir və çox yavaşdır",
            "Kitabxana həftə sonu açıq olsun",
            "WI-FI gücləndirilsin",
            "Yeməkxana",
        ]
        words = {item["stem"]: item for item in keyword_frequency(texts)}
        self.assertEqual(words["kitabxana"]["count"], 2)
        self.assertEqual(words["kitabxana"]["word"], "kitabxana")
        self.assertEqual(words["wi-fi"]["count"], 2)
        self.assertNotIn("və", words)
        self.assertNotIn("yeməkxana", words)  # yalnız 1 təklifdə — göstərilmir

    def test_azerbaijani_case_folding_and_conservative_stemming(self):
        self.assertEqual(normalize("İNGİLİS DİLİ"), "ingilis dili")
        self.assertEqual(normalize("KITAB"), "kıtab")
        self.assertEqual(stem("kitabxanada"), "kitabxana")
        self.assertEqual(stem("müəllimlər"), "müəllim")
        self.assertEqual(stem("dərsdə"), "dərsdə")  # kök 5 hərfdən qısadır — kəsilmir


class PeriodTest(SimpleTestCase):
    def setUp(self):
        self.rows = [
            {"id": uuid.uuid4(), "period_name": "Payız", "academic_year": "2026/2027", "effective_status": "open"},
            {"id": uuid.uuid4(), "period_name": "Yaz", "academic_year": "2025/2026", "effective_status": "closed"},
            {"id": uuid.uuid4(), "period_name": "Payız", "academic_year": "2025/2026", "effective_status": "closed"},
        ]

    def test_default_is_latest_closed_campaign_with_previous(self):
        # M-1: açıq kampaniya (rows[0]) nəticə dəstinə düşmür — defolt son BAĞLI kampaniyadır.
        period = resolve_period("", self.rows)
        self.assertEqual(period.campaign_ids, (self.rows[1]["id"],))
        self.assertEqual(period.previous_ids, (self.rows[2]["id"],))
        self.assertFalse(period.live)
        self.assertEqual(period.value, "")

    def test_open_campaign_is_participation_only(self):
        live = resolve_period(str(self.rows[0]["id"]), self.rows)
        self.assertTrue(live.live)
        self.assertEqual(live.campaign_ids, (self.rows[0]["id"],))
        only_open = resolve_period("", self.rows[:1])
        self.assertTrue(only_open.live)
        self.assertEqual(resolve_period("", []).campaign_ids, ())

    def test_year_all_and_explicit_campaign(self):
        year = resolve_period("y:2025/2026", self.rows)
        self.assertEqual(set(year.campaign_ids), {self.rows[1]["id"], self.rows[2]["id"]})
        self.assertEqual(year.previous_ids, ())
        union = resolve_period("all", self.rows)
        self.assertEqual(set(union.campaign_ids), {self.rows[1]["id"], self.rows[2]["id"]})  # açıq kampaniya YOX
        explicit = resolve_period(str(self.rows[1]["id"]), self.rows)
        self.assertEqual((explicit.mode, explicit.previous_ids), ("campaign", (self.rows[2]["id"],)))
        self.assertEqual(resolve_period("garbage", self.rows).mode, "latest")

    def test_options_and_labels(self):
        values = [option["value"] for option in period_options(self.rows)]
        self.assertEqual(values[:3], ["", "all", "y:2025/2026"])
        self.assertEqual(values[-1], str(self.rows[0]["id"]))  # davam edən kampaniya sonda, «yalnız iştirak»
        self.assertEqual(
            campaign_label({"period_name": "2026/2027 Payız", "academic_year": "2026/2027"}), "2026/2027 Payız"
        )

    def test_parse_query_validates_values(self):
        query = parse_query(
            {
                "er_department": "not-a-uuid",
                "er_teacher": "12",
                "er_tab": "nope",
                "er_sort": "-bogus",
                "er_q": "x" * 500,
            },
            self.rows,
        )
        self.assertIsNone(query.filters.department_id)
        self.assertEqual(query.filters.teacher_id, 12)
        self.assertEqual((query.tab, query.sort), ("overview", "-avg_overall"))
        self.assertLessEqual(len(query.filters.text_query), 120)


class HelpersTest(SimpleTestCase):
    def test_sort_rows_keeps_missing_values_last(self):
        rows = [
            {"teacher_name": "b", "avg_overall": None},
            {"teacher_name": "a", "avg_overall": 7.0},
            {"teacher_name": "c", "avg_overall": 9.0},
        ]
        self.assertEqual([row["teacher_name"] for row in sort_rows(rows, "-avg_overall")], ["c", "a", "b"])
        self.assertEqual([row["teacher_name"] for row in sort_rows(rows, "avg_overall")], ["a", "c", "b"])

    def test_buckets_and_delta(self):
        data = buckets_for({1: 1, 4: 2, 5: 1}, "likert5")
        self.assertEqual((data["n"], data["buckets"], data["avg"], data["top2"]), (4, [1, 0, 0, 2, 1], 3.5, 0.75))
        self.assertEqual(buckets_for({10: 2}, "scale10")["buckets"][-1], 2)
        self.assertEqual(delta_info(8.2, 8.0)["direction"], "up")
        self.assertEqual(delta_info(8.0, 8.02)["direction"], "flat")
        self.assertIsNone(delta_info(None, 8.0))
        self.assertTrue(datetime.date.today())


class DisclosureGuardTest(SimpleTestCase):
    """M-1/M-2 köməkçiləri: səbətlər, 5%-lik faiz, qardaş xanalar, iç-içə dövr dəstləri."""

    def test_count_buckets_and_rates(self):
        from apps.surveys.services.analytics_guard import count_bucket, count_floor, round5

        self.assertEqual(
            [count_bucket(n) for n in (0, 4, 5, 9, 10, 19, 20, 99, 100, 149, 150)],
            ["<5", "<5", "5+", "5+", "10+", "10+", "20+", "50+", "100+", "100+", "150+"],
        )
        self.assertEqual((count_floor(None), count_bucket(None)), (None, "—"))
        self.assertEqual((round5(0.43), round5(0.476), round5(None)), (45, 50, None))

    def test_sibling_rule_needs_two_hidden_cells_and_k_hidden_responses(self):
        from apps.surveys.services.analytics_guard import finalize

        # PoC: 4 / 4 / 1 — tək gizli xana → daha bir xana gizlənir; gizli xanada n də yoxdur.
        rows = [{"label": "a", "n": 4}, {"label": "b", "n": 4}, {"label": "c", "n": 1, "suppressed": True}]
        finalize(rows, k=3, total_n=9)
        self.assertEqual([row.get("suppressed", False) for row in rows], [True, False, True])
        self.assertEqual([row["n"] for row in rows], [None, 4, None])
        # İki gizli xana, amma cəmi < k → üçüncü də gizlənir.
        rows = [
            {"label": "a", "n": 9},
            {"label": "b", "n": 5},
            {"label": "c", "n": 1, "suppressed": True},
            {"label": "d", "n": 1, "suppressed": True},
        ]
        finalize(rows, k=3, total_n=16)
        self.assertEqual([row.get("suppressed", False) for row in rows], [False, True, True, True])

    def test_nested_campaign_sets(self):
        import uuid as _uuid

        from apps.surveys.services.analytics_guard import campaign_family, nested_ok

        c1, c2, c3 = (_uuid.uuid4() for _ in range(3))
        rows = [
            {"id": c1, "academic_year": "2026/2027", "effective_status": "closed", "min_group_size": 3},
            {"id": c2, "academic_year": "2026/2027", "effective_status": "closed", "min_group_size": 3},
            {"id": c3, "academic_year": "2025/2026", "effective_status": "closed", "min_group_size": 3},
            {"id": _uuid.uuid4(), "academic_year": "2026/2027", "effective_status": "open", "min_group_size": 3},
        ]
        family = campaign_family(rows)
        self.assertEqual(len(family.sets), 5)  # 3 tək + 1 il + hamısı (açıq kampaniya yox)
        everything = (c1, c2, c3)
        self.assertTrue(nested_ok((c1,), {c1: 5}, family, 3))  # tək kampaniyanın öz alt-dəsti yoxdur
        self.assertTrue(nested_ok(everything, {c1: 10, c2: 10, c3: 5}, family, 3))
        self.assertFalse(nested_ok(everything, {c1: 10, c2: 10, c3: 1}, family, 3))  # tək gizli kampaniya
        self.assertFalse(nested_ok((c1, c2), {c1: 10, c2: 2}, family, 3))  # il − c1 = 2 < k
        self.assertFalse(nested_ok(everything, {c1: 10, c2: 1, c3: 2}, family, 3))  # hamısı − il = 2 < k
