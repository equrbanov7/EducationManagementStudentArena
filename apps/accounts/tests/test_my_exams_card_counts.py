"""«İmtahanlarım» kart sayğacları — dəyər ekvivalentliyi (Faza 7).

Sayğaclar (sual / apellyasiya / icazəli qrup / icazəli istifadəçi) əvvəllər BİR
sorğuda dörd ``Count(..., distinct=True)`` kimi hesablanırdı. Eyni sorğuda bir
neçə çoxdəyərli əlaqə üzrə aqreqasiya dekart hasili yaradır: hər JOIN sətirləri
çoxaldır, ``DISTINCT`` isə şişmiş aralıq nəticəni sonradan təmizləyir.

Sayğaclar korrelyasiyalı alt-sorğulara keçirildi. Bu testlər dəyərlərin
DƏYİŞMƏDİYİNİ qoruyur — xüsusən çoxaldıcı hal: eyni imtahanda həm çoxlu sual,
həm çoxlu icazəli istifadəçi olanda köhnə `distinct`-siz yazılış şişmiş rəqəm
verərdi.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.exams.models import Exam, ExamQuestion, StudentGroup
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"


class MyExamsCardCountsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("cc_owner", "cc_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Counts Univ",
            slug="counts-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="teacher",
            defaults={
                "display_name": "Teacher",
                "level": 60,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": [],
                "is_system": False,
                "is_active": True,
            },
        )
        cls.teacher = User.objects.create_user("cc_teacher", "cc_teacher@qku.edu.az", PASSWORD)
        Membership.objects.create(user=cls.teacher, organization=cls.org, role=role, is_primary=True, is_active=True)

        cls.exam = Exam.objects.create(
            title="Counts exam",
            author=cls.teacher,
            organization=cls.org,
            exam_type="written",
            is_active=True,
        )
        # 3 aktiv + 1 deaktiv sual: filtr işləməlidir.
        for order in range(1, 4):
            ExamQuestion.objects.create(exam=cls.exam, text=f"Q{order}", order=order, points=10, is_active=True)
        ExamQuestion.objects.create(exam=cls.exam, text="Q-off", order=4, points=10, is_active=False)

        # 2 icazəli istifadəçi — sual sayı ilə birlikdə çoxaldıcı hal yaradır.
        cls.students = []
        for index in range(2):
            student = User.objects.create_user(f"cc_s{index}", f"cc_s{index}@qku.edu.az", PASSWORD)
            cls.students.append(student)
            cls.exam.allowed_users.add(student)

        # 2 icazəli tələbə qrupu.
        for index in range(2):
            group = StudentGroup.objects.create(teacher=cls.teacher, organization=cls.org, name=f"Group {index}")
            cls.exam.allowed_groups.add(group)

    def _exam_from_context(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile") + "?section=my-exams")
        self.assertEqual(response.status_code, 200)
        exams = {exam.pk: exam for exam in response.context["my_exams"]}
        self.assertIn(self.exam.pk, exams)
        return exams[self.exam.pk]

    def test_question_count_excludes_inactive_questions(self):
        self.assertEqual(self._exam_from_context().card_question_count, 3)

    def test_allowed_user_and_group_counts_are_not_multiplied(self):
        """Çoxaldıcı hal: 3 sual × 2 istifadəçi × 2 qrup birləşsəydi 12 çıxardı."""
        exam = self._exam_from_context()

        self.assertEqual(exam.card_allowed_user_count, 2)
        self.assertEqual(exam.card_allowed_group_count, 2)

    def test_appeal_count_is_zero_without_appeals(self):
        self.assertEqual(self._exam_from_context().card_appeal_count, 0)

    def test_counts_match_direct_orm_values(self):
        exam = self._exam_from_context()

        self.assertEqual(exam.card_question_count, self.exam.questions.filter(is_active=True).count())
        self.assertEqual(exam.card_allowed_user_count, self.exam.allowed_users.count())
        self.assertEqual(exam.card_allowed_group_count, self.exam.allowed_groups.count())
        self.assertEqual(exam.card_appeal_count, self.exam.appeals.count())


class MyExamsPaginationTest(TestCase):
    """Səhifələmə KPI rəqəmlərini pozmamalıdır.

    Bu, səhifələmənin əsas riski idi: dashboard qruplaşması Python tərəfdə,
    göstərilən siyahı üzərində qurulur. Səhifələmə əlavə edilib sayğaclar da
    həmin siyahıdan hesablansaydı, 150 aktiv imtahanı olan müəllim «Aktiv: 12»
    görərdi. Ona görə sayğaclar SQL aqreqatı ilə BÜTÜN dəst üzrə hesablanır.
    """

    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("pg_teacher", "pg_teacher@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Pagination Univ",
            slug="pagination-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.teacher,
            status="active",
            is_active=True,
        )
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="teacher",
            defaults={
                "display_name": "Teacher",
                "level": 60,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": [],
                "is_system": False,
                "is_active": True,
            },
        )
        Membership.objects.create(user=cls.teacher, organization=cls.org, role=role, is_primary=True, is_active=True)
        # 20 aktiv + 5 qaralama = 25; səhifə ölçüsü 12.
        cls.active_total = 20
        cls.draft_total = 5
        for index in range(cls.active_total):
            Exam.objects.create(
                title=f"Aktiv {index}",
                author=cls.teacher,
                organization=cls.org,
                exam_type="written",
                is_active=True,
            )
        for index in range(cls.draft_total):
            Exam.objects.create(
                title=f"Qaralama {index}",
                author=cls.teacher,
                organization=cls.org,
                exam_type="written",
                is_active=False,
            )

    def _page(self, number=None):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        url = reverse("accounts:profile") + "?section=my-exams"
        if number:
            url += f"&exam_page={number}"
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        return response

    def test_first_page_shows_only_page_size_items(self):
        from apps.accounts.views.profile._sections.exams import MY_EXAMS_PAGE_SIZE

        response = self._page()

        self.assertEqual(len(response.context["my_exams"]), MY_EXAMS_PAGE_SIZE)

    def test_kpi_counts_cover_the_whole_set_not_just_the_page(self):
        dashboard = self._page().context["my_exams_dashboard"]

        self.assertEqual(dashboard["status_counts"]["active"], self.active_total)
        self.assertEqual(dashboard["status_counts"]["draft"], self.draft_total)
        self.assertEqual(dashboard["status_counts"]["all"], self.active_total + self.draft_total)
        self.assertEqual(dashboard["total"], self.active_total + self.draft_total)

    def test_second_page_reports_the_same_totals(self):
        first = self._page().context["my_exams_dashboard"]["status_counts"]
        second = self._page(2).context["my_exams_dashboard"]["status_counts"]

        self.assertEqual(first, second)

    def test_pagination_object_is_exposed_with_filters_preserved(self):
        response = self._page()
        page_obj = response.context["my_exams_page_obj"]

        self.assertTrue(page_obj.has_next())
        self.assertIn("section=my-exams", response.context["my_exams_pagination_query"])

    def test_search_filter_narrows_counts_too(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:profile") + "?section=my-exams&exam_q=Qaralama")

        counts = response.context["my_exams_dashboard"]["status_counts"]
        self.assertEqual(counts["all"], self.draft_total)
        self.assertEqual(counts["active"], 0)


class MyExamsServerSideFilterTest(TestCase):
    """Səhifələmə klient-tərəf filtri sındırmışdı — filtrlər serverdə olmalıdır.

    Deploy-öncəsi əks-yoxlamanın tapdığı regressiya: səhifələmədən sonra DOM-da
    yalnız 12 kart qalır, toolbar isə filtri klient tərəfdə tətbiq edirdi. Yəni
    3-cü səhifədəki imtahanı axtaranda «tapılmadı» yazılırdı — imtahan mövcud
    olsa belə. Server filtrləri (`exam_q`, `exam_type`) hələ də var idi, sadəcə
    JS `preventDefault()` etdiyi üçün onlara heç vaxt çatmaq olmurdu.

    Bu testlər server filtrlərinin — o cümlədən YENİ `exam_status` filtrinin —
    tam dəst üzərində işlədiyini qoruyur.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sf_owner", "sf_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Filter Univ",
            slug="filter-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="teacher",
            defaults={
                "display_name": "Teacher",
                "level": 60,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": [],
                "is_system": False,
                "is_active": True,
            },
        )
        cls.teacher = User.objects.create_user("sf_teacher", "sf_teacher@qku.edu.az", PASSWORD)
        Membership.objects.create(user=cls.teacher, organization=cls.org, role=role, is_primary=True, is_active=True)

        # 20 aktiv + 5 qaralama → 25 imtahan, səhifə ölçüsü 12 (3 səhifə).
        for i in range(20):
            Exam.objects.create(
                title=f"Aktiv {i:02d}",
                author=cls.teacher,
                organization=cls.org,
                exam_type="written",
                is_active=True,
            )
        for i in range(5):
            Exam.objects.create(
                title=f"Qaralama {i:02d}",
                author=cls.teacher,
                organization=cls.org,
                exam_type="test",
                is_active=False,
            )

    def setUp(self):
        self.client = Client()
        self.client.login(username="sf_teacher", password=PASSWORD)

    def _get(self, query=""):
        response = self.client.get(reverse("accounts:profile") + "?section=my-exams" + query)
        self.assertEqual(response.status_code, 200)
        return response.context

    def test_section_reports_itself_as_paginated(self):
        """Şablon bu bayraqla filtri serverə yönləndirir — yoxdursa JS köhnə yolla gedər."""
        self.assertTrue(self._get()["my_exams_is_paginated"])

    def test_search_finds_an_exam_that_is_not_on_the_first_page(self):
        """Regressiyanın özü: 3-cü səhifədəki imtahan tapılmalıdır."""
        ctx = self._get("&exam_q=Aktiv 00")
        titles = [exam.title for exam in ctx["my_exams"]]
        self.assertIn("Aktiv 00", titles)
        self.assertEqual(ctx["my_exams_count"], 1)

    def test_status_filter_narrows_the_whole_set_on_the_server(self):
        ctx = self._get("&exam_status=draft")
        self.assertEqual(ctx["my_exams_count"], 5)
        self.assertTrue(all(not exam.is_active for exam in ctx["my_exams"]))

    def test_status_filter_rejects_unknown_values_instead_of_erroring(self):
        ctx = self._get("&exam_status=; DROP TABLE")
        self.assertEqual(ctx["my_exams_count"], 25)
        self.assertEqual(ctx["my_exams_filter_status"], "")

    def test_status_filter_is_preserved_in_pagination_links(self):
        ctx = self._get("&exam_status=active")
        self.assertIn("exam_status=active", ctx["my_exams_pagination_query"])

    def test_type_and_status_combine(self):
        ctx = self._get("&exam_type=test&exam_status=draft")
        self.assertEqual(ctx["my_exams_count"], 5)
