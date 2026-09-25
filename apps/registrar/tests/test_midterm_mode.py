"""Midterm rejimi (sahibin qərarı 2026-09-25): 2026/2027-dən 3 kollokvium əvəzinə TƏK 20 ballıq midterm.

Keçmiş dövrlər K1–K3 (hər biri 10) formasında qalır — o hissə ``test_journal_rules`` və
``test_kollokvium_window_validation``-da (açıq şəkildə kollokvium dövrü ilə) yoxlanılır.
"""

import datetime
from decimal import Decimal

from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod
from apps.registrar import gradebook, interim_assessment, journal_extras
from apps.registrar import kollokvium_windows as kw
from apps.registrar.models import AssessmentComponent, ComponentKind, ComponentScore, KollokviumWindow
from apps.registrar.tests.test_journal_rules import _setup_offering
from core.constants import AcademicPeriodType
from core.rls import bypass_rls


class InterimModePolicyTest(TestCase):
    """Rejim qərarı: tədris ilinin başlanğıc ili ≥ 2026 → midterm; təşkilat həddi dəyişə bilər."""

    def _period(self, academic_year, start=None):
        return AcademicPeriod(academic_year=academic_year, start_date=start or datetime.date(2026, 9, 15))

    def test_year_boundary(self):
        self.assertEqual(interim_assessment.mode_for_period(self._period("2026/2027")), "midterm")
        self.assertEqual(interim_assessment.mode_for_period(self._period("2027/2028")), "midterm")
        self.assertEqual(interim_assessment.mode_for_period(self._period("2025/2026")), "kollokvium")
        self.assertEqual(interim_assessment.mode_for_period(self._period("2025-2026")), "kollokvium")

    def test_start_date_fallback_when_year_text_missing(self):
        # Yay semestri 2026-07-01 hələ 2025/2026 tədris ilidir; payız 2026-09-15 isə 2026/2027.
        self.assertEqual(interim_assessment.mode_for_period(self._period("", datetime.date(2026, 7, 1))), "kollokvium")
        self.assertEqual(interim_assessment.mode_for_period(self._period("", datetime.date(2026, 9, 15))), "midterm")

    def test_organization_override(self):
        class _Org:
            settings = {"registrar": {"midterm_from_year": 2027}}

        self.assertEqual(interim_assessment.mode_for_period(self._period("2026/2027"), _Org()), "kollokvium")
        self.assertEqual(interim_assessment.mode_for_period(self._period("2027/2028"), _Org()), "midterm")

    def test_specs(self):
        midterm = interim_assessment.spec_for_mode("midterm")
        self.assertEqual((midterm.count, midterm.max_score, midterm.component_names), (1, 20, ("Midterm",)))
        self.assertEqual(midterm.label_for(0), "Midterm")
        koll = interim_assessment.spec_for_mode("kollokvium")
        self.assertEqual((koll.count, koll.max_score, koll.total_max), (3, 10, 30))
        self.assertEqual([koll.label_for(i) for i in range(3)], ["K1", "K2", "K3"])


