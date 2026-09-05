"""Kollokvium bal-yazma pəncərəsi dəyişikliyi bildirişləri.

``apps.registrar.kollokvium_notifications`` — pəncərə aktivləşəndə/
bağlananda/tarixi dəyişəndə həmin dövrün açılış müəllimlərinə (distinct)
toplu in-app bildiriş. Servis-səviyyə + `kollokvium_windows` view-i
(toggle/save) inteqrasiyası ilə yoxlanılır (əvvəllər bu axının HEÇ bir
view-səviyyə testi yox idi — SCOUT §5).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.notifications.models import InAppNotification
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import kollokvium_notifications
from apps.registrar.models import CourseOffering, KollokviumWindow, Program, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class KollokviumNotificationsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("kw_owner", "kw_owner@test.az", "StrongPass123!")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Kollokvium Notify Univ",
                slug="kollokvium-notify-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="KW Qrup", slug="kw-group", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2025/2026 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-01",
                end_date="2026-01-31",
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="KW101", name="Fənn")
            cls.program = Program.objects.create(organization=cls.org, code="KW", name="Proqram")
            cls.teacher = User.objects.create_user("kw_teacher", "kw_teacher@test.az", "StrongPass123!")
            cls.other_teacher = User.objects.create_user("kw_teacher2", "kw_teacher2@test.az", "StrongPass123!")
            for teacher in (cls.teacher, cls.other_teacher):
                Membership.objects.create(
                    user=teacher,
                    organization=cls.org,
                    role=cls.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
            cls.offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.subject,
                period=cls.period,
                group=cls.group,
                instructor=cls.teacher,
                lesson_hours=30,
            )
            # Digər qrup, EYNİ dövrdə, EYNİ müəllim → distinct qorunmalıdır.
            cls.group2 = OrgUnit.objects.create(
                organization=cls.org, name="KW Qrup 2", slug="kw-group-2", unit_type=OrgUnitType.GROUP
            )
            cls.offering2 = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.subject,
                period=cls.period,
                group=cls.group2,
                instructor=cls.teacher,
                lesson_hours=30,
            )
            cls.window = KollokviumWindow.objects.create(
                organization=cls.org,
                period=cls.period,
                k_index=0,
                opens_on="2025-11-01",
                closes_on="2025-11-10",
                is_active=False,
                created_by=cls.owner,
            )


class ServiceLevelTests(KollokviumNotificationsBase):
    def test_notify_window_opened_notifies_distinct_offering_instructors(self):
        with self.captureOnCommitCallbacks(execute=True):
            kollokvium_notifications.notify_window_opened(self.window)

        notes = InAppNotification.objects.filter(recipient=self.teacher, metadata__event="kollokvium_window_opened")
        self.assertEqual(notes.count(), 1)  # distinct — iki offering, TƏK bildiriş
        self.assertIn("K1", notes.first().title)
        self.assertIn("açıldı", notes.first().title)

    def test_notify_window_closed_notifies_offering_instructors(self):
        with self.captureOnCommitCallbacks(execute=True):
            kollokvium_notifications.notify_window_closed(self.window)

        notes = InAppNotification.objects.filter(recipient=self.teacher, metadata__event="kollokvium_window_closed")
        self.assertEqual(notes.count(), 1)
        self.assertIn("bağlandı", notes.first().title)

    def test_notify_window_extended_notifies_offering_instructors(self):
        with self.captureOnCommitCallbacks(execute=True):
            kollokvium_notifications.notify_window_extended(self.window)

        notes = InAppNotification.objects.filter(recipient=self.teacher, metadata__event="kollokvium_window_extended")
        self.assertEqual(notes.count(), 1)

    def test_no_recipients_creates_no_notification(self):
        with bypass_rls():
            empty_period = AcademicPeriod.objects.create(
                organization=self.org,
                name="Boş dövr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
            )
            empty_window = KollokviumWindow.objects.create(
                organization=self.org,
                period=empty_period,
                k_index=0,
                opens_on="2024-11-01",
                closes_on="2024-11-10",
            )
        with self.captureOnCommitCallbacks(execute=True):
            kollokvium_notifications.notify_window_opened(empty_window)
        self.assertFalse(InAppNotification.objects.filter(metadata__event="kollokvium_window_opened").exists())


class KollokviumWindowsViewIntegrationTests(KollokviumNotificationsBase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser("kw_super", "kw_super@test.az", "StrongPass123!")
        self.client = Client()
        assert self.client.login(username="kw_super", password="StrongPass123!")

    def test_non_uuid_window_id_is_a_404_not_a_500(self):
        """QA 2026-09-05 EXAMS-02: `window_id=x` `get_object_or_404(pk=...)`-də ValidationError → 500 verirdi."""
        response = self.client.post(
            reverse("accounts:kollokvium_windows"),
            {"action": "toggle_window_active", "window_id": "x"},
        )
        self.assertEqual(response.status_code, 404)

    def test_toggle_active_sends_opened_notification(self):
        url = reverse("accounts:kollokvium_windows")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                {
                    "action": "toggle_window_active",
                    "window_id": str(self.window.pk),
                    "organization_id": str(self.org.pk),
                },
            )
        self.assertEqual(response.status_code, 302)
        self.window.refresh_from_db()
        self.assertTrue(self.window.is_active)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.teacher, metadata__event="kollokvium_window_opened"
            ).exists()
        )

    def test_toggle_inactive_sends_closed_notification(self):
        self.window.is_active = True
        self.window.save(update_fields=["is_active"])
        url = reverse("accounts:kollokvium_windows")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                url,
                {
                    "action": "toggle_window_active",
                    "window_id": str(self.window.pk),
                    "organization_id": str(self.org.pk),
                },
            )
        self.window.refresh_from_db()
        self.assertFalse(self.window.is_active)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.teacher, metadata__event="kollokvium_window_closed"
            ).exists()
        )

    def test_save_window_date_change_on_active_window_sends_extended_notification(self):
        self.window.is_active = True
        self.window.save(update_fields=["is_active"])
        url = reverse("accounts:kollokvium_windows")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                url,
                {
                    "action": "save_window",
                    "period": str(self.period.pk),
                    "k_index": "0",
                    "opens_on": "2025-11-01",
                    "closes_on": "2025-11-20",  # uzadılıb
                    "organization_id": str(self.org.pk),
                },
            )
        self.window.refresh_from_db()
        self.assertEqual(str(self.window.closes_on), "2025-11-20")
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.teacher, metadata__event="kollokvium_window_extended"
            ).exists()
        )

    def test_save_window_same_dates_on_active_window_sends_nothing(self):
        self.window.is_active = True
        self.window.save(update_fields=["is_active"])
        url = reverse("accounts:kollokvium_windows")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                url,
                {
                    "action": "save_window",
                    "period": str(self.period.pk),
                    "k_index": "0",
                    "opens_on": "2025-11-01",
                    "closes_on": "2025-11-10",  # DƏYİŞMİR
                    "organization_id": str(self.org.pk),
                },
            )
        self.assertFalse(InAppNotification.objects.filter(metadata__event="kollokvium_window_extended").exists())

    def test_new_window_creation_sends_nothing_yet_inactive_by_default(self):
        url = reverse("accounts:kollokvium_windows")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                url,
                {
                    "action": "save_window",
                    "period": str(self.period.pk),
                    "k_index": "1",
                    "opens_on": "2025-12-01",
                    "closes_on": "2025-12-10",
                    "organization_id": str(self.org.pk),
                },
            )
        new_window = KollokviumWindow.objects.get(organization=self.org, period=self.period, k_index=1)
        self.assertFalse(new_window.is_active)
        self.assertFalse(InAppNotification.objects.filter(metadata__event__startswith="kollokvium_window").exists())
