"""Bildiriş keçidi alıcını DOĞRU tenant kontekstinə gətirməlidir.

Kök səbəb: keçid yaradılan anda donur, hədəf view isə obyekti sessiyadakı
aktiv təşkilata görə scope-lanmış queryset-də axtarır. Aktiv org fərqli olanda
tamamilə etibarlı keçid 404 verirdi (çox-org istifadəçiləri).
"""

from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.notifications.models import InAppNotification
from apps.notifications.services.crud import create_notification
from apps.notifications.services.helpers import org_scoped_link
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class OrgScopedLinkHelperTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("osl-owner", "osl-owner@example.com", "pass12345")
        cls.org = Organization.objects.create(
            name="OSL Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.user,
            status="active",
            is_active=True,
        )

    def test_wraps_internal_link_with_switch_hop(self):
        wrapped = org_scoped_link("/exams/some-exam/results/", self.org)

        parsed = urlparse(wrapped)
        self.assertEqual(parsed.path, reverse("organizations:switch", kwargs={"slug": self.org.slug}))
        self.assertEqual(parse_qs(parsed.query)["next"], ["/exams/some-exam/results/"])

    def test_already_wrapped_link_is_left_alone(self):
        original = org_scoped_link("/exams/a/results/", self.org)
        self.assertEqual(org_scoped_link(original, self.org), original)

    def test_no_organization_leaves_link_untouched(self):
        self.assertEqual(org_scoped_link("/exams/a/results/", None), "/exams/a/results/")

    def test_organization_passed_as_id_is_a_safe_no_op(self):
        """`organization` bəzən id kimi ötürülür — slug yoxdursa toxunmuruq."""
        self.assertEqual(org_scoped_link("/exams/a/results/", self.org.id), "/exams/a/results/")

    def test_empty_and_external_links_untouched(self):
        self.assertEqual(org_scoped_link("", self.org), "")
        self.assertEqual(org_scoped_link("https://elsewhere.example/x", self.org), "https://elsewhere.example/x")


class CreateNotificationAppliesScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("osl-recipient", "osl-recipient@example.com", "pass12345")
        cls.org = Organization.objects.create(
            name="OSL Recipient Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.user,
            status="active",
            is_active=True,
        )

    def test_link_is_scoped_at_creation(self):
        notification = create_notification(
            recipient=self.user,
            title="Yeni imtahan cəhdi",
            link="/exams/demo-exam/results/",
            organization=self.org,
        )

        stored = InAppNotification.objects.get(pk=notification.pk)
        self.assertTrue(stored.link.startswith("/organizations/switch/"))
        self.assertIn("next=", stored.link)

    def test_global_notification_keeps_plain_link(self):
        notification = create_notification(
            recipient=self.user,
            title="Sistem elanı",
            link="/blog/post/1/",
            organization=None,
        )

        self.assertEqual(notification.link, "/blog/post/1/")