class MidtermComponentsTest(TestCase):
    """2026/2027 dövrü (``_setup_offering`` defoltu) — jurnalda tək Midterm (0–20)."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "mtm")

    def test_single_midterm_created_idempotent(self):
        with bypass_rls():
            first = journal_extras.ensure_kollokviums(self.offering)
            second = journal_extras.ensure_kollokviums(self.offering)
        self.assertEqual([c.name for c in first], ["Midterm"])
        self.assertEqual(first[0].max_score, 20)
        self.assertEqual(first[0].kind, ComponentKind.KOLLOKVIUM)
        self.assertEqual([c.id for c in first], [c.id for c in second])

    def test_unscored_leftover_kollokviums_are_removed(self):
        with bypass_rls():
            for i in range(1, 4):
                AssessmentComponent.objects.create(
                    organization=self.org,
                    offering=self.offering,
                    name=f"Kollokvium {i}",
                    kind=ComponentKind.KOLLOKVIUM,
                    max_score=10,
                    order=i,
                )
            comps = journal_extras.ensure_kollokviums(self.offering)
            names = list(
                AssessmentComponent.objects.filter(offering=self.offering, kind=ComponentKind.KOLLOKVIUM).values_list(
                    "name", flat=True
                )
            )
        self.assertEqual([c.name for c in comps], ["Midterm"])
        self.assertEqual(names, ["Midterm"])

    def test_scored_leftover_is_kept_read_only(self):
        with bypass_rls():
            k1 = AssessmentComponent.objects.create(
                organization=self.org,
                offering=self.offering,
                name="Kollokvium 1",
                kind=ComponentKind.KOLLOKVIUM,
                max_score=10,
                order=1,
            )
            ComponentScore.objects.create(
                organization=self.org, component=k1, enrollment=self.enrollment, score=Decimal("7")
            )
            grid = journal_extras.get_kollokvium_grid(self.offering)
        self.assertEqual([c.name for c in grid["components"]], ["Midterm", "Kollokvium 1"])
        leftover = grid["columns"][1]
        self.assertFalse(leftover["is_primary"])
        self.assertEqual(leftover["status"], "archived")
        self.assertFalse(leftover["open"])
        self.assertTrue(grid["show_total"])

    def test_midterm_score_is_capped_at_20(self):
        with bypass_rls():
            midterm = journal_extras.ensure_kollokviums(self.offering)[0]
            gradebook.save_component_scores(
                offering=self.offering,
                entries=[{"component_id": midterm.id, "enrollment_id": self.enrollment.id, "score": "25"}],
                by_user=self.teacher,
                bypass_edit_window=True,
            )
            score = ComponentScore.objects.get(component=midterm, enrollment=self.enrollment).score
            entry = gradebook.entry_score_for(self.enrollment, 50)
        self.assertEqual(score, Decimal("20"))
        # Midterm giriş balına düşür (0–20 hissə).  2026-09-25 sillabus standartı (entry_standard):
        # bu dövrdə giriş balı = davamiyyət 10 (qayıb yoxdur) + aktivlik 0 + midterm 20 + sərbəst iş 0.
        self.assertEqual(entry, Decimal("30"))

    def test_score_options_and_grid_spec(self):
        with bypass_rls():
            grid = journal_extras.get_kollokvium_grid(self.offering)
            options = journal_extras.interim_score_options(self.offering)
        self.assertEqual(options, list(range(0, 21)))
        self.assertTrue(grid["spec"].is_midterm)
        self.assertEqual([col["label"] for col in grid["columns"]], ["Midterm"])
        self.assertFalse(grid["show_total"])  # tək sütunda «CƏMİ» göstərilmir

    def test_final_breakdown_uses_midterm(self):
        with bypass_rls():
            midterm = journal_extras.ensure_kollokviums(self.offering)[0]
            ComponentScore.objects.create(
                organization=self.org, component=midterm, enrollment=self.enrollment, score=Decimal("16")
            )
            breakdown = journal_extras.get_final_breakdown(self.offering)
        self.assertTrue(breakdown["interim"].is_midterm)
        self.assertEqual([c.name for c in breakdown["kolls"]], ["Midterm"])
        self.assertEqual(breakdown["rows"][0]["kvals"], [Decimal("16")])

    def test_student_journal_detail_shows_midterm(self):
        from apps.registrar import public

        with bypass_rls():
            midterm = journal_extras.ensure_kollokviums(self.offering)[0]
            ComponentScore.objects.create(
                organization=self.org, component=midterm, enrollment=self.enrollment, score=Decimal("18")
            )
            request = RequestFactory().get("/accounts/profile/", {"subject": str(self.enrollment.id)})
            request.user = self.student
            ctx = public.build_student_journal_context(request, organization=self.org)
        detail = ctx["journal_student_section"]["detail"]
        self.assertTrue(detail["interim"].is_midterm)
        self.assertEqual([(k["label"], k["score"]) for k in detail["kollokviums"]], [("Midterm", Decimal("18"))])


class MidtermWindowRuleTest(TestCase):
    """İmtahan Mərkəzi pəncərəsi: midterm dövründə yalnız ``k_index=0``."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "mtw")

    def test_only_first_window_allowed_in_midterm_period(self):
        today = timezone.localdate()
        kwargs = {
            "organization": self.org,
            "period": self.period,
            "opens_on": today,
            "closes_on": today + datetime.timedelta(days=7),
            "is_new": True,
            "today": today,
        }
        with bypass_rls():
            kw.validate_window_save(k_index=0, **kwargs)  # istisna yoxdur
            for k_index in (1, 2):
                with self.assertRaises(kw.KollokviumWindowRuleError) as ctx:
                    kw.validate_window_save(k_index=k_index, **kwargs)
                self.assertIn("Midterm", str(ctx.exception))

    def test_kollokvium_period_still_allows_three(self):
        today = timezone.localdate()
        with bypass_rls():
            past = AcademicPeriod.objects.create(
                organization=self.org,
                name="Yaz",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=datetime.date(2026, 2, 1),
                end_date=datetime.date(2026, 6, 30),
            )
            kw.validate_window_save(
                organization=self.org,
                period=past,
                k_index=2,
                opens_on=today,
                closes_on=today + datetime.timedelta(days=7),
                is_new=False,
                today=today,
            )


