"""Dözümlü axtarış (sahib 2026-09-26) — imtahan modulunun əsas axtarış nöqtələri.

«qruplar və bütün search yerlərində az dili hərfləri ilə yazmağı nəzərə al, en
dilə olan nəticə də gəlsin; qrup «234 K ing»dir, «234king» və s. kombinasiyada da
işləsin». Hamısı ``core.search_text.tolerant_q`` / ``tolerant_match`` ilə.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import QueryDict
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import (
    BankQuestion,
    Exam,
    ExamQuestion,
    ExamRoom,
    ExamRoomSession,
    FinalExamTicket,
    QuestionBank,
    StudentGroup,
)
from apps.exams.services.final_center.reports import filter_sessions, filter_tickets
from apps.exams.services.question_bank_attach import bank_questions_queryset
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.exams.views.teacher.submission_meta import filter_snapshot_questions
from apps.organizations.models import Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _login(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


class _Fixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("st26_owner", "st26_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="ST26 Uni", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active", is_active=True
        )
        cls.teacher = User.objects.create_user("st26_teacher", "st26_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.center = User.objects.create_user("st26_center", "st26_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.aliyev = User.objects.create_user(
            "st26_s1", "st26_s1@test.az", PASSWORD, first_name="Rəşad", last_name="Əliyev"
        )
        _assign_user_to_org(cls.aliyev, cls.org, ProfileRole.STUDENT, "student")
        cls.shahzad = User.objects.create_user(
            "st26_s2", "st26_s2@test.az", PASSWORD, first_name="Şahzad", last_name="Quliyev"
        )
        _assign_user_to_org(cls.shahzad, cls.org, ProfileRole.STUDENT, "student")
        with bypass_rls():
            faculty = OrgUnit.objects.create(
                organization=cls.org, name="İnformatika", slug="st26-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.unit_king = OrgUnit.objects.create(
                organization=cls.org, parent=faculty, name="234 K ing", slug="st26-234king", unit_type=OrgUnitType.GROUP
            )
            cls.unit_k1 = OrgUnit.objects.create(
                organization=cls.org, parent=faculty, name="234 K-1", slug="st26-234k1", unit_type=OrgUnitType.GROUP
            )
            cls.unit_other = OrgUnit.objects.create(
                organization=cls.org, parent=faculty, name="701 biz", slug="st26-701", unit_type=OrgUnitType.GROUP
            )


class GroupSearchTolerantTests(_Fixture):
    def _unit_names(self, query):
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:group_search"), {"kind": "units", "q": query})
        self.assertEqual(response.status_code, 200)
        return {row["text"].split(" — ")[0] for row in response.json()["results"]}

    def test_units_compact_variants_find_234_k_ing(self):
        for query in ("234king", "234k ing", "234 K ing", "234-K-ing", "234KİNG"):
            with self.subTest(query=query):
                self.assertEqual(self._unit_names(query), {"234 K ing"})

    def test_units_subgroup_and_prefix(self):
        self.assertEqual(self._unit_names("234k1"), {"234 K-1"})
        self.assertEqual(self._unit_names("234k"), {"234 K ing", "234 K-1"})
        self.assertEqual(self._unit_names(""), {"234 K ing", "234 K-1", "701 biz"})

    def test_legacy_student_group_branch_is_compact(self):
        hit = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="234 K ing")
        StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="701 biz")
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:group_search"), {"q": "234king"})
        self.assertEqual([row["id"] for row in response.json()["results"]], [str(hit.id)])


class PersonSearchTolerantTests(_Fixture):
    def test_user_search_aliyev_finds_eliyev(self):
        client = _login(self.teacher, self.org)
        for query in ("Aliyev", "eliyev", "Rəşad Əliyev", "resad aliyev"):
            with self.subTest(query=query):
                response = client.get(reverse("exams:user_search"), {"q": query})
                ids = {row["id"] for row in response.json()["results"]}
                self.assertEqual(ids, {str(self.aliyev.id)})

    def test_pin_search_shahzad_finds_sahzad(self):
        exam = Exam.objects.create(
            title="ST26 Final",
            author=self.center,
            organization=self.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
        )
        room = ExamRoom.objects.create(organization=self.org, name="Zal 101-A", code="Z-101", capacity=20)
        now = timezone.now()
        session = ExamRoomSession.objects.create(
            organization=self.org,
            room=room,
            invigilator=self.center,
            scheduled_start=now + timedelta(hours=1),
            scheduled_end=now + timedelta(hours=3),
        )
        FinalExamTicket.objects.create(organization=self.org, session=session, exam=exam, student=self.shahzad)
        FinalExamTicket.objects.create(organization=self.org, session=session, exam=exam, student=self.aliyev)

        client = _login(self.center, self.org)
        for query in ("Shahzad", "sahzad", "ŞAHZAD"):
            with self.subTest(query=query):
                response = client.get(reverse("exams:exam_center_pin_search"), {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.json()["results"]], [self.shahzad.id])

        # Hesabat servisi: ad normal, zal adı/kodu kod rejimində.
        names = {t.student_id for t in filter_tickets(self.org, QueryDict("q=Aliyev"))}
        self.assertEqual(names, {self.aliyev.id})
        self.assertEqual(filter_tickets(self.org, QueryDict("q=z101")).count(), 2)
        self.assertEqual(filter_sessions(self.org, QueryDict("q=101a")).count(), 1)
        self.assertEqual(filter_sessions(self.org, QueryDict("q=999")).count(), 0)


class QuestionTextSearchTolerantTests(_Fixture):
    def setUp(self):
        cache.clear()

    def test_exam_question_bank_verilenler_finds_verilenler(self):
        exam = Exam.objects.create(author=self.teacher, title="ST26 Exam", exam_type="test", is_active=True)
        hit = ExamQuestion.objects.create(
            exam=exam, text="Verilənlər bazası nədir?", order=1, answer_mode="single", language="az"
        )
        ExamQuestion.objects.create(exam=exam, text="Şəbəkə protokolu", order=2, answer_mode="single", language="az")
        client = _login(self.teacher, self.org)
        url = reverse("exams:teacher_questions_bank", args=[exam.slug])
        for query in ("Verilenler", "verilənlər baza", "VERILENLER"):
            with self.subTest(query=query):
                response = client.get(url, {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([q.id for q in response.context["page_obj"].object_list], [hit.id])

    def test_library_bank_service_and_detail_view(self):
        bank = QuestionBank.objects.create(
            name="ST26 Bank", organization=self.org, created_by=self.teacher, is_shared=False
        )
        hit = BankQuestion.objects.create(bank=bank, text="Verilənlər strukturu", created_by=self.teacher)
        BankQuestion.objects.create(bank=bank, text="Alqoritm", created_by=self.teacher)
        self.assertEqual(list(bank_questions_queryset(bank, search="Verilenler")), [hit])
        self.assertEqual(bank_questions_queryset(bank, search=None).count(), 2)

        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:question_bank_detail", kwargs={"bank_id": bank.id}), {"q": "verilenler"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([q.id for q in response.context["page_obj"].object_list], [hit.id])

    def test_snapshot_filter_is_tolerant_and_tokenized(self):
        questions = [
            {"text": "Verilənlər bazası", "options": {"A": "SQL", "B": "Excel"}},
            {"text": "Şəbəkə", "options": {"A": "TCP"}},
        ]
        self.assertEqual(len(filter_snapshot_questions(questions, query="verilenler sql")), 1)
        self.assertEqual(len(filter_snapshot_questions(questions, query="sebeke")), 1)
        self.assertEqual(len(filter_snapshot_questions(questions, query="")), 2)
        self.assertEqual(len(filter_snapshot_questions(questions, query="yoxdur")), 0)
