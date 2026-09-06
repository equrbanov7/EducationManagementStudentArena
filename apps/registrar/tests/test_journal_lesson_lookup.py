"""Dərs modalının axtarışlı/lazy müəllim seçicisi (QA 2026-09-05 P3-13).

Əvvəllər `lesson_teacher_choices` nəticəsi (təşkilatın BÜTÜN dərs deyən
müəllimləri) hər jurnal səhifəsi yüklənməsində <option> kimi HTML-ə
bişirilirdi. Bu test qıfıllayır ki:
  * jurnal detal səhifəsi ARTIQ namizədlərin tam siyahısını HTML-ə YAZMIR
    (yalnız cari müəllimin adı görünə bilər — o da AJAX ilə tamamlanır);
  * yeni `journal_lesson_teacher_search` endpoint-i EMSSearchableSelect
    müqaviləsinə uyğun axtarır/səhifələyir/`resolve` edir;
  * icazə qapısı jurnal SƏHİFƏSİ ilə EYNİDİR (əlaqəsiz üzv 404 alır)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class JournalLessonTeacherLookupTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jll_owner", "jll_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JLL Univ",
                slug="jll-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="jll-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.teachers = []
            for i in range(3):
                teacher = User.objects.create_user(
                    f"jll_teacher_{i}", f"jll_teacher_{i}@qku.edu.az", "pw", first_name=f"Ada{i}", last_name="Named"
                )
                Membership.objects.create(
                    user=teacher,
                    organization=cls.org,
                    role=cls.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
                subject = Subject.objects.create(organization=cls.org, code=f"JLL{i:03d}", name=f"Fənn {i}")
                offering = services.get_or_create_offering(
                    organization=cls.org, subject=subject, period=cls.period, group=cls.group
                )
                offering.instructor = teacher
                offering.save(update_fields=["instructor"])
                cls.teachers.append(teacher)
                if i == 0:
                    cls.offering = offering
            cls.student = User.objects.create_user("jll_student", "jll_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_modal_no_longer_bakes_in_the_full_teacher_option_list(self):
        resp = self._client(self.teachers[0]).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        html = resp.content.decode()
        self.assertIn("data-jd-lesson-instructor", html)
        self.assertIn("data-search-url=", html)
        # Köhnə <select><option> siyahısı silinib — digər müəllimlərin adı heç
        # birbaşa render olunmamalıdır (yalnız AJAX cavabında gələ bilər).
        self.assertNotIn(">Ada1 Named<", html)
        self.assertNotIn(">Ada2 Named<", html)

    def test_search_endpoint_filters_by_name(self):
        resp = self._client(self.teachers[0]).get(
            reverse("registrar:journal_lesson_teacher_search", args=[self.offering.id]), {"q": "Ada1"}
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual([row["text"] for row in payload["results"]], ["Ada1 Named"])
        self.assertFalse(payload["has_more"])

    def test_search_endpoint_paginates(self):
        client = self._client(self.teachers[0])
        resp = client.get(
            reverse("registrar:journal_lesson_teacher_search", args=[self.offering.id]), {"limit": 2, "offset": 0}
        )
        payload = resp.json()
        self.assertEqual(len(payload["results"]), 2)
        self.assertTrue(payload["has_more"])
        resp2 = client.get(
            reverse("registrar:journal_lesson_teacher_search", args=[self.offering.id]), {"limit": 2, "offset": 2}
        )
        payload2 = resp2.json()
        self.assertEqual(len(payload2["results"]), 1)
        self.assertFalse(payload2["has_more"])

    def test_resolve_returns_the_single_matching_candidate(self):
        resp = self._client(self.teachers[0]).get(
            reverse("registrar:journal_lesson_teacher_search", args=[self.offering.id]),
            {"resolve": str(self.teachers[1].id)},
        )
        payload = resp.json()
        self.assertEqual(payload["results"], [{"id": str(self.teachers[1].id), "text": "Ada1 Named"}])

    def test_resolve_unknown_id_returns_empty(self):
        resp = self._client(self.teachers[0]).get(
            reverse("registrar:journal_lesson_teacher_search", args=[self.offering.id]), {"resolve": "999999"}
        )
        self.assertEqual(resp.json(), {"results": [], "has_more": False})

    def test_lookup_denies_org_member_unrelated_to_the_offering(self):
        resp = self._client(self.student).get(
            reverse("registrar:journal_lesson_teacher_search", args=[self.offering.id])
        )
        self.assertEqual(resp.status_code, 404)

    def test_lookup_denies_anonymous(self):
        resp = Client().get(reverse("registrar:journal_lesson_teacher_search", args=[self.offering.id]))
        self.assertEqual(resp.status_code, 302)  # login_required → redirect
