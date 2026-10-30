"""A shared teacher appears in broad pickers without widening journal scope."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.registrar.models import CourseOffering, JournalShare
from core.rls import bypass_rls

from . import test_journal_list_teacher_search as fixtures


class SharedTeacherFilterTest(TestCase):
    setUpTestData = classmethod(fixtures.JournalListTeacherSearchTest.setUpTestData.__func__)

    def setUp(self):
        with bypass_rls():
            self.shared = get_user_model().objects.create_user("shared_only", first_name="Shared", last_name="Teacher")
            self.a = CourseOffering.objects.get(subject__code="JLT0", organization=self.org)
            self.b = CourseOffering.objects.get(subject__code="JLT3", organization=self.org)
            self.share = JournalShare.objects.create(organization=self.org, offering=self.a, teacher=self.shared)

    def test_active_share_in_picker_and_filtered_list(self):
        self.client.force_login(self.coordinator)
        result = self.client.get(reverse("registrar:journal_list_teachers"), {"q": "Shared"}).json()
        self.assertEqual([r["id"] for r in result["results"]], [str(self.shared.pk)])
        response = self.client.get(reverse("registrar:journal_list"), {"teacher": self.shared.pk})
        self.assertEqual([o.pk for o in response.context["offerings"]], [self.a.pk])
        self.assertIn(str(self.shared.pk), [r["value"] for r in response.context["journal_teachers"]])

    def test_inactive_share_and_outside_faculty_do_not_appear(self):
        with bypass_rls():
            self.share.is_active = False
            self.share.save(update_fields=["is_active"])
            JournalShare.objects.create(organization=self.org, offering=self.b, teacher=self.shared)
        self.client.force_login(self.coordinator)
        result = self.client.get(reverse("registrar:journal_list_teachers"), {"q": "Shared"}).json()
        self.assertEqual(result["results"], [])
        response = self.client.get(reverse("registrar:journal_list"), {"teacher": self.shared.pk})
        self.assertEqual(list(response.context["offerings"]), [])

    def test_mismatched_tenant_share_is_ignored(self):
        from apps.organizations.models import Organization

        with bypass_rls():
            other = Organization.objects.create(name="Other", slug="shared-other", owner=self.owner)
            JournalShare.objects.filter(pk=self.share.pk).update(organization=other)
        self.client.force_login(self.corrector)
        self.assertEqual(
            self.client.get(reverse("registrar:journal_list_teachers"), {"q": "Shared"}).json()["results"], []
        )
        response = self.client.get(reverse("registrar:journal_list"), {"teacher": self.shared.pk})
        self.assertEqual(list(response.context["offerings"]), [])
