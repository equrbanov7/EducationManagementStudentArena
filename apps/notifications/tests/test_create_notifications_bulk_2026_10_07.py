"""``create_notifications`` — fərqli mətnli bildirişlər TƏK toplu INSERT-də, sətirlər ``create_notification`` ilə eyni.

Tutum 2026-10-07: jurnal yazısından sonra (``registrar.journal_notifications``) hər
tələbə üçün ``create_notification`` — ``bypass_rls`` bloku + INSERT = 4 ifadə — gedirdi.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.notifications.models import InAppNotification, NotificationType
from apps.notifications.public import create_notification, create_notifications
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

_FIELDS = ("recipient_id", "organization_id", "title", "message", "link", "notification_type", "is_read", "metadata")


class CreateNotificationsBulkTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("cnb-owner", "cnb-owner@example.com", "pass12345")
        cls.org = Organization.objects.create(
            name="CNB Org",
            slug="cnb-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.users = [User.objects.create_user(f"cnb-{i}", f"cnb-{i}@example.com", "pass12345") for i in range(12)]

    def _item(self, user, index):
        return {
            "recipient": user,
            "title": f"Başlıq {index}",
            "message": f"Mətn {index}\nikinci sətir",
            "link": "/accounts/profile/?section=my-journal",
            "organization": self.org,
            "notification_type": NotificationType.SYSTEM,
            "metadata": {"event": "journal_update", "offering_id": f"off-{index}"},
        }

    def test_rows_match_single_create(self):
        expected = []
        for index, user in enumerate(self.users[:3]):
            row = create_notification(**self._item(user, index))
            expected.append({field: getattr(row, field) for field in _FIELDS})
        InAppNotification.objects.all().delete()
        created = create_notifications([self._item(user, index) for index, user in enumerate(self.users[:3])])
        self.assertEqual(len(created), 3)
        actual = [
            {field: getattr(row, field) for field in _FIELDS}
            for row in InAppNotification.objects.filter(pk__in=[row.pk for row in created]).order_by("title")
        ]
        self.assertEqual(actual, expected)

    def test_query_count_does_not_grow_with_recipients(self):
        counts = []
        for users in (self.users[:2], self.users[2:12]):
            with CaptureQueriesContext(connection) as ctx:
                create_notifications([self._item(user, index) for index, user in enumerate(users)])
            counts.append(len(ctx.captured_queries))
        self.assertEqual(counts[0], counts[1], counts)
        self.assertEqual(InAppNotification.objects.count(), 12)

    def test_empty_items_do_nothing(self):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(create_notifications([]), [])
        self.assertEqual(len(ctx.captured_queries), 0)
