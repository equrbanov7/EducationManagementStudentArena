"""Müəllim imtahan səhifələrinin redizaynı + «Mövcud imtahanlar»ın bağlanması (sahib 2026-10-10).

* Dil variantları / nəticələr / bankdan sual / sual bankı / sual modalı ortaq başlıqla
  (breadcrumb + geri + H1) render olunur, inline asset yoxdur, form müqaviləsi dəyişməyib.
* «Deaktiv et» sətir düyməsi təsdiq dialoqu ilə, az kataloqundakı «Bəli, deaktiv et» sızmır.
* Nəticələrdə tarix «gg.aa.iiii» (köhnə ISO linkləri də işləyir), nəticə yoxdursa Excel söndürülü.
* «Mövcud imtahanlar» defolt bağlıdır: keçidlər gizli, səhifə kabinetə yönləndirir, tələbənin
  ehtiyat «evi» kabinetdir; tənzimləmə yandırılanda köhnə davranış qayıdır (geri dönüş tələbi).
"""

from datetime import date

from django.contrib.messages import get_messages
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import translation

from apps.exams.models import BankQuestion, ExamAttempt, QuestionBank
from apps.exams.navigation import cabinet_exams_url, student_exams_home_url
from apps.exams.services.language_variants import create_variant, set_variant_active
from apps.exams.views.student._helpers import resolve_exam_failure_redirect
from apps.exams.views.teacher.results._helpers import _parse_filter_date

from .test_w4_wizard_units import _login, _UnitFixture

PAGE_MARKERS = ('class="ems-crumbs"', 'class="etp-back"', 'class="ems-header__title"')


class _PagesBase(_UnitFixture):
    def _client(self):
        return _login(self.teacher, self.org)

    def assertPageShell(self, html):
        for marker in PAGE_MARKERS:
            self.assertIn(marker, html)
        self.assertNotIn("<style", html)
        self.assertNotIn(" onclick=", html)


class LanguageManagerPageTests(_PagesBase):
    def test_renders_shell_and_confirmed_deactivate_action(self):
        exam = self._exam()
        create_variant(exam, "az")
        inactive = create_variant(exam, "ru")
        set_variant_active(inactive, False)
        with translation.override("az"):
            response = self._client().get(reverse("exams:exam_language_manager", kwargs={"slug": exam.slug}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertPageShell(html)
        # Aktiv sətir: təsdiq dialoqlu «Deaktiv et»; deaktiv sətir: təsdiqsiz «Aktiv et».
        self.assertEqual(html.count("data-elm-deactivate"), 1)
        self.assertIn('data-confirm-label="Deaktiv et"', html)
        self.assertIn("Aktiv et", html)
        self.assertNotIn("Bəli, deaktiv et", html)
        self.assertIn('name="action" value="toggle_variant"', html)
        self.assertIn('name="action" value="add_variant"', html)
        self.assertIn("exams/js/exam_language_manager.js", html)

    def test_toggle_still_flips_variant(self):
        exam = self._exam()
        variant = create_variant(exam, "az")
        url = reverse("exams:exam_language_manager", kwargs={"slug": exam.slug})
        response = self._client().post(url, {"action": "toggle_variant", "variant_id": variant.id})
        self.assertEqual(response.status_code, 302)
        variant.refresh_from_db()
        self.assertFalse(variant.is_active)


class ResultsPageTests(_PagesBase):
    def test_empty_exam_shows_disabled_export_and_empty_state(self):
        exam = self._exam()
        with translation.override("az"):
            response = self._client().get(reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertPageShell(html)
        self.assertIn('aria-disabled="true"', html.split('class="ems-header__actions"')[1][:900])
        self.assertNotIn(reverse("exams:export_exam_results_xlsx", kwargs={"slug": exam.slug}), html)
        self.assertIn("Hələ iştirakçı yoxdur", html)
        # Tarix sahələri native date deyil — «gg.aa.iiii» mətn sahəsi.
        self.assertNotIn('type="date"', html)
        self.assertEqual(html.count("data-etr-date"), 2)

    def test_participants_enable_export_and_render_rows(self):
        exam = self._exam()
        ExamAttempt.objects.create(exam=exam, user=self.student, status="submitted")
        response = self._client().get(reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}))
        html = response.content.decode()
        self.assertIn(reverse("exams:export_exam_results_xlsx", kwargs={"slug": exam.slug}), html)
        self.assertIn("data-seconds-remaining", html)
        self.assertIn('class="ems-sort"', html)

    def test_filtered_empty_state_differs_from_no_participants(self):
        exam = self._exam()
        ExamAttempt.objects.create(exam=exam, user=self.student, status="submitted")
        with translation.override("az"):
            response = self._client().get(
                reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}), {"q": "heç-kim-yoxdur"}
            )
        html = response.content.decode()
        self.assertIn("Filtrlərə uyğun nəticə yoxdur", html)
        self.assertNotIn("Hələ iştirakçı yoxdur", html)

    def test_date_filter_accepts_day_first_and_legacy_iso(self):
        self.assertEqual(_parse_filter_date("06.10.2026"), ("06.10.2026", date(2026, 10, 6)))
        self.assertEqual(_parse_filter_date("6/10/26"), ("06.10.2026", date(2026, 10, 6)))
        self.assertEqual(_parse_filter_date("2026-10-06"), ("06.10.2026", date(2026, 10, 6)))
        self.assertEqual(_parse_filter_date("31.02.2026"), ("", None))
        self.assertEqual(_parse_filter_date("sabah"), ("", None))
        self.assertEqual(_parse_filter_date(""), ("", None))

    def test_day_first_date_filters_attempts(self):
        exam = self._exam()
        ExamAttempt.objects.create(exam=exam, user=self.student, status="submitted")
        url = reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug})
        response = self._client().get(url, {"date_from": "01.01.2000", "date_to": "31.12.2099"})
        self.assertEqual(response.context["review_stats"]["total"], 1)
        self.assertEqual(response.context["date_from"], "01.01.2000")
        response = self._client().get(url, {"date_from": "01.01.2099"})
        self.assertEqual(response.context["review_stats"]["total"], 0)


