"""«Yük bölgüsü» — «Bütün kafedralar» axtarışı (sahib 2026-11-04).

Müqavilə (``rows?chair=all``, bax ``services/all_chairs.py``):
  * baxış əhatəsindəki BÜTÜN kafedraların sətirləri bir siyahıda, hər sətirdə kafedra adı (+ fakültə, status);
  * fənn / müəllim axtarışı kafedralar üzrə işləyir; ``limit`` / ``offset`` / ``has_more`` ardıcıl və təkrarsız;
  * sorğu sayı dilimin ölçüsündən asılı deyil (N+1 yoxdur);
  * yalnız oxu: ``can_edit`` / ``edit_url`` yalnız bölmənin idarə əhatəsindəki kafedrada, digərləri «yalnız baxış»;
  * tək kafedralı müdir öz kafedrasından kənara çıxmır və seçicidə variantı görmür; açarsız aktor 403.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.registrar.models import Subject
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment
from core.constants import OrgUnitType, RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()

CHAIR_PERMS = ["workload.view", "workload.manage", "workload.distribute", "workload.report"]


class AllChairsSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("allch1104")
        cls.stack = make_structure(cls.org, code="ALC")
        cls.chair_a = cls.stack["chair"]
        cls.chair_b = OrgUnit.objects.create(
            organization=cls.org,
            name="Statistika kafedrası",
            slug="allch1104-chair-b",
            unit_type=OrgUnitType.CHAIR,
            parent=cls.stack["faculty"],
        )
        cls.task_a = make_task(cls.org, cls.chair_a, status=TaskStatus.APPROVED)
        cls.task_b = make_task(cls.org, cls.chair_b, status=TaskStatus.APPROVED)

        def row(task, code, name):
            subject = Subject.objects.create(organization=cls.org, code=code, name=name, ects=6)
            return make_row(task, {**cls.stack, "subject": subject}, lecture_total=30, seminar_total=15)

        cls.rows_a = [row(cls.task_a, "ALC201", "Riyazi analiz"), row(cls.task_a, "ALC202", "Fizika")]
        cls.rows_a.append(row(cls.task_a, "ALC203", "Proqramlaşdırma"))
        cls.rows_b = [row(cls.task_b, "ALC301", "Riyazi statistika"), row(cls.task_b, "ALC302", "Ehtimal nəzəriyyəsi")]
        cls.kamran = User.objects.create_user("alc_kamran", "alc_kamran@x.test", "pw", first_name="Kamran")
        cls.leyla = User.objects.create_user("alc_leyla", "alc_leyla@x.test", "pw", first_name="Leyla")
        for row_, teacher in ((cls.rows_b[1], cls.kamran), (cls.rows_a[0], cls.leyla), (cls.rows_a[1], cls.leyla)):
            TeacherAssignment.objects.create(
                organization=cls.org, row=row_, teacher=teacher, activity=Activity.LECTURE, hours=30
            )

        # RİM: bütün universitet (ORGANIZATION əhatəsi).
        cls.rim = User.objects.create_user("alc_rim", "alc_rim@x.test", "pw")
        activate_member(cls.org, cls.rim, "rim_workload", permissions=CHAIR_PERMS, level=80)
        # Kafedra A-nın müdiri — yalnız öz kafedrası.
        cls.head_a = User.objects.create_user("alc_head_a", "alc_head_a@x.test", "pw")
        activate_member(
            cls.org,
            cls.head_a,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.chair_a,
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        # Universitet üzrə BAXIŞ, idarə isə yalnız kafedra A-da (məs. prorektorluq + kafedra müdirliyi).
        cls.viewer = User.objects.create_user("alc_viewer", "alc_viewer@x.test", "pw")
        activate_member(cls.org, cls.viewer, "org_workload_viewer", permissions=["workload.view"], level=60)
        activate_member(
            cls.org,
            cls.viewer,
            "chair_head",
            permissions=CHAIR_PERMS,
            scope_unit=cls.chair_a,
            level=70,
            scope_type=RoleScopeType.UNIT,
        )
        cls.teacher = User.objects.create_user("alc_teacher", "alc_teacher@x.test", "pw")
        activate_member(
            cls.org,
            cls.teacher,
            "teacher",
            permissions=TEACHER_PERMS + ["workload.object"],
            scope_unit=cls.chair_a,
            level=50,
            scope_type=RoleScopeType.COURSE,
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _get(self, user, status=200, **params):
        self._login(user)
        response = self.client.get(reverse("workload:rows"), {"chair": "all", "year": YEAR, **params})
        self.assertEqual(response.status_code, status, response.content[:300])
        return response.json()

    # ── məzmun ─────────────────────────────────────────────────────────────
    def test_rows_from_every_chair_carry_the_chair_label(self):
        payload = self._get(self.rim, limit=30)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["all_chairs"])
        self.assertIsNone(payload["task"])
        self.assertEqual(payload["total"], 5)
        self.assertFalse(payload["has_more"])
        by_chair = {}
        for item in payload["rows"]:
            by_chair.setdefault(item["chair_id"], set()).add(item["subject"])
            self.assertEqual(item["faculty_name"], self.stack["faculty"].name)
            self.assertIn(item["chair_name"], {self.chair_a.name, self.chair_b.name})
            self.assertEqual(item["task_status"], TaskStatus.APPROVED)
        self.assertEqual(set(by_chair), {str(self.chair_a.pk), str(self.chair_b.pk)})
        self.assertIn("Riyazi statistika", by_chair[str(self.chair_b.pk)])

    def test_subject_search_spans_chairs(self):
        payload = self._get(self.rim, limit=30, q="Riyazi")
        self.assertEqual(payload["total"], 2)
        self.assertEqual({item["chair_id"] for item in payload["rows"]}, {str(self.chair_a.pk), str(self.chair_b.pk)})

    def test_teacher_search_spans_chairs(self):
        payload = self._get(self.rim, limit=30, q="Kamran")
        self.assertEqual([item["id"] for item in payload["rows"]], [str(self.rows_b[1].pk)])
        self.assertEqual(payload["rows"][0]["chair_name"], self.chair_b.name)

    def test_pagination_is_ordered_and_without_duplicates(self):
        first = self._get(self.rim, limit=2, offset=0)
        self.assertEqual((first["total"], first["next_offset"], first["has_more"]), (5, 2, True))
        second = self._get(self.rim, limit=2, offset=2)
        self.assertEqual((second["next_offset"], second["has_more"]), (4, True))
        third = self._get(self.rim, limit=2, offset=4)
        self.assertEqual((len(third["rows"]), third["has_more"]), (1, False))
        ids = [item["id"] for page in (first, second, third) for item in page["rows"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {str(row.pk) for row in self.rows_a + self.rows_b})

    def test_query_count_does_not_grow_with_page_size(self):
        self._login(self.rim)
        url = reverse("workload:rows")
        self.client.get(url, {"chair": "all", "year": YEAR, "limit": 1})  # sessiya / əhatə keşi isinsin
        # İki dilim də müəllimli təyinat daşıyır (prefetch-in müəllim sorğusu hər ikisində olsun).
        with CaptureQueriesContext(connection) as small:
            self.client.get(url, {"chair": "all", "year": YEAR, "limit": 1})
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(url, {"chair": "all", "year": YEAR, "limit": 5})
        self.assertEqual(len(response.json()["rows"]), 5)
        self.assertEqual(len(large.captured_queries), len(small.captured_queries))

    # ── icazə ──────────────────────────────────────────────────────────────
    def test_rows_are_editable_only_through_their_own_chair(self):
        payload = self._get(self.viewer, limit=30)
        self.assertEqual(payload["total"], 5)
        for item in payload["rows"]:
            if item["chair_id"] == str(self.chair_a.pk):
                self.assertTrue(item["can_edit"])
                self.assertIn(f"chair={self.chair_a.pk}", item["edit_url"])
                self.assertIn(f"row={item['id']}", item["edit_url"])
                self.assertIn("section=workload-distribution", item["edit_url"])
            else:
                self.assertFalse(item["can_edit"])
                self.assertEqual(item["edit_url"], "")

    def test_single_chair_head_stays_inside_own_chair(self):
        payload = self._get(self.head_a, limit=30)
        self.assertEqual({item["chair_id"] for item in payload["rows"]}, {str(self.chair_a.pk)})
        self.assertEqual(payload["total"], 3)
        # Köhnə (tək kafedra) davranışı dəyişmir.
        response = self.client.get(reverse("workload:rows"), {"chair": str(self.chair_a.pk), "year": YEAR})
        self.assertEqual(response.json()["task"]["id"], str(self.task_a.pk))

    def test_actor_without_section_keys_is_denied(self):
        payload = self._get(self.teacher, status=403)
        self.assertFalse(payload["ok"])

    # ── bölmə ──────────────────────────────────────────────────────────────
    def _section_html(self, user):
        self._login(user)
        response = self.client.get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "workload-distribution"})
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["html"]

    def test_chair_picker_offers_all_chairs_only_with_two_or_more_chairs(self):
        html = self._section_html(self.rim)
        self.assertIn('<option value="all"', html)
        self.assertIn("data-wl-all-note", html)
        self.assertIn("data-wl-chair-only", html)
        self.assertNotIn('<option value="all"', self._section_html(self.head_a))
