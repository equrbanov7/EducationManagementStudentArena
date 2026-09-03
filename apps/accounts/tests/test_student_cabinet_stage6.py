"""Ekran 10 «Tələbə kabineti» — Mərhələ 6 fərqləri (dizayn handoff).

Nəyi qoruyur
------------
1. **Transkript siyasəti (README §10.1, default `request`).**
   ``STUDENT_TRANSCRIPT_SELF_SERVICE=False`` ikən kabinetdə «PDF yüklə»
   GÖSTƏRİLMİR (endpoint onsuz da 404 verirdi) — əvəzinə «Transkript sorğusu»
   növü ÖNCƏDƏN SEÇİLMİŞ halda Müraciətlər panelinə CTA verilir.
   Bayraq AÇILANDA köhnə davranış qayıdır (yalnız policy dəyəri dəyişir).
2. **Sillabus yalnız APPROVED (§8/9).** Fənn kartındakı «Sillabus» keçidi
   yalnız təsdiqlənmiş versiyası olan açılış üçün görünür; qaralama /
   baxışdakı versiya kartda YOXDUR.
3. **Qiymətləndirmə çəkiləri (§8/4)** kabinetdə görünür və kodda hardcode
   deyil — org siyasətindən oxunur (10 / 10 / 30 / 50, cəm 100).
4. **«Bu gün / növbəti dərslər»** kartı bu gün dərs olmayanda boş qalmır.
"""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, TestCase, override_settings

from apps.registrar import public as registrar_public
from apps.registrar.cabinet_policy import (
    TRANSCRIPT_APPLICATION_KIND,
    approved_syllabus_offerings,
    assessment_weights_view,
    transcript_policy,
)


class TranscriptPolicyTest(TestCase):
    def test_default_policy_is_request_and_points_at_the_application_kind(self):
        # Sahib qərarı: öz-özünə xidmət SÖNDÜRÜLÜ qalır.
        self.assertFalse(registrar_public.STUDENT_TRANSCRIPT_SELF_SERVICE)
        policy = transcript_policy(self_service=False)
        self.assertFalse(policy["self_service"])
        self.assertIn("section=applications", policy["request_url"])
        self.assertIn("new_kind=%s" % TRANSCRIPT_APPLICATION_KIND, policy["request_url"])

    def test_download_policy_only_flips_the_flag(self):
        policy = transcript_policy(self_service=True)
        self.assertTrue(policy["self_service"])
        # URL YENƏ qurulur — sahib `download`-a keçəndə yeni UI lazım deyil.
        self.assertIn("section=applications", policy["request_url"])

    def test_transcript_kind_exists_in_the_applications_catalogue(self):
        from apps.applications.constants import DEFAULT_KIND_SEED

        codes = {kind["code"] for kind in DEFAULT_KIND_SEED}
        self.assertIn(TRANSCRIPT_APPLICATION_KIND, codes)


class AssessmentWeightsTest(TestCase):
    def test_locked_weights_sum_to_one_hundred(self):
        weights = assessment_weights_view(None)
        self.assertEqual(weights["attendance"], 10)
        self.assertEqual(weights["selfwork"], 10)
        self.assertEqual(weights["current"], 30)
        self.assertEqual(weights["final"], 50)
        self.assertEqual(weights["total"], 100)


class ApprovedSyllabusBatchTest(TestCase):
    def test_no_offerings_returns_an_empty_set(self):
        self.assertEqual(approved_syllabus_offerings(None, []), set())


@override_settings(UNIVERSITY_MODE=True)
class UpcomingSlotsTest(TestCase):
    """«Bu gün / növbəti dərslər» — bu gün boş olanda növbəti günü göstərir."""

    def test_upcoming_slots_picks_the_next_teaching_day(self):
        import datetime as dt

        from apps.accounts.views.profile._sections.dashboard_widgets import upcoming_slots
        from apps.registrar.models import WeekType

        class Slot:
            def __init__(self, weekday, hour):
                self.weekday = weekday
                self.week_type = WeekType.ALL
                self.start_time = dt.time(hour, 0)

        slots = [Slot(5, 9), Slot(3, 12), Slot(3, 9)]
        week_context = {"today": mock.Mock(isoweekday=lambda: 2), "parity": WeekType.ODD}
        day, picked = upcoming_slots(slots, week_context)
        self.assertTrue(day)
        self.assertEqual([slot.start_time.hour for slot in picked], [9, 12])

    def test_upcoming_slots_is_empty_when_nothing_is_left_this_week(self):
        from apps.accounts.views.profile._sections.dashboard_widgets import upcoming_slots

        day, picked = upcoming_slots([], {"today": mock.Mock(isoweekday=lambda: 5), "parity": None})
        self.assertEqual((day, picked), ("", []))


class TranscriptTemplateContractTest(TestCase):
    """Şablon siyasət açarlarını OXUYUR — «PDF yüklə» şərtsiz qalmasın."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_template_branches_on_self_service(self):
        from pathlib import Path

        from django.conf import settings

        path = Path(settings.BASE_DIR) / "apps/accounts/templates/accounts/profile/sections/_my_transcript.html"
        body = path.read_text(encoding="utf-8")
        self.assertIn("sec.self_service", body)
        self.assertIn("sec.request_url", body)

    def test_subjects_template_uses_approved_only_syllabus_flag(self):
        from pathlib import Path

        from django.conf import settings

        path = Path(settings.BASE_DIR) / "apps/accounts/templates/accounts/profile/sections/_my_subjects.html"
        body = path.read_text(encoding="utf-8")
        self.assertIn("row.syllabus_available", body)
        self.assertIn("sec.assessment_weights", body)
        self.assertIn("row.teacher", body)
