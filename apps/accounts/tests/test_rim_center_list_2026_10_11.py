"""RİM mərkəzi — ilk açılışda siyahı, hesab növü / vəziyyət filtrləri, sıralama, tab sayları (sahib 2026-10-11)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.accounts.tests.test_rim_center import RimCenterTestBase, add_member, make_user

User = get_user_model()


class RimListTests(RimCenterTestBase):
    def setUp(self):
        super().setUp()
        self.student = make_user("rim_student", first="Aysu", last="Babayeva", organization=self.org)
        add_member(self.student, self.org, self.student_role)
        self.staff = make_user("rim_staff", first="Orxan", last="Cəfərov", organization=self.org)
        add_member(self.staff, self.org, self.staff_role)
        self.orphan = make_user("rim_orphan", first="Zaur", last="Dadaşov", organization=self.org)
        add_member(self.orphan, self.org, self.student_role)
        # «Rolsuz»: üzvlük var amma aktiv deyil → idarə sahəsindən çıxır; ona görə yalnız silinmiş halda görünür.
        now = timezone.now()
        User.objects.filter(pk=self.student.pk).update(date_joined=now, last_login=None)
        User.objects.filter(pk=self.teacher.pk).update(date_joined=now - timedelta(days=30), last_login=now)
        User.objects.filter(pk=self.staff.pk).update(is_active=False, date_joined=now - timedelta(days=5))
        UserProfile.objects.filter(user=self.namesake).update(password_change_required=True)

    def _names(self, payload):
        return [row["username"] for row in payload["results"]]

    def test_empty_query_lists_newest_accounts_with_counts(self):
        self.login_operator()
        payload = self.client.get(reverse("accounts:rim_user_search"), {"counts": "1"}).json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["sort"], "recent")
        self.assertEqual(self._names(payload)[0], "rim_student")  # ən yeni
        self.assertNotIn("vice_rector_user", self._names(payload))  # iyerarxiya qapısı qalır
        counts = payload["counts"]
        self.assertEqual(counts["all"], payload["total"])
        self.assertEqual(counts["blocked"], 1)
        self.assertEqual(counts["active"] + counts["blocked"] + counts["archived"] + counts["deleted"], counts["all"])
        # Səhifə dəyişəndə saylar istənmir.
        self.assertIsNone(self.client.get(reverse("accounts:rim_user_search")).json()["counts"])

    def test_query_defaults_to_name_sort(self):
        self.login_operator()
        payload = self.search("Elvin").json()
        self.assertEqual(payload["sort"], "name")
        self.assertEqual(payload["total"], 2)

    def test_kind_filters(self):
        self.login_operator()
        cases = {
            "student": {"rim_student", "rim_orphan"},
            "teacher": {"myedu.worker.772", "myedu.worker.913"},
            "staff": {"rim_staff"},
        }
        for kind, expected in cases.items():
            with self.subTest(kind=kind):
                payload = self.search("", kind=kind).json()
                self.assertEqual(set(self._names(payload)), expected)
                self.assertEqual(payload["kind"], kind)
        self.assertEqual(self.search("", kind="bogus").json()["kind"], "")

    def test_flag_filters_and_sorts(self):
        self.login_operator()
        self.assertEqual(self._names(self.search("", flag="initial").json()), ["myedu.worker.913"])
        never = set(self._names(self.search("", flag="never").json()))
        self.assertIn("rim_student", never)
        self.assertNotIn("myedu.worker.772", never)
        self.assertEqual(self._names(self.search("", sort="last_login").json())[0], "myedu.worker.772")
        by_name = self._names(self.search("", sort="name").json())
        # Babayeva < Dadaşov (ASCII başlanğıc — «Ə»-nin yeri collation-dan asılıdır).
        self.assertLess(by_name.index("rim_student"), by_name.index("rim_orphan"))
        self.assertEqual(self.search("", sort="bogus").json()["sort"], "recent")
