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