class BankPickerPageTests(_PagesBase):
    def _bank(self, **kwargs):
        defaults = {"name": "Riyaziyyat bankı", "organization": self.org, "created_by": self.teacher}
        defaults.update(kwargs)
        return QuestionBank.objects.create(**defaults)

    def test_no_bank_selected_shows_guided_empty_state(self):
        exam = self._exam()
        self._bank()
        with translation.override("az"):
            response = self._client().get(reverse("exams:exam_bank_picker", kwargs={"slug": exam.slug}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertPageShell(html)
        self.assertIn("Əvvəl bank seçin", html)
        self.assertIn('data-live-search="true"', html)
        self.assertNotIn("data-ebp-attach", html)

    def test_no_compatible_bank_points_to_library(self):
        exam = self._exam()
        with translation.override("az"):
            response = self._client().get(reverse("exams:exam_bank_picker", kwargs={"slug": exam.slug}))
        html = response.content.decode()
        self.assertIn("Uyğun sual bankı yoxdur", html)
        self.assertIn(reverse("exams:question_bank_list"), html)

    def test_selected_bank_lists_checkboxes_and_sticky_bar(self):
        exam = self._exam()
        bank = self._bank()
        question = BankQuestion.objects.create(bank=bank, text="2 + 2 = ?", question_type="test", language="az")
        response = self._client().get(reverse("exams:exam_bank_picker", kwargs={"slug": exam.slug}), {"bank": bank.id})
        html = response.content.decode()
        self.assertIn('name="question_ids" value="%s"' % question.id, html)
        self.assertIn('name="action" value="attach"', html)
        self.assertIn("data-ebp-submit", html)
        self.assertIn("etp-actionbar", html)
        self.assertEqual(response.context["page_start"], 1)
        self.assertEqual(response.context["page_end"], 1)

    def test_empty_bank_and_filtered_empty_states_differ(self):
        exam = self._exam()
        bank = self._bank()
        url = reverse("exams:exam_bank_picker", kwargs={"slug": exam.slug})
        with translation.override("az"):
            html = self._client().get(url, {"bank": bank.id}).content.decode()
            self.assertIn("Bu bankda uyğun sual yoxdur", html)
            self.assertNotIn("Filtrləri sıfırla", html)
            BankQuestion.objects.create(bank=bank, text="5 + 5 = ?", question_type="test", language="az")
            html = self._client().get(url, {"bank": bank.id, "q": "yoxdur-xyz"}).content.decode()
        self.assertIn("Filtrlərə uyğun sual tapılmadı", html)
        self.assertNotIn("Bu bankda uyğun sual yoxdur", html)

    def test_attach_post_contract_unchanged(self):
        exam = self._exam()
        bank = self._bank()
        question = BankQuestion.objects.create(bank=bank, text="3 + 3 = ?", question_type="test", language="az")
        url = reverse("exams:exam_bank_picker", kwargs={"slug": exam.slug})
        response = self._client().post(url, {"action": "attach", "bank": bank.id, "question_ids": [question.id]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(exam.questions.count(), 1)


class AvailableExamsGateTests(_UnitFixture):
    """Sahib 2026-10-10: «Mövcud imtahanlar»ı yığışdır — defolt bağlı, tənzimləmə ilə qayıdır."""

    def test_page_redirects_to_cabinet_with_info_when_disabled(self):
        response = _login(self.student, self.org).get(reverse("exams:student_exam_list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('accounts:profile')}?section=assigned-exams")
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(messages)

    def test_teacher_lands_on_my_exams(self):
        response = _login(self.teacher, self.org).get(reverse("exams:student_exam_list"))
        self.assertEqual(response.url, f"{reverse('accounts:profile')}?section=my-exams")

    def test_safe_return_to_is_honoured_without_loop(self):
        client = _login(self.student, self.org)
        target = f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=exams"
        response = client.get(reverse("exams:student_exam_list"), {"return_to": target})
        self.assertEqual(response.url, target)
        loop = client.get(reverse("exams:student_exam_list"), {"return_to": reverse("exams:student_exam_list")})
        self.assertEqual(loop.url, f"{reverse('accounts:profile')}?section=assigned-exams")
        offsite = client.get(reverse("exams:student_exam_list"), {"return_to": "https://evil.example/"})
        self.assertNotIn("evil", offsite.url)

    @override_settings(EXAM_AVAILABLE_PAGE=True)
    def test_page_still_works_when_switched_back_on(self):
        response = _login(self.student, self.org).get(reverse("exams:student_exam_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "exams/student/student_exam_list.html")

    def test_student_fallback_home_is_cabinet_when_disabled(self):
        request = RequestFactory().get("/")
        request.user = self.student
        self.assertEqual(resolve_exam_failure_redirect(request), cabinet_exams_url(self.student))
        self.assertEqual(student_exams_home_url(self.student), cabinet_exams_url(self.student))
        with override_settings(EXAM_AVAILABLE_PAGE=True):
            self.assertEqual(resolve_exam_failure_redirect(request), reverse("exams:student_exam_list"))

    def test_student_still_starts_assigned_exam_from_cabinet(self):
        """Tələbə qapalı qalmır: təyin olunmuş imtahan kabinet bölməsində görünür və başlanır."""
        exam = self._exam(title="Kabinetdən başlanan quiz")
        exam.allowed_units.add(self.group)
        client = _login(self.student, self.org)
        response = client.get(reverse("accounts:profile"), {"section": "assigned-exams"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kabinetdən başlanan quiz")
        self.assertContains(response, reverse("exams:start_exam", kwargs={"slug": exam.slug}))

    @override_settings(UNIVERSITY_MODE=False)
    def test_navbar_and_footer_links_follow_the_flag(self):
        client = _login(self.student, self.org)
        url = reverse("exams:student_exam_list")
        html = client.get(reverse("accounts:profile")).content.decode()
        self.assertNotIn(f'href="{url}"', html)
        with override_settings(EXAM_AVAILABLE_PAGE=True):
            html = client.get(reverse("accounts:profile")).content.decode()
        self.assertIn(f'href="{url}"', html)

    def test_ai_assistant_context_omits_closed_page(self):
        from types import SimpleNamespace

        from apps.ai_assistant.context_builder import _navigation_section

        org = SimpleNamespace(slug="qku")
        memberships = [SimpleNamespace(role=SimpleNamespace(name="student"), is_active=True)]
        closed = _navigation_section(self.student, org, memberships, [])
        self.assertNotIn("/exams/available/", closed)
        with override_settings(EXAM_AVAILABLE_PAGE=True):
            opened = _navigation_section(self.student, org, memberships, [])
        self.assertIn("/accounts/profile/?section=assigned-exams", closed)
        self.assertIn("/exams/available/", opened)
