"""Təhlükəsizlik auditi 2026-10-05 — blog sualının tenant görünürlüyü.

WP9a (2026-10-10): «Suallar» səhifələri və ``QuestionForm`` silindi (giriş nöqtəsi
yox idi); model səviyyəli görünürlük qaydası (``Question.visible_q`` /
``can_user_see``) qalır və burada yoxlanılır.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.blog.models import Question
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _org(name, owner):
    return Organization.objects.create(
        name=name, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )


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
        # Əvvəl `questions/` səhifəsinin kontekstindən oxunurdu — eyni filtr (aktiv təşkilat).
        organization = Organization.objects.filter(memberships__user=user, memberships__is_active=True).first()
        return set(
            Question.objects.filter(Question.visible_q(user, organization)).distinct().values_list("pk", flat=True)
        )

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
