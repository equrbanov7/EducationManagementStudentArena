"""«Sorğu nəticələri» — təhlükəsizlik rəyinin PoC-ları (M-1, M-2) F2 GÖRÜNÜŞLƏRİNƏ qarşı.

Rəyçinin ``secreview/poc/test_poc_surveys.py`` ssenariləri F1 xam API-si əvəzinə
istifadəçinin HƏQİQƏTƏN gördüyü səthlərə (kabinet bölməsi, müəllim kartı, ixrac) tətbiq
olunur və hücumun artıq alınmadığı yoxlanılır. ``pytest -s`` ilə «PoC» sətirləri
düzəlişdən sonrakı rəqəmləri çap edir.
"""

from __future__ import annotations

import csv
import io
import json
import re

from django.test import TestCase
from django.urls import reverse

from apps.registrar.models import CourseOffering, Enrollment
from apps.surveys.forms import validate_answers
from apps.surveys.services.submit import submit_target
from apps.surveys.services.targets import student_targets
from apps.surveys.services.templates import template_questions
from core.rls import bypass_rls

from .factories import build_world, client_for, close_all, close_journal, likert_payload, member, open_campaign
from .results_world import add_responses, build_results_world, close_campaign

SECTION = "/accounts/profile/?section=evaluation-results"
_AVG_RE = re.compile(r"\b\d+,\d{2}\b")


def _cleaned(template, *, score, overall):
    questions = template_questions(template, section="teacher")
    cleaned, errors, _values = validate_answers(questions, likert_payload(questions, score=score, overall=overall))
    assert not errors, errors
    return cleaned


def _island(html, island_id):
    match = re.search(r'<script id="%s" type="application/json">(.*?)</script>' % re.escape(island_id), html, re.S)
    return json.loads(match.group(1)) if match else None


def _panel(html):
    start = html.index('data-profile-section-panel="evaluation-results"')
    return html[start : html.index("</section>", start)]


class LiveResultsPoCTest(TestCase):
    """M-1: açıq kampaniyada iki yükləmə arasındakı fərqdən bir tələbənin cavabı hesablanmır."""

    @classmethod
    def setUpTestData(cls):
        w = cls.w = build_world("svpl", students=6)
        close_all(w)
        cls.campaign = open_campaign(w, grace_until=None)
        with bypass_rls():
            cls.chair_b = member(w["org"], "svpl_chb", "chair_head", unit=w["chair_b"])
            for student in w["students"][:5]:
                for target in student_targets(cls.campaign, student):
                    if not target.is_general:
                        cleaned = _cleaned(cls.campaign.template, score=5, overall=8)
                        submit_target(campaign=cls.campaign, student=student, target=target, cleaned_answers=cleaned)

    def _panel_html(self, client):
        response = client.get(SECTION)
        self.assertEqual(response.status_code, 200)
        return _panel(response.content.decode())

    def test_live_panel_shows_no_averages_before_or_after_a_submission(self):
        viewer = client_for(self.w["org"], self.chair_b)
        before = self._panel_html(viewer)
        victim = self.w["students"][5]
        with bypass_rls():
            target = next(t for t in student_targets(self.campaign, victim) if t.teacher_id == self.w["teacher_b"].pk)
        questions = template_questions(self.campaign.template, section="teacher")
        url = reverse("surveys:teacher", args=[self.campaign.pk, target.offering_id, target.teacher_id])
        self.assertEqual(
            client_for(self.w["org"], victim).post(url, likert_payload(questions, score=1, overall=2)).status_code, 302
        )
        after = self._panel_html(viewer)
        for html in (before, after):
            self.assertIn("Kampaniya davam edir", html)
            self.assertIsNone(_island(html, "svr-overview-data"))
            self.assertEqual(_AVG_RE.findall(html), [])  # heç bir 2 onluq rəqəmli orta yoxdur
            self.assertNotIn(">6<", html)
        print("\n[PoC M-1 after fix] live panel: averages=none, n=none → n2·avg2 − n1·avg1 not computable")
        drawer = viewer.get(reverse("surveys:results_teacher", args=[self.w["teacher_b"].pk]))
        self.assertEqual(drawer.status_code, 409)
        export = viewer.get(reverse("surveys:results_export", args=["xlsx"]))
        self.assertEqual(export.status_code, 409)

    def test_closed_campaign_shows_results_with_bucketed_counts_only(self):
        close_campaign(self.campaign)
        html = self._panel_html(client_for(self.w["org"], self.chair_b))
        data = _island(html, "svr-overview-data")
        self.assertIsNotNone(data)
        self.assertIn("5+", html)  # 5 cavab → «5+», dəqiq say heç yerdə yoxdur
        self.assertNotRegex(html, r'ems-kpi__value">\s*5\s*<')
        print("[PoC M-1 after fix] closed panel: n shown as '5+' (true 5), averages shown only after closing")


