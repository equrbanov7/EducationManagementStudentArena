"""Təhlükəsizlik auditi 2026-10-05 — kataloq axtarışı kontakt icazəsi olmadan FİN/e-poçt üzrə getmir.

``search_q`` ``email`` və ``profile__fin`` sahələrini HƏR aktor üçün axtarırdı.
``people.view_contacts`` olmayan (kafedra müdiri, koordinator) həmin sütunları
görmür, amma «ad + FİN parçası» sorğusu ilə tələbənin FİN-ini simvol-simvol
bərpa edə bilirdi (axtarış oracle-ı).
"""

from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.accounts.services import people
from apps.accounts.services.people.constants import DEFAULT_PAGE_SIZE, STUDENT_SORT_OPTIONS
from apps.accounts.services.people.students import filtered_students_qs
from core.rls import bypass_rls

from .people_fixture import PeopleFixture

SECRET_FIN = "7XQ9ZZ1"


class PeopleContactSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fx = PeopleFixture()
        profile = cls.fx.student_a.profile
        profile.fin = SECRET_FIN
        profile.save(update_fields=["fin"])

    def _usernames(self, user, query):
        request = RequestFactory().get("/accounts/profile/")
        request.user = user
        request.organization = self.fx.org
        actor = people.resolve_actor(request)
        filters = people.parse_filters(
            {"q": query}, sort_options=STUDENT_SORT_OPTIONS, default_page_size=DEFAULT_PAGE_SIZE
        )
        with bypass_rls():
            return set(filtered_students_qs(actor=actor, filters=filters).values_list("username", flat=True))

    def test_actor_without_contacts_cannot_search_by_fin(self):
        self.assertNotIn(self.fx.student_a.username, self._usernames(self.fx.chair_a1, SECRET_FIN[:5]))

    def test_actor_without_contacts_still_finds_by_name(self):
        self.assertIn(self.fx.student_a.username, self._usernames(self.fx.chair_a1, "Ağayeva"))

    def test_actor_with_contacts_can_search_by_fin(self):
        self.assertIn(self.fx.student_a.username, self._usernames(self.fx.rector, SECRET_FIN[:5]))