class MidtermSaveViewTest(TestCase):
    """Müəllim POST-u (`journal_kollokvium_save`): açıq pəncərədə 0–20 yazılır, bağlıda yox."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "mtv")

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _open_window(self, *, active=True):
        today = timezone.localdate()
        with bypass_rls():
            return KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=today - datetime.timedelta(days=1),
                closes_on=today + datetime.timedelta(days=5),
                is_active=active,
            )

    def _post(self, score):
        with bypass_rls():
            midterm = journal_extras.ensure_kollokviums(self.offering)[0]
        url = reverse("registrar:journal_kollokvium_save", args=[self.offering.id])
        response = self._client(self.teacher).post(url, {f"kscore__{midterm.id}__{self.enrollment.id}": score})
        return midterm, response

    def test_open_window_accepts_midterm_score(self):
        self._open_window()
        midterm, response = self._post("18")
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            score = ComponentScore.objects.get(component=midterm, enrollment=self.enrollment).score
        self.assertEqual(score, Decimal("18"))

    def test_inactive_window_blocks_score(self):
        self._open_window(active=False)
        midterm, response = self._post("18")
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.assertFalse(ComponentScore.objects.filter(component=midterm).exists())

    def test_journal_page_renders_midterm_tab_and_scale(self):
        self._open_window()
        url = reverse("registrar:journal_detail", args=[self.offering.id])
        response = self._client(self.teacher).get(url, {"jt": "kollokvium"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Midterm", html)
        self.assertIn('<option value="20"', html)
        self.assertNotIn(">K1<", html)
        self.assertNotIn("/30<", html)


class NormalizeInterimCommandTest(TestCase):
    """`normalize_interim_components`: dry-run heç nə yazmır; --apply idempotentdir; keçmiş dövrə toxunmur."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "mtc")
            for i in range(1, 4):
                AssessmentComponent.objects.create(
                    organization=cls.org,
                    offering=cls.offering,
                    name=f"Kollokvium {i}",
                    kind=ComponentKind.KOLLOKVIUM,
                    max_score=10,
                    order=i,
                )

    def _names(self):
        with bypass_rls():
            return sorted(
                AssessmentComponent.objects.filter(offering=self.offering, kind=ComponentKind.KOLLOKVIUM).values_list(
                    "name", flat=True
                )
            )

    def test_dry_run_then_apply(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("normalize_interim_components", "--organization", self.org.slug, stdout=out)
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertEqual(self._names(), ["Kollokvium 1", "Kollokvium 2", "Kollokvium 3"])

        call_command("normalize_interim_components", "--organization", self.org.slug, "--apply", stdout=StringIO())
        self.assertEqual(self._names(), ["Midterm"])

        again = StringIO()
        call_command("normalize_interim_components", "--organization", self.org.slug, "--apply", stdout=again)
        self.assertIn("dəyişən 0", again.getvalue())


class MidtermLeftoverWindowTest(TestCase):
    """Midterm dövründə qalmış köhnə K2 pəncərəsi Midterm pəncərəsinin saxlanmasını bloklamır."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "mtl")

    def test_leftover_k2_window_does_not_block_midterm(self):
        today = timezone.localdate()
        with bypass_rls():
            KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=1,
                opens_on=today,
                closes_on=today + datetime.timedelta(days=3),
            )
            kw.validate_window_save(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=today + datetime.timedelta(days=1),
                closes_on=today + datetime.timedelta(days=9),
                is_new=True,
                today=today,
            )