class CellSubtractionPoCTest(TestCase):
    """M-2: müəllim B — qruplar 4 / 4 / 1; tək tələbəli xana çıxma ilə bərpa olunmur."""

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import OrgUnit
        from core.constants import OrgUnitType

        w = cls.w = build_world("svpb", students=4)
        with bypass_rls():
            groups = {
                name: OrgUnit.objects.create(
                    organization=w["org"],
                    name=name,
                    slug=f"svpb-{name.lower()}",
                    unit_type=OrgUnitType.GROUP,
                    parent=w["chair_b"],
                )
                for name in ("G-LONE", "G-THREE")
            }
            offerings = {
                name: CourseOffering.objects.create(
                    organization=w["org"], subject=w["phys"], period=w["period"], group=group, instructor=w["teacher_b"]
                )
                for name, group in groups.items()
            }
            cls.lonely = member(w["org"], "svpb_lonely", "student")
            Enrollment.objects.create(organization=w["org"], student=cls.lonely, offering=offerings["G-LONE"])
            others = []
            for index in range(4):
                student = member(w["org"], f"svpb_g3_{index}", "student")
                Enrollment.objects.create(organization=w["org"], student=student, offering=offerings["G-THREE"])
                others.append(student)
            for offering in (w["off_math"], w["off_phys"], *offerings.values()):
                close_journal(w["org"], offering)
            cls.campaign = open_campaign(w)
            for student in w["students"] + others + [cls.lonely]:
                for target in student_targets(cls.campaign, student):
                    if target.is_general or target.teacher_id != w["teacher_b"].pk:
                        continue
                    overall, score = (3, 2) if student == cls.lonely else (8, 5)
                    cleaned = _cleaned(cls.campaign.template, score=score, overall=overall)
                    submit_target(campaign=cls.campaign, student=student, target=target, cleaned_answers=cleaned)
            cls.qc = member(w["org"], "svpb_qc", "quality_control_staff")
        close_campaign(cls.campaign)

    def test_teacher_card_never_leaves_a_single_hidden_cell(self):
        client = client_for(self.w["org"], self.qc)
        html = client.get(reverse("surveys:results_teacher", args=[self.w["teacher_b"].pk])).content.decode()
        table = html[html.index('id="svr-of-title"') :]
        table = table[: table.index("</table>")]
        rows = re.findall(r"<tr>\s*<th scope=\"row\">(.*?)</th>\s*<td>(.*?)</td>(.*?)</tr>", table, re.S)
        visible = [(group, cells) for _subject, group, cells in rows if "svr-hidden" not in cells]
        hidden = [(group, cells) for _subject, group, cells in rows if "svr-hidden" in cells]
        self.assertEqual(len(rows), 3)
        self.assertGreaterEqual(len(hidden), 2)  # tək gizli xana qalmır (qardaş qaydası)
        for _group, cells in hidden:
            self.assertNotRegex(cells, r'ems-table__num">\s*\d')  # gizli xanada heç bir rəqəm, n də yox
        self.assertIn("5+ cavab", html)  # müəllimin cəmi 9 → «5+»
        # Hücumçu dəqiq cəmi (9) bilsə belə: 9·orta − görünən xana(lar) = GİZLİ 5 CAVABIN ortası.
        true_total, visible_cell = 9 * (8 * 8 + 3) / 9, 4 * 8
        recovered = (true_total - visible_cell) / 5
        print(
            f"\n[PoC M-2 after fix] cells visible={len(visible)} hidden={len(hidden)}; "
            f"best recovery = mean of 5 hidden answers = {recovered:.2f} (lonely student's 3 not recoverable)"
        )
        self.assertNotAlmostEqual(recovered, 3.0, places=1)

    def test_teacher_table_and_export_carry_no_exact_counts(self):
        client = client_for(self.w["org"], self.qc)
        rows = _island(client.get(SECTION + "&er_tab=teachers").content.decode(), "svr-rank-data")
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name[self.w["teacher_b"].username]["n"], 5)  # səbət alt həddi, 9 deyil
        response = client.get(reverse("surveys:results_export", args=["csv"]) + "?dataset=teachers")
        body = response.content.decode("utf-8-sig")
        table = list(csv.reader(io.StringIO(body)))
        n_column = table[0].index("Cavab sayı")
        self.assertEqual({row[n_column] for row in table[1:]} - {"", "<5", "5+"}, set())
        self.assertNotIn("G-LONE", body)


