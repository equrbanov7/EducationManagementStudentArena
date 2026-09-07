"""Kollokvium pəncərəsi — tarix qaydaları validasiyası (QA 2026-09-05, P3-21).

İmtahan Mərkəzi kabinetində (``apps.accounts.views.kollokvium_windows``) əvvəllər
server-side yoxlanmayan üç qayda test olunur:

1. **Keçmiş bağlanış — yalnız YARADILIŞDA qadağan.** YENİ pəncərənin bağlanış
   tarixi bugündən əvvəl ola bilməz; ARTIQ MÖVCUD (işləyən/bitmiş) pəncərəni
   uzatmaq (redaktə) sərbətdir.
2. **K-sırası / toqquşma.** Eyni (organization, period) əhatəsində K2 K1
   bitmədən başlaya bilməz; fərqli K-lər üst-üstə düşə bilməz (yalnız qonşu
   K-lər deyil — K1/K3 arası da yoxlanılır, K2 olmasa belə).
3. **Boş forma xətası.** ``KollokviumWindowForm``-un boş POST-da verdiyi
   "sahə mütləqdir" xətası Django-nun ÖZ kontekstsiz "This field is
   required." mesajıdır — AZ kataloqda bu səhvən "Fayl seçilməyib."-ə
   tərcümə olunmuşdu (fayl sahəsi HEÇ olmayan formada çaşdırıcı idi).
   ``locale/az/LC_MESSAGES/django.po`` düzəldilib; bura reqressiya testidir.

Qayda 1-2 domen qatındadır: ``apps.registrar.kollokvium_windows.validate_window_save``
(``KollokviumWindowRuleError`` qaldırır — ``gradebook.LessonRuleError`` naxışı).
View (``apps.accounts.views.kollokvium_windows._dispatch_action``) bunu
``KollokviumAdminError``-a çevirib forma xətası kimi göstərir.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.forms.kollokvium_windows import KollokviumWindowForm
from apps.organizations.models import AcademicPeriod, Organization
from apps.registrar import kollokvium_windows as kollokvium_window_rules
from apps.registrar.models import KollokviumWindow
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class KollokviumWindowValidationBase(TestCase):
    """Ortaq fixture — bir təşkilat + uzaq keçmişdən uzaq gələcəyə qədər semestr.

    Semestr aralığı real "bugün"dən asılı olmayaraq HƏMİŞƏ cari sayılsın deyə
    geniş götürülüb (``is_past`` yalnız ``end_date < bugün`` yoxlayır) — testlər
    ``_reject_if_period_past`` maneəsinə ilişməsin.
    """

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.owner = User.objects.create_user("kwv_owner", "kwv_owner@test.az", "StrongPass123!")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Kollokvium Validation Univ",
                slug="kollokvium-validation-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Validasiya semestri",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2099/2100",
                start_date=cls.today - datetime.timedelta(days=400),
                end_date=cls.today + datetime.timedelta(days=400),
                is_current=True,
            )


class ValidateWindowSaveServiceTests(KollokviumWindowValidationBase):
    """``validate_window_save`` — birbaşa servis-səviyyə testlər."""

    def test_new_window_with_past_closes_on_is_rejected(self):
        with self.assertRaises(kollokvium_window_rules.KollokviumWindowRuleError) as ctx:
            kollokvium_window_rules.validate_window_save(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=self.today - datetime.timedelta(days=30),
                closes_on=self.today - datetime.timedelta(days=1),
                is_new=True,
                today=self.today,
            )
        self.assertIn("keçmişdə", str(ctx.exception))

    def test_new_window_with_future_closes_on_is_allowed(self):
        # İstisna qaldırılmır — sükutla keçir.
        kollokvium_window_rules.validate_window_save(
            organization=self.org,
            period=self.period,
            k_index=0,
            opens_on=self.today,
            closes_on=self.today + datetime.timedelta(days=10),
            is_new=True,
            today=self.today,
        )

    def test_existing_past_window_can_be_extended(self):
        """Redaktə (``is_new=False``) — bağlanış keçmişdə olsa belə rədd edilmir."""
        kollokvium_window_rules.validate_window_save(
            organization=self.org,
            period=self.period,
            k_index=0,
            opens_on=self.today - datetime.timedelta(days=60),
            closes_on=self.today - datetime.timedelta(days=1),  # hələ keçmişdə — amma UZADILIR
            is_new=False,
            today=self.today,
        )

    def test_k2_cannot_start_before_k1_closes(self):
        with bypass_rls():
            KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=self.today,
                closes_on=self.today + datetime.timedelta(days=10),
            )
        with self.assertRaises(kollokvium_window_rules.KollokviumWindowRuleError) as ctx:
            kollokvium_window_rules.validate_window_save(
                organization=self.org,
                period=self.period,
                k_index=1,
                opens_on=self.today + datetime.timedelta(days=5),  # K1 bitmədən (gün 10) başlayır
                closes_on=self.today + datetime.timedelta(days=20),
                is_new=True,
                today=self.today,
            )
        self.assertIn("K2", str(ctx.exception))
        self.assertIn("K1", str(ctx.exception))

    def test_k2_starting_exactly_when_k1_closes_is_allowed(self):
        """Eyni gün keçid (``opens_on == k1.closes_on``) toqquşma sayılmır."""
        with bypass_rls():
            KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=self.today,
                closes_on=self.today + datetime.timedelta(days=10),
            )
        kollokvium_window_rules.validate_window_save(
            organization=self.org,
            period=self.period,
            k_index=1,
            opens_on=self.today + datetime.timedelta(days=10),  # == K1.closes_on
            closes_on=self.today + datetime.timedelta(days=20),
            is_new=True,
            today=self.today,
        )

    def test_editing_k1_into_k2_overlap_is_rejected(self):
        """K1-i redaktə edərək K2-nin başladığı tarixdən sonra bitirmək qadağandır."""
        with bypass_rls():
            KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=self.today,
                closes_on=self.today + datetime.timedelta(days=10),
            )
            KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=1,
                opens_on=self.today + datetime.timedelta(days=12),
                closes_on=self.today + datetime.timedelta(days=20),
            )
        with self.assertRaises(kollokvium_window_rules.KollokviumWindowRuleError) as ctx:
            kollokvium_window_rules.validate_window_save(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=self.today,
                closes_on=self.today + datetime.timedelta(days=15),  # K2 açılışından (gün 12) sonra bitir
                is_new=False,
                today=self.today,
            )
        self.assertIn("K1", str(ctx.exception))
        self.assertIn("K2", str(ctx.exception))

    def test_k1_and_k3_overlap_detected_without_k2(self):
        """Qonşu olmayan cütlər də yoxlanılır — K2 mövcud olmasa belə K1/K3 toqquşması tutulur."""
        with bypass_rls():
            KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=self.today,
                closes_on=self.today + datetime.timedelta(days=10),
            )
        with self.assertRaises(kollokvium_window_rules.KollokviumWindowRuleError):
            kollokvium_window_rules.validate_window_save(
                organization=self.org,
                period=self.period,
                k_index=2,
                opens_on=self.today + datetime.timedelta(days=5),  # K1 bitmədən (gün 10) başlayır
                closes_on=self.today + datetime.timedelta(days=30),
                is_new=True,
                today=self.today,
            )

    def test_different_period_windows_never_clash(self):
        """Fərqli semestr — fərqli əhatə: eyni tarixlər problemsiz qəbul olunur."""
        with bypass_rls():
            other_period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Başqa semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2098/2099",
                start_date=self.today - datetime.timedelta(days=800),
                end_date=self.today - datetime.timedelta(days=400),
            )
            KollokviumWindow.objects.create(
                organization=self.org,
                period=other_period,
                k_index=0,
                opens_on=self.today - datetime.timedelta(days=750),
                closes_on=self.today - datetime.timedelta(days=740),
            )
        # Eyni k_index (0), tamam fərqli (gələcək) tarixlər, AMMA fərqli period — toqquşma yoxdur.
        kollokvium_window_rules.validate_window_save(
            organization=self.org,
            period=self.period,
            k_index=0,
            opens_on=self.today,
            closes_on=self.today + datetime.timedelta(days=10),
            is_new=True,
            today=self.today,
        )


class KollokviumWindowFormEmptySubmissionTests(KollokviumWindowValidationBase):
    """Qayda 3 — boş POST "Fayl seçilməyib." demir, sahə tələb olunur deyir."""

    def test_empty_payload_required_field_error_is_not_file_message(self):
        form = KollokviumWindowForm(data={}, organization=self.org)
        self.assertFalse(form.is_valid())
        rendered_errors = str(form.errors)
        self.assertNotIn("Fayl seçilməyib", rendered_errors)
        # Bütün məcburi sahələr (period/k_index/opens_on/closes_on) xəta verməlidir.
        for field in ("period", "k_index", "opens_on", "closes_on"):
            self.assertIn(field, form.errors)
            self.assertNotIn("Fayl seçilməyib", str(form.errors[field]))

    def test_django_required_message_catalog_is_fixed(self):
        """Reqressiya: AZ kataloqda ``"This field is required."`` "Fayl
        seçilməyib."-ə YOX, "sahə" mesajına tərcümə olunmalıdır (no-ctx
        msgid toqquşması — kollokvium formu heç bir fayl sahəsi daşımır)."""
        from django.utils.translation import gettext

        message = gettext("This field is required.")
        self.assertNotEqual(message, "Fayl seçilməyib.")


class KollokviumWindowsViewValidationIntegrationTests(KollokviumWindowValidationBase):
    """Tam HTTP axını — ``accounts:kollokvium_windows`` view-i üzərindən."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser("kwv_super", "kwv_super@test.az", "StrongPass123!")
        self.client = Client()
        assert self.client.login(username="kwv_super", password="StrongPass123!")
        self.url = reverse("accounts:kollokvium_windows")

    def _post(self, data):
        payload = {"organization_id": str(self.org.pk), "period": str(self.period.pk)}
        payload.update(data)
        return self.client.post(self.url, payload)

    def test_new_window_with_past_closes_on_is_rejected_end_to_end(self):
        response = self._post(
            {
                "action": "save_window",
                "k_index": "0",
                "opens_on": (self.today - datetime.timedelta(days=30)).isoformat(),
                "closes_on": (self.today - datetime.timedelta(days=1)).isoformat(),
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(KollokviumWindow.objects.filter(organization=self.org, period=self.period, k_index=0).exists())
        texts = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("keçmişdə" in t for t in texts), texts)

    def test_extending_existing_past_window_succeeds_end_to_end(self):
        with bypass_rls():
            window = KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=self.today - datetime.timedelta(days=60),
                closes_on=self.today - datetime.timedelta(days=30),
                is_active=True,
            )
        new_closes = self.today - datetime.timedelta(days=10)  # hələ keçmişdə, amma UZADILIB
        response = self._post(
            {
                "action": "save_window",
                "k_index": "0",
                "opens_on": window.opens_on.isoformat(),
                "closes_on": new_closes.isoformat(),
            }
        )
        self.assertEqual(response.status_code, 302)
        window.refresh_from_db()
        self.assertEqual(window.closes_on, new_closes)

    def test_k2_before_k1_ends_is_rejected_end_to_end(self):
        with bypass_rls():
            KollokviumWindow.objects.create(
                organization=self.org,
                period=self.period,
                k_index=0,
                opens_on=self.today,
                closes_on=self.today + datetime.timedelta(days=10),
            )
        response = self._post(
            {
                "action": "save_window",
                "k_index": "1",
                "opens_on": (self.today + datetime.timedelta(days=5)).isoformat(),
                "closes_on": (self.today + datetime.timedelta(days=20)).isoformat(),
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(KollokviumWindow.objects.filter(organization=self.org, period=self.period, k_index=1).exists())
        texts = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("K1" in t and "K2" in t for t in texts), texts)

    def test_empty_save_window_submission_does_not_show_file_message(self):
        response = self._post({"action": "save_window", "period": "", "k_index": "", "opens_on": "", "closes_on": ""})
        self.assertEqual(response.status_code, 302)
        texts = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(texts, "gözlənilən xəta mesajı yaranmadı")
        self.assertFalse(any("Fayl seçilməyib" in t for t in texts), texts)
