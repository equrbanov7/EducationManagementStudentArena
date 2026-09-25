"""İmtahan Mərkəzi «Midterm pəncərələri» ekranı — semestrin rejiminə görə (sahib 2026-09-25).

Sahibin qərarı: 2026/2027-dən 3 kollokvium əvəzinə TƏK midterm (20 bal); bal yazma
vaxtını İmtahan Mərkəzi təyin edir; keçmiş dövrlərdə K1/K2/K3 olduğu kimi qalır.
Rejimin tək mənbəyi ``apps.registrar.interim_assessment``-dir. Bu fayl kabinet
tərəfinin müqaviləsini kilidləyir:

* midterm semestri → TƏK «Midterm — bal yazma pəncərəsi (0–20 bal)» kartı;
  ``k_index=1/2`` POST-la göndərilsə belə server rədd edir (forma + view);
* keçmiş (kollokvium) semestr → əvvəlki kimi 3 kart, K-sıra qaydası qüvvədədir;
* ``k_index=0`` üçün yadda saxla / aktivləşdir / əlavə gün / sil əvvəlki kimi işləyir;
* midterm semestrində köhnə qaydadan qalmış K2 pəncərəsi ayrıca siyahıda görünür və
  yalnız SİLİNƏ bilər (aktivləşdirmə/əlavə gün rədd edilir).
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from apps.accounts.forms.kollokvium_windows import KollokviumWindowForm
from apps.organizations.models import AcademicPeriod, Membership, Organization
from apps.registrar.models import KollokviumExtraGrant, KollokviumWindow
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()

_CARD = 'class="ems-card kw-card"'


@override_settings(UNIVERSITY_MODE=True)
class _MidtermScreenBase(TestCase):
    """Bir təşkilat, iki redaktə oluna bilən semestr: 2026/2027 (midterm) və 2025/2026 (kollokvium).

    Hər iki semestrin tarix aralığı bu günü əhatə edir ki, ``is_past`` kilidi testlərə
    qarışmasın — rejim yalnız TƏDRİS İLİNDƏN (``academic_year``) çıxır.
    """

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.owner = User.objects.create_user("mws_owner", "mws_owner@qku.edu.az", "pw")
        cls.head = User.objects.create_user("mws_head", "mws_head@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="MWS Univ",
                slug="mws-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.midterm_period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız 2026",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=cls.today - datetime.timedelta(days=30),
                end_date=cls.today + datetime.timedelta(days=150),
                is_current=True,
            )
            cls.kollokvium_period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Yaz 2026",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=cls.today - datetime.timedelta(days=60),
                end_date=cls.today + datetime.timedelta(days=150),
            )
            Membership.objects.create(
                user=cls.head,
                organization=cls.org,
                role=cls.org.roles.get(name="exam_center_head"),
                is_primary=True,
                is_active=True,
            )

    def _client(self):
        client = Client()
        client.force_login(self.head)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _get(self, period):
        return self._client().get(
            reverse("accounts:profile"),
            {"section": "kollokvium-windows", "win_year": period.year_display, "period": str(period.pk)},
        )

    def _post(self, data):
        response = self._client().post(reverse("accounts:kollokvium_windows"), data)
        self.assertEqual(response.status_code, 302)
        return response, [str(m) for m in get_messages(response.wsgi_request)]

    def _save(self, period, k_index, *, opens=1, closes=10):
        return self._post(
            {
                "action": "save_window",
                "period": str(period.pk),
                "k_index": str(k_index),
                "opens_on": (self.today + datetime.timedelta(days=opens)).isoformat(),
                "closes_on": (self.today + datetime.timedelta(days=closes)).isoformat(),
            }
        )

    def _window(self, period, k_index, **extra):
        with bypass_rls():
            return KollokviumWindow.objects.create(
                organization=self.org,
                period=period,
                k_index=k_index,
                opens_on=self.today + datetime.timedelta(days=1),
                closes_on=self.today + datetime.timedelta(days=10),
                **extra,
            )

    def _windows(self, period):
        with bypass_rls():
            return {w.k_index: w for w in KollokviumWindow.objects.filter(organization=self.org, period=period)}


class MidtermScreenRenderTests(_MidtermScreenBase):
    def test_midterm_period_shows_one_midterm_card(self):
        response = self._get(self.midterm_period)
        self.assertEqual(response.status_code, 200)
        section = response.context["kollokvium_windows_section"]
        self.assertTrue(section["interim"].is_midterm)
        self.assertEqual([row["label"] for row in section["k_rows"]], ["Midterm"])
        self.assertEqual(response.content.decode().count(_CARD), 1)
        self.assertContains(response, "Midterm — bal yazma pəncərəsi (0–20 bal)")
        self.assertContains(response, 'name="k_index" value="0"')
        self.assertNotContains(response, 'id="kw-save-1"')
        self.assertNotContains(response, 'id="kw-save-2"')
        # Uyğunlaşdırılmış KPI: say əvəzinə şkala; K-sıra kilidi (əvvəlki kollokvium) yoxdur.
        self.assertContains(response, "Bal şkalası")
        self.assertNotContains(response, "Əvvəlcə əvvəlki kollokvium təyin edilməlidir.")

    def test_kollokvium_period_keeps_three_cards(self):
        response = self._get(self.kollokvium_period)
        self.assertEqual(response.status_code, 200)
        section = response.context["kollokvium_windows_section"]
        self.assertFalse(section["interim"].is_midterm)
        self.assertEqual([row["label"] for row in section["k_rows"]], ["K1", "K2", "K3"])
        self.assertEqual(response.content.decode().count(_CARD), 3)
        self.assertNotContains(response, "bal yazma pəncərəsi (0–20 bal)")
        # K1 təyin olunmayıb → K2/K3 kartında sıra kilidi (köhnə davranış).
        self.assertContains(response, "Əvvəlcə əvvəlki kollokvium təyin edilməlidir.")
        # Niyə «Midterm pəncərələri» altında K1–K3 göründüyünün izahı.
        self.assertContains(response, "Köhnə qayda:")

    def test_section_title_is_midterm_windows(self):
        response = self._get(self.midterm_period)
        self.assertContains(response, "Midterm pəncərələri")

    def test_stale_k2_window_in_midterm_period_is_listed_separately(self):
        stale = self._window(self.midterm_period, 1)
        response = self._get(self.midterm_period)
        section = response.context["kollokvium_windows_section"]
        self.assertEqual([row["window"].pk for row in section["stale_rows"]], [stale.pk])
        self.assertEqual(response.content.decode().count(_CARD), 1)  # kart sayı dəyişmir
        self.assertContains(response, "Köhnə qaydadan qalmış kollokvium pəncərələri")
        self.assertContains(response, f'name="window_id" value="{stale.pk}"')


class MidtermScreenPostTests(_MidtermScreenBase):
    def test_midterm_period_rejects_k_index_1_and_2(self):
        for k_index in (1, 2):
            with self.subTest(k_index=k_index):
                _response, texts = self._save(self.midterm_period, k_index)
                self.assertNotIn(k_index, self._windows(self.midterm_period))
                self.assertTrue(any("midterm" in text.lower() for text in texts), texts)

    def test_midterm_k0_save_toggle_grant_and_delete(self):
        _response, texts = self._save(self.midterm_period, 0)
        window = self._windows(self.midterm_period)[0]
        self.assertFalse(window.is_active)
        self.assertIn("Pəncərə yadda saxlanıldı.", texts)

        self._post({"action": "toggle_window_active", "window_id": str(window.pk)})
        window.refresh_from_db()
        self.assertTrue(window.is_active)

        self._post(
            {"action": "grant_extra_days", "window_id": str(window.pk), "scope": "organization", "extra_days": "3"}
        )
        with bypass_rls():
            grant = KollokviumExtraGrant.objects.get(window=window)
        self.assertEqual(grant.extra_days, 3)

        self._post({"action": "edit_extra_days", "grant_id": str(grant.pk), "scope": "organization", "extra_days": "5"})
        grant.refresh_from_db()
        self.assertEqual(grant.extra_days, 5)

        self._post({"action": "delete_extra_days", "grant_id": str(grant.pk)})
        with bypass_rls():
            self.assertFalse(KollokviumExtraGrant.objects.filter(pk=grant.pk).exists())

        self._post({"action": "delete_window", "window_id": str(window.pk)})
        self.assertEqual(self._windows(self.midterm_period), {})

    def test_kollokvium_period_keeps_k_order_rule(self):
        _response, texts = self._save(self.kollokvium_period, 1, opens=11, closes=20)
        self.assertNotIn(1, self._windows(self.kollokvium_period))
        self.assertTrue(any("Əvvəlcə K1" in text for text in texts), texts)

        self._save(self.kollokvium_period, 0)
        self._save(self.kollokvium_period, 1, opens=11, closes=20)
        self._save(self.kollokvium_period, 2, opens=21, closes=30)
        self.assertEqual(sorted(self._windows(self.kollokvium_period)), [0, 1, 2])

    def test_stale_window_can_only_be_deleted(self):
        stale = self._window(self.midterm_period, 1)

        _response, texts = self._post({"action": "toggle_window_active", "window_id": str(stale.pk)})
        stale.refresh_from_db()
        self.assertFalse(stale.is_active)
        self.assertTrue(any("yalnız silmək olar" in text for text in texts), texts)

        self._post(
            {"action": "grant_extra_days", "window_id": str(stale.pk), "scope": "organization", "extra_days": "2"}
        )
        with bypass_rls():
            self.assertFalse(KollokviumExtraGrant.objects.filter(window=stale).exists())

        self._post({"action": "delete_window", "window_id": str(stale.pk)})
        self.assertNotIn(1, self._windows(self.midterm_period))


class MidtermWindowFormTests(_MidtermScreenBase):
    def _data(self, period, k_index):
        return {
            "period": str(period.pk),
            "k_index": str(k_index),
            "opens_on": (self.today + datetime.timedelta(days=1)).isoformat(),
            "closes_on": (self.today + datetime.timedelta(days=10)).isoformat(),
        }

    def test_choices_follow_the_period_mode(self):
        midterm_form = KollokviumWindowForm(self._data(self.midterm_period, 0), organization=self.org)
        self.assertEqual([value for value, _label in midterm_form.fields["k_index"].choices], [0])
        kollokvium_form = KollokviumWindowForm(self._data(self.kollokvium_period, 0), organization=self.org)
        self.assertEqual(
            [label for _value, label in kollokvium_form.fields["k_index"].choices],
            ["K1", "K2", "K3"],
        )

    def test_crafted_k_index_is_rejected_for_midterm_period(self):
        form = KollokviumWindowForm(self._data(self.midterm_period, 2), organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("midterm", str(form.errors["k_index"]).lower())

    def test_k_index_0_is_valid_and_exposes_the_spec(self):
        form = KollokviumWindowForm(self._data(self.midterm_period, 0), organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.interim_spec.is_midterm)

    def test_invalid_period_does_not_crash(self):
        form = KollokviumWindowForm(
            {"period": "not-a-uuid", "k_index": "1", "opens_on": "", "closes_on": ""}, organization=self.org
        )
        self.assertFalse(form.is_valid())
        self.assertIn("period", form.errors)


class MidtermWordingTests(SimpleTestCase):
    """Jurnaldan kənar ad dəyişikliyi: bölmə başlığı + sillabus düsturu («Kollokvium» → «Midterm»)."""

    def test_section_title(self):
        from apps.accounts.views.profile._sections.labels import build_section_titles

        with translation.override("az"):
            self.assertEqual(str(build_section_titles()["kollokvium-windows"]), "Midterm pəncərələri")

    def test_syllabus_formula_label(self):
        from apps.syllabus.assessment_formula import LABELS, formula_text

        with translation.override("az"):
            self.assertEqual(str(LABELS["midterm"]), "Midterm (aralıq imtahan)")
            self.assertIn("Midterm (aralıq imtahan) 20", formula_text(("seminar",)))
            self.assertNotIn("Kollokvium", formula_text(("seminar",)))