class CampaignNarrowingTest(TestCase):
    """Kampaniya seçimi daraldıcıdır: «bütün dövrlər» − tək kampaniya kiçik qalığı açmır."""

    @classmethod
    def setUpTestData(cls):
        w = cls.w = build_results_world("svcn")
        # Müəllim D: cari kampaniyada 4 cavab, əvvəlkində 1 (tək gizli kampaniya).
        add_responses(
            w,
            w["previous"],
            teacher=w["teacher_d"],
            department=w["chair_d"],
            faculty=w["faculty2"],
            subject=w["chem"],
            group=w["group2"],
            count=1,
            score=1,
            overall=1,
        )

    def _rows(self, period):
        client = client_for(self.w["org"], self.w["rector"])
        html = client.get(SECTION + f"&er_tab=teachers&er_period={period}").content.decode()
        return {row["name"]: row for row in _island(html, "svr-rank-data")}

    def test_union_hides_teacher_whose_other_campaign_is_below_k(self):
        name = self.w["teacher_d"].username
        current = self._rows(str(self.w["campaign"].pk))
        union = self._rows("all")
        self.assertTrue(current[name]["visible"])
        self.assertFalse(union[name]["visible"])  # hər iki görünüş açıq olsaydı: all − cari = 1 cavab
        self.assertIsNone(union[name]["avg_overall"])
        self.assertIsNone(union[name]["n"])
        # Teacher A: əvvəlki kampaniyada 4 cavab (≥ k) — birləşmə göstərilə bilir.
        self.assertTrue(union[self.w["teacher_a"].username]["visible"])


class MixedCampaignsTest(TestCase):
    """Açıq cari kampaniya + bağlı əvvəlki kampaniya: defolt bağlı olandır, açıq olan yalnız iştirak."""

    @classmethod
    def setUpTestData(cls):
        cls.w = build_results_world("svmx", live=True)

    def test_default_is_closed_campaign_and_open_one_is_participation_only(self):
        client = client_for(self.w["org"], self.w["rector"])
        default = _panel(client.get(SECTION).content.decode())
        self.assertIsNotNone(_island(default, "svr-overview-data"))
        self.assertIn(self.w["previous"].period.name, default)
        self.assertIn("davam edir (yalnız iştirak)", default)  # açıq kampaniya seçimdə, ayrıca işarə ilə
        live = _panel(client.get(SECTION + f"&er_period={self.w['campaign'].pk}").content.decode())
        self.assertIsNone(_island(live, "svr-overview-data"))
        self.assertIn("Kampaniya davam edir", live)
        self.assertEqual(_AVG_RE.findall(live), [])
        self.assertRegex(live, r"≈ \d+%")  # yalnız 5-ə yuvarlaq iştirak faizi
