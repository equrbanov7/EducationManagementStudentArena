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

    def test_created_question_is_bound_to_active_organization(self):
        response = self.client.post(reverse("create_question"), {"question_text": "Sual", "answer_text": "Cavab"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Question.objects.get(author=self.teacher).organization_id, self.org.pk)


class QuestionTenantVisibilityTest(TestCase):
    """``visible_to_all`` sualı yalnız ÖZ təşkilatında görünür.

    Əvvəl ``Question``-da təşkilat yox idi: A universitetinin müəllimi «hamı görə
    bilər» seçəndə sual B universitetinin istifadəçilərinə də görünürdü.
    """

    def setUp(self):
        self.author = User.objects.create_user("secqt_author", "secqt_author@example.com", "StrongPass123!")
        self.peer = User.objects.create_user("secqt_peer", "secqt_peer@example.com", "StrongPass123!")
        self.outsider = User.objects.create_user("secqt_out", "secqt_out@example.com", "StrongPass123!")
        self.org = _org("SecQT Org A", self.author)
        self.other_org = _org("SecQT Org B", self.outsider)
        for user, org in ((self.author, self.org), (self.peer, self.org), (self.outsider, self.other_org)):
            Membership.objects.create(
                user=user, organization=org, role=org.roles.get(name="student"), is_primary=True, is_active=True
            )
        self.public_q = Question.objects.create(
            author=self.author, question_text="Org A ümumi sual", visible_to_all=True, organization=self.org
        )
        self.legacy_q = Question.objects.create(author=self.author, question_text="Köhnə sual", visible_to_all=True)

    def _visible(self, user):
        self.client.force_login(user)
        response = self.client.get(reverse("questions_i_can_see"))
        self.assertEqual(response.status_code, 200)
        return {q.pk for q in response.context["questions"]}

    def test_public_question_visible_inside_own_org(self):
        self.assertIn(self.public_q.pk, self._visible(self.peer))

    def test_public_question_hidden_from_other_tenant(self):
        visible = self._visible(self.outsider)
        self.assertNotIn(self.public_q.pk, visible)
        self.assertNotIn(self.legacy_q.pk, visible)

    def test_legacy_question_without_org_only_for_author_and_superadmin(self):
        self.assertNotIn(self.legacy_q.pk, self._visible(self.peer))
        self.assertIn(self.legacy_q.pk, self._visible(self.author))
        admin = User.objects.create_superuser("secqt_admin", "secqt_admin@example.com", "StrongPass123!")
        self.assertIn(self.legacy_q.pk, self._visible(admin))

    def test_can_user_see_respects_organization(self):
        self.assertTrue(self.public_q.can_user_see(self.peer, organization=self.org))
        self.assertFalse(self.public_q.can_user_see(self.outsider, organization=self.other_org))
        self.assertFalse(self.legacy_q.can_user_see(self.peer, organization=self.org))
