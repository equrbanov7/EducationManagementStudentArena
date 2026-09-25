"""Jurnal bağlanması → kampaniyanın avtomatik açılışı (siqnal) + əmrlər."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.notifications.models import InAppNotification
from apps.registrar.public import journal_close
from apps.surveys.constants import EVENT_CAMPAIGN_OPENED, CampaignStatus, OpenedVia
from apps.surveys.models import SurveyCampaign, SurveyTemplate
from apps.surveys.receivers import handle_journals_closed
from apps.surveys.services.gate_snapshot import read_snapshot
from core.rls import bypass_rls

from .factories import build_world, member


def _notes(org):
    return InAppNotification.objects.filter(organization=org, metadata__event=EVENT_CAMPAIGN_OPENED)


class JournalClosedSignalTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svsig", students=3)
        with bypass_rls():
            cls.rim = member(cls.w["org"], "svsig_rim", "ikt_rehber")

    def _close(self, **kwargs):
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            return journal_close.close_journals(
                organization=self.w["org"], period=self.w["period"], by_user=self.rim, **kwargs
            )

    def test_close_opens_campaign_seeds_template_and_notifies_students_once(self):
        self._close()
        campaign = SurveyCampaign.objects.get(organization=self.w["org"], period=self.w["period"])
        self.assertEqual(campaign.status, CampaignStatus.OPEN)
        self.assertEqual(campaign.opened_via, OpenedVia.JOURNAL_CLOSE)
        self.assertTrue(campaign.mandatory)
        self.assertIsNotNone(campaign.closes_on)
        self.assertEqual((campaign.closes_on - campaign.opens_on).days, 30)
        self.assertEqual((campaign.grace_until - campaign.opens_on).days, 3)
        self.assertTrue(SurveyTemplate.objects.filter(organization=self.w["org"], is_default=True).exists())
        self.w["org"].refresh_from_db()
        self.assertEqual([c["id"] for c in read_snapshot(self.w["org"])["campaigns"]], [str(campaign.pk)])
        notes = _notes(self.w["org"])
        self.assertEqual(set(notes.values_list("recipient_id", flat=True)), {s.pk for s in self.w["students"]})
        self.assertEqual(notes.count(), 3)

    def test_second_close_is_idempotent(self):
        self._close()
        self._close()
        self.assertEqual(SurveyCampaign.objects.filter(organization=self.w["org"]).count(), 1)
        self.assertEqual(_notes(self.w["org"]).count(), 3)  # heç nə dəyişmədi → yeni bildiriş yox

    def test_later_close_notifies_only_newly_eligible_students(self):
        from apps.registrar.models import Enrollment

        with bypass_rls():
            newcomer = member(self.w["org"], "svsig_new", "student")
            Enrollment.objects.create(organization=self.w["org"], student=newcomer, offering=self.w["off_phys"])
        # 1) yalnız riyaziyyat (kafedra A qrupu → faculty scope eyni; ayrı-ayrı bağlayırıq)
        with bypass_rls():
            from apps.surveys.tests.factories import close_journal

            close_journal(self.w["org"], self.w["off_math"])
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            handle_journals_closed(self.w["org"], self.w["period"], [self.w["off_math"].pk])
        first = set(_notes(self.w["org"]).values_list("recipient_id", flat=True))
        self.assertEqual(first, {s.pk for s in self.w["students"]})
        with bypass_rls():
            close_journal(self.w["org"], self.w["off_phys"])
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            handle_journals_closed(self.w["org"], self.w["period"], [self.w["off_phys"].pk])
        # İkinci bağlanma: yalnız əvvəl heç bir bağlı açılışı olmayan tələbə.
        self.assertEqual(_notes(self.w["org"]).filter(recipient=newcomer).count(), 1)
        self.assertEqual(_notes(self.w["org"]).count(), 4)

    def test_closed_campaign_is_not_reopened_automatically(self):
        self._close()
        SurveyCampaign.objects.filter(organization=self.w["org"]).update(status=CampaignStatus.CLOSED)
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            report = handle_journals_closed(self.w["org"], self.w["period"], [self.w["off_math"].pk])
        self.assertEqual(report["campaign"].status, CampaignStatus.CLOSED)
        self.assertFalse(report["opened"])

    def test_auto_open_can_be_disabled_per_org(self):
        org = self.w["org"]
        org.settings = {**(org.settings or {}), "surveys": {"auto_open": False}}
        org.save(update_fields=["settings"])
        self._close()
        self.assertFalse(SurveyCampaign.objects.filter(organization=org).exists())

    def test_receiver_failure_never_breaks_journal_close(self):
        from unittest import mock

        with mock.patch("apps.surveys.receivers.handle_journals_closed", side_effect=RuntimeError("boom")):
            result = self._close()
        self.assertEqual(result["closed"], 2)


class CommandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("svcmd", students=2)
        from .factories import close_all

        close_all(cls.w)

    def test_dry_run_writes_nothing(self):
        out = StringIO()
        call_command("surveys_open_campaign", "--period", str(self.w["period"].pk), stdout=out)
        self.assertIn("Quru icra", out.getvalue())
        self.assertFalse(SurveyCampaign.objects.filter(organization=self.w["org"]).exists())

    def test_apply_opens_manually_and_is_idempotent(self):
        with self.captureOnCommitCallbacks(execute=True):
            call_command("surveys_open_campaign", "--period", str(self.w["period"].pk), "--apply", stdout=StringIO())
        campaign = SurveyCampaign.objects.get(organization=self.w["org"])
        self.assertEqual((campaign.status, campaign.opened_via), (CampaignStatus.OPEN, OpenedVia.MANUAL))
        self.assertEqual(_notes(self.w["org"]).count(), 2)
        with self.captureOnCommitCallbacks(execute=True):
            call_command("surveys_open_campaign", "--period", str(self.w["period"].pk), "--apply", stdout=StringIO())
        self.assertEqual(SurveyCampaign.objects.filter(organization=self.w["org"]).count(), 1)
        self.assertEqual(_notes(self.w["org"]).count(), 2)

    def test_ensure_template_command(self):
        call_command("surveys_ensure_template", "--org", self.w["org"].slug, "--apply", stdout=StringIO())
        template = SurveyTemplate.objects.get(organization=self.w["org"], is_default=True)
        self.assertEqual(template.questions.count(), 20)
        self.assertEqual(template.questions.filter(section="general").count(), 3)
        call_command("surveys_ensure_template", "--org", self.w["org"].slug, "--apply", stdout=StringIO())
        self.assertEqual(SurveyTemplate.objects.filter(organization=self.w["org"]).count(), 1)
