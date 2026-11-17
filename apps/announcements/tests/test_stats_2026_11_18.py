"""«Elan statistikası» (sahib 2026-11-18): kim görüb / oxuyub / görməyib — bölgü, filtrlər, şəxs siyahısı, ixrac.

Dünya (``world.py``): F1 → Kafedra A → Qrup G1 (s1, müəllim t1 kafedrada), F2 → Qrup G2 (s2).
Elan: tələbələr + müəllimlər. s1 popup-u görüb, t1 oxuyub, s2 heç nə.

Performans: sorğu sayı istifadəçi sayından asılı deyil (bölgü, siyahı); mövcud idarə siyahısı əlavə sorğu almır.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.announcements.models import AnnouncementReceipt
from apps.announcements.services import stats
from apps.registrar.models import Curriculum, Program
from core.rls import bypass_rls

from .world import _record, build_world, client_for, make_announcement, member

SUMMARY = "announcements:stats_summary"
PEOPLE = "announcements:stats_people"


def _receipt(item, user, **fields):
    with bypass_rls():
        AnnouncementReceipt.objects.create(organization=item.organization, announcement=item, user=user, **fields)


class StatsServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annst")
        cls.item = make_announcement(cls.w, title="Statistika elanı", families=["students", "teachers"])
        now = timezone.now()
        _receipt(cls.item, cls.w["s1"], popup_seen_at=now)
        _receipt(cls.item, cls.w["t1"], read_at=now)
        _receipt(cls.item, cls.w["dean"], read_at=now)  # hədəfdən kənar (staff) — sayılmır

    def _summary(self, **kwargs):
        with bypass_rls():
            return stats.summary(self.item, **kwargs)

    def _rows(self, data):
        return {row["label"]: (row["total"], row["seen"], row["read"], row["unseen"]) for row in data["rows"]}

    def test_totals_are_relative_to_target_audience(self):
        totals = self._summary()["totals"]
        self.assertEqual((totals["total"], totals["seen"], totals["read"], totals["unseen"]), (3, 1, 1, 1))
        self.assertEqual((totals["seen_pct"], totals["reached_pct"], totals["unseen_pct"]), (33, 67, 33))

    def test_faculty_dimension_rolls_groups_and_chairs_up(self):
        rows = self._rows(self._summary(dimension="faculty"))
        self.assertEqual(rows["Fakulte F1"], (2, 1, 1, 0))  # s1 (G1) + t1 (Kafedra A)
        self.assertEqual(rows["Fakulte F2"], (1, 0, 0, 1))

    def test_group_chair_and_role_dimensions(self):
        groups = self._rows(self._summary(dimension="group"))
        self.assertEqual(groups["Qrup G1"], (1, 1, 0, 0))
        self.assertEqual(groups["Qrup G2"], (1, 0, 0, 1))
        self.assertEqual(groups["Bölmə göstərilməyib"], (1, 0, 1, 0))  # müəllim qrupa bağlı deyil
        chairs = self._rows(self._summary(dimension="chair"))
        self.assertEqual(chairs["Kafedra A"], (2, 1, 1, 0))  # G1 kafedranın altındadır (test dünyası)
        roles = self._rows(self._summary(dimension="role"))
        self.assertEqual(roles["Tələbələr"], (2, 1, 0, 1))
        self.assertEqual(roles["Müəllimlər"], (1, 0, 1, 0))

    def test_role_and_unit_filters(self):
        self.assertEqual(self._summary(family="teachers")["totals"]["total"], 1)
        self.assertEqual(self._summary(unit=str(self.w["f2"].pk))["totals"]["total"], 1)
        self.assertEqual(self._summary(unit=str(self.w["f1"].pk), family="students")["totals"]["total"], 1)

    def test_people_statuses_search_and_labels(self):
        with bypass_rls():
            unseen = stats.people_page(self.item, status="unseen")
            seen = stats.people_page(self.item, status="seen")
            read = stats.people_page(self.item, status="read")
            found = stats.people_page(self.item, q=self.w["t1"].username)
        self.assertEqual([row["pk"] for row in unseen["items"]], [self.w["s2"].pk])
        self.assertEqual([row["pk"] for row in seen["items"]], [self.w["s1"].pk])
        self.assertEqual([row["pk"] for row in read["items"]], [self.w["t1"].pk])
        self.assertEqual(found["total"], 1)
        row = found["items"][0]
        self.assertEqual(
            (row["unit_label"], row["faculty_label"], row["family_label"]), ("Kafedra A", "Fakulte F1", "Müəllimlər")
        )


class StatsEndpointsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annsx")
        cls.item = make_announcement(cls.w, title="Hamıya elan", families=["students", "teachers"], show_as_popup=True)
        _receipt(cls.item, cls.w["s1"], popup_seen_at=timezone.now())

    def _client(self, user=None):
        return client_for(self.w["org"], user or self.w["owner"])

    def test_page_is_light_and_lists_the_announcement(self):
        client = self._client()
        client.get(reverse("announcements:stats"))
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(reverse("announcements:stats"), {"elan": self.item.pk})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Hamıya elan", html)
        self.assertIn("data-annst-summary", html)
        self.assertIn("data-live-search-url", html)
        self.assertNotIn("<style", html.split("data-annst-root")[1])
        stats_tables = [q["sql"] for q in ctx.captured_queries if "announcements_announcementreceipt" in q["sql"]]
        self.assertEqual(stats_tables, [])  # aqreqat səhifədə deyil — tənbəl JSON-dadır

    def test_summary_and_people_query_counts_do_not_grow_with_audience(self):
        client = self._client()
        params = {"elan": str(self.item.pk), "dim": "faculty"}
        client.get(reverse(SUMMARY), params)
        with CaptureQueriesContext(connection) as before_summary:
            client.get(reverse(SUMMARY), params)
        with CaptureQueriesContext(connection) as before_people:
            client.get(reverse(PEOPLE), params)
        with bypass_rls():
            program = Program.objects.get(organization=self.w["org"])
            curriculum = Curriculum.objects.get(organization=self.w["org"])
            for index in range(8):
                student = member(self.w["org"], f"annsx_more{index}", "student")
                _record(self.w["org"], student, self.w["g2" if index % 2 else "g1"], program, curriculum)
                _receipt(self.item, student, read_at=timezone.now())
        with CaptureQueriesContext(connection) as after_summary:
            payload = client.get(reverse(SUMMARY), params).json()
        with CaptureQueriesContext(connection) as after_people:
            people = client.get(reverse(PEOPLE), params).json()
        self.assertEqual(payload["totals"]["total"], 11)
        self.assertEqual(people["total"], 11)
        self.assertEqual(len(before_summary.captured_queries), len(after_summary.captured_queries))
        self.assertEqual(len(before_people.captured_queries), len(after_people.captured_queries))

    def test_permissions(self):
        student = self._client(self.w["s1"])
        self.assertEqual(student.get(reverse("announcements:stats")).status_code, 403)
        self.assertEqual(student.get(reverse(SUMMARY), {"elan": self.item.pk}).status_code, 403)
        self.assertEqual(student.get(reverse(PEOPLE), {"elan": self.item.pk}).status_code, 403)
        self.assertEqual(student.get(reverse("announcements:stats_units"), {"q": "F"}).status_code, 403)
        self.assertEqual(student.get(reverse("announcements:stats_export"), {"elan": self.item.pk}).status_code, 403)
        dean = self._client(self.w["dean"])  # təşkilat səviyyəli elan dekanın əhatəsindən kənardır
        self.assertEqual(dean.get(reverse(SUMMARY), {"elan": self.item.pk}).status_code, 404)

    def test_unit_search_and_export(self):
        client = self._client()
        results = client.get(reverse("announcements:stats_units"), {"q": "G2"}).json()["results"]
        self.assertEqual([row["id"] for row in results], [str(self.w["g2"].pk)])
        response = client.get(reverse("announcements:stats_export"), {"elan": self.item.pk, "dim": "group"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertTrue(response.content.startswith(b"PK"))

    def test_entry_points_for_managers_only(self):
        manage_html = self._client().get(reverse("announcements:manage_list")).content.decode()
        stats_url = reverse("announcements:stats")
        self.assertIn(f'href="{stats_url}"', manage_html)
        self.assertIn(f"{stats_url}?elan={self.item.pk}", manage_html)  # kartdan statistikaya
        cabinet = self._client().get("/accounts/profile/api/sections/announcements/").json()["html"]
        self.assertIn(stats_url, cabinet)
        student_cabinet = self._client(self.w["s1"]).get("/accounts/profile/api/sections/announcements/").json()["html"]
        self.assertNotIn(stats_url, student_cabinet)


class StatsEdgeCasesTest(TestCase):
    """Review 2026-11-18: çox üzvlüklü müəllim hədəf bölmədə sayılır; boş auditoriya 500 vermir."""

    @classmethod
    def setUpTestData(cls):
        from apps.organizations.models import Membership

        cls.w = build_world("annse")
        with bypass_rls():
            # t1-in əsas üzvlüyü Kafedra A-dadır; F2-də əlavə (əsas olmayan) üzvlüyü var.
            Membership.objects.create(
                user=cls.w["t1"],
                organization=cls.w["org"],
                role=cls.w["org"].roles.get(name="teacher"),
                scope_unit=cls.w["f2"],
                is_primary=False,
                is_active=True,
            )
        cls.item = make_announcement(cls.w, title="F2 müəllimləri", families=["teachers"], units=[cls.w["f2"].pk])

    def test_secondary_membership_counts_in_targeted_unit(self):
        with bypass_rls():
            data = stats.summary(self.item, dimension="faculty")
            filtered = stats.summary(self.item, unit=str(self.w["f2"].pk))
        self.assertEqual([(row["label"], row["total"]) for row in data["rows"]], [("Fakulte F2", 1)])
        self.assertEqual(filtered["totals"]["total"], 1)

    def test_empty_audience_does_not_crash(self):
        from apps.announcements.models import Announcement

        with bypass_rls():
            Announcement.objects.filter(pk=self.item.pk).update(audience_families=[])
            self.item.refresh_from_db()
        client = client_for(self.w["org"], self.w["owner"])
        payload = client.get(reverse(SUMMARY), {"elan": self.item.pk}).json()
        self.assertEqual(payload["totals"]["total"], 0)
        response = client.get(reverse("announcements:stats_export"), {"elan": self.item.pk})
        self.assertEqual(response.status_code, 200)
