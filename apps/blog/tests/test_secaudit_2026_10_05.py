"""Təhlükəsizlik auditi 2026-10-05 — blog sualı ``visible_users`` seçicisi.

``QuestionForm.visible_users`` default queryset-i ``User.objects.all()`` idi:
istənilən müəllim «Sual yarat» səhifəsində BÜTÜN tenant-ların istifadəçi
siyahısını görürdü və POST ilə başqa universitetin istifadəçisini əlavə edə
bilirdi. İndi seçim yalnız aktiv təşkilatın aktiv üzvləri ilə məhdudlaşır.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.blog.models import Question
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _org(name, owner):
    return Organization.objects.create(
        name=name, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )


class QuestionVisibleUsersScopeTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("secq_teacher", "secq_teacher@example.com", "StrongPass123!")
        self.teacher.profile.role = "teacher"
        self.teacher.profile.save(update_fields=["role", "updated_at"])
        self.colleague = User.objects.create_user("secq_colleague", "secq_colleague@example.com", "StrongPass123!")
        self.outsider = User.objects.create_user("secq_outsider", "secq_outsider@example.com", "StrongPass123!")

        self.org = _org("SecQ Org A", self.teacher)
        self.other_org = _org("SecQ Org B", self.outsider)
        for user, org, role in (
            (self.teacher, self.org, "teacher"),
            (self.colleague, self.org, "student"),
            (self.outsider, self.other_org, "student"),
        ):
            Membership.objects.create(
                user=user, organization=org, role=org.roles.get(name=role), is_primary=True, is_active=True
            )
        self.client.force_login(self.teacher)

    def test_form_lists_only_active_org_members(self):
        response = self.client.get(reverse("create_question"))
        self.assertEqual(response.status_code, 200)
        choices = set(response.context["form"].fields["visible_users"].queryset.values_list("pk", flat=True))
        self.assertIn(self.colleague.pk, choices)
        self.assertNotIn(self.outsider.pk, choices)

    def test_cannot_grant_question_to_user_of_other_tenant(self):
        response = self.client.post(
            reverse("create_question"),
            {"question_text": "Sual", "answer_text": "Cavab", "visible_users": [self.outsider.pk]},
        )
        self.assertEqual(response.status_code, 200)  # forma yenidən göstərilir (invalid)
        self.assertFalse(Question.objects.filter(visible_users=self.outsider).exists())

    def test_can_grant_question_to_org_member(self):
        response = self.client.post(
            reverse("create_question"),
            {"question_text": "Sual", "answer_text": "Cavab", "visible_users": [self.colleague.pk]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Question.objects.filter(visible_users=self.colleague).exists())
