"""«Alt qrupdan tələbə əlavə et» axtarışı «Soyad Ad Ata adı» göstərir, ata adı ilə tapır (sahib 2026-11-15)."""

from django.urls import reverse

from apps.accounts.models import UserProfile
from core.rls import bypass_rls

from .test_guest_roster import _GuestRosterBase


class GuestStudentSearchLabelTests(_GuestRosterBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.guest.first_name, cls.guest.last_name = "Nigar", "Həsənova"
            cls.guest.save(update_fields=["first_name", "last_name"])
            profile, _ = UserProfile.objects.get_or_create(user=cls.guest)
            profile.patronymic = "Elşən"
            profile.save(update_fields=["patronymic"])

    def _search(self, **params):
        client = self._client(self.coordinator)
        url = reverse("registrar:journal_guest_student_search", args=[self.offering.id])
        return client.get(url, {"group": str(self.group2.id), **params}).json()["results"]

    def test_label_is_surname_name_patronymic(self):
        row = next(r for r in self._search() if r["id"] == str(self.guest.id))
        self.assertEqual(row["text"], "Həsənova Nigar Elşən")

    def test_search_by_patronymic(self):
        self.assertEqual([r["id"] for r in self._search(q="Elşən")], [str(self.guest.id)])
