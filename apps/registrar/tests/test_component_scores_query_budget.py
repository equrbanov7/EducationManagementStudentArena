"""Midterm/kollokvium və komponent balı yazısı — sorğu büdcəsi (tutum 2026-10-07).

Əvvəl ``journal_kollokvium_save`` hər xana üçün pəncərə + əlavə gün SELECT-i
(``kollokvium_windows.is_open``), ``save_component_scores`` isə hər xana üçün
mövcud bal SELECT + ``update_or_create`` (SELECT FOR UPDATE + INSERT/UPDATE) +
audit üçün tələbə SELECT-i edirdi — ölçü (midterm, bütün qrup bir POST-da):

==================  ===========  ===========
POST                10 tələbə    40 tələbə
==================  ===========  ===========
ilk yazı            124 → 29     424 → 29
eyni balla təkrar    91 → 26     301 → 26
düzəliş             104 → 29     344 → 29
==================  ===========  ===========

İndi «oxu → toplu yaz» (``save_marks`` naxışı): açılış sətri ``FOR UPDATE``, mövcud
ballar bir SELECT-də, silinən/yeni/mövcud sətirlər üç toplu sorğuda. Qaydalar
(pəncərə, 2 saat, tavan, rədd edilən dəyər, audit, bildiriş) bu faylın davranış
testlərində və ``test_components`` / ``test_midterm_mode`` / ``test_rubric_*``-da yoxlanır.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, journal_extras, services
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    Curriculum,
    CurriculumSubject,
    KollokviumWindow,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

#: Ölçülmüş 29 + 3 ehtiyat. Əsas qıfıl «10 tələbə == 40 tələbə»dir.
KOLLOKVIUM_POST_BUDGET = 32


class ComponentScoresQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.owner = User.objects.create_user("csq_owner", "csq_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="CSQ Univ",
                slug="csq-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            specialty = OrgUnit.objects.create(
                organization=cls.org, name="CS", slug="csq-cs", unit_type=OrgUnitType.SPECIALTY
            )
            # 2026/2027 → midterm rejimi (tək sütun, 0–20).
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="CSQ semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=60),
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
            )
            program = Program.objects.create(organization=cls.org, code="CSQ", name="CSQ", absence_limit_percent=25)
            cls.teacher = User.objects.create_user("csq_teacher", "csq_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.small = cls._offering(program, specialty, "small", 10, admission_year=2026)
            cls.large = cls._offering(program, specialty, "large", 40, admission_year=2025)
            KollokviumWindow.objects.create(
                organization=cls.org,
                period=cls.period,
                k_index=0,
                opens_on=today - datetime.timedelta(days=1),
                closes_on=today + datetime.timedelta(days=5),
                is_active=True,
            )
            AuditLog.objects.exists()  # audit sxem introspeksiyası ölçüyə düşməsin

    @classmethod
    def _offering(cls, program, specialty, label, students, *, admission_year):
        group = OrgUnit.objects.create(
            organization=cls.org,
            name=f"CSQ-{label}",
            slug=f"csq-{label}",
            unit_type=OrgUnitType.GROUP,
            parent=specialty,
        )
        curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=admission_year)
        subject = Subject.objects.create(organization=cls.org, code=f"CSQ{label[:2].upper()}", name=f"Fənn {label}")
        CurriculumSubject.objects.create(
            organization=cls.org, curriculum=curriculum, subject=subject, semester_number=1
        )
        role = cls.org.roles.get(name="student")
        for index in range(students):
            student = User.objects.create_user(
                f"csq_{label}_{index:02d}", f"csq_{label}_{index:02d}@qku.edu.az", "pw", first_name=f"S{index}"
            )
            Membership.objects.create(user=student, organization=cls.org, role=role, is_primary=True, is_active=True)
            record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=student,
                program=program,
                curriculum=curriculum,
                group=group,
                admission_year=admission_year,
            )
            services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
        offering = subject.offerings.get()
        offering.instructor = cls.teacher
        offering.save(update_fields=["instructor"])
        gradebook.ensure_assessment_scheme(offering=offering)
        midterm = journal_extras.ensure_kollokviums(offering)[0]
        generic = AssessmentComponent.objects.create(
            organization=cls.org, offering=offering, name="Layihə", kind=ComponentKind.GENERIC, max_score=10, order=9
        )
        enrollments = list(offering.enrollments.order_by("student__username"))
        return {"offering": offering, "midterm": midterm, "generic": generic, "enrollments": enrollments}

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _post(self, case, score_for, *, run_on_commit=False):
        url = reverse("registrar:journal_kollokvium_save", args=[case["offering"].id])
        data = {
            f"kscore__{case['midterm'].id}__{enrollment.id}": score_for(index)
            for index, enrollment in enumerate(case["enrollments"])
        }
        with CaptureQueriesContext(connection) as ctx:
            with self.captureOnCommitCallbacks(execute=run_on_commit):
                response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        return len(ctx.captured_queries)

    def _scores(self, case):
        with bypass_rls():
            return {
                score.enrollment_id: score
                for score in ComponentScore.objects.filter(component=case["midterm"]).select_related("entered_by")
            }

    def test_kollokvium_post_query_count_is_constant_in_roster_size(self):
        # Sessiya / proses keşlərini isit (ölçüyə yalnız POST-un öz işi düşsün).
        self.client.get(reverse("registrar:journal_detail", args=[self.small["offering"].id]), {"jt": "kollokvium"})
        phases = (
            ("ilk yazı", lambda i: str(10 + i % 8)),
            ("təkrar", lambda i: str(10 + i % 8)),
            ("düzəliş", lambda i: str(11 + i % 8)),
        )
        for phase, score_for in phases:
            small = self._post(self.small, score_for)
            large = self._post(self.large, score_for)
            print(f"\n[component budget] {phase}: 10 tələbə={small} q; 40 tələbə={large} q")
            self.assertEqual(small, large, f"{phase}: sorğu sayı qrup ölçüsü ilə böyüyür")
            self.assertLessEqual(large, KOLLOKVIUM_POST_BUDGET, phase)
        scores = self._scores(self.large)
        self.assertEqual(len(scores), 40)
        for index, enrollment in enumerate(self.large["enrollments"]):
            self.assertEqual(scores[enrollment.id].score, Decimal(11 + index % 8))
            self.assertEqual(scores[enrollment.id].entered_by_id, self.teacher.pk)

    def test_student_notifications_are_one_bulk_insert(self):
        """Commit-dən sonrakı tələbə bildirişləri (``send_journal_events``) də qrup ölçüsündən asılı deyil.

        Əvvəl hər tələbə üçün ``create_notification`` (bypass_rls + INSERT = 4 ifadə): 40 tələbədə +160."""
        from apps.notifications.models import InAppNotification

        self.client.get(reverse("registrar:journal_detail", args=[self.small["offering"].id]), {"jt": "kollokvium"})
        small = self._post(self.small, lambda i: str(10 + i % 8), run_on_commit=True)
        large = self._post(self.large, lambda i: str(10 + i % 8), run_on_commit=True)
        self.assertEqual(small, large)
        with bypass_rls():
            rows = list(
                InAppNotification.objects.filter(recipient__enrollments__offering=self.large["offering"]).distinct()
            )
        self.assertEqual(len(rows), 40)
        sample = rows[0]
        self.assertEqual(sample.organization_id, self.org.pk)
        self.assertIn(self.large["offering"].subject.name, sample.title)
        self.assertEqual(sample.metadata, {"event": "journal_update", "offering_id": str(self.large["offering"].id)})
        self.assertIn("section%3Dmy-journal", sample.link)  # org-scoped keçid (organizations:switch?next=…)
        self.assertTrue(sample.message)

    def test_service_semantics_delete_reject_clamp_duplicates_and_audit(self):
        case = self.small
        first, second, third, fourth = case["enrollments"][:4]
        midterm = case["midterm"]
        with bypass_rls():
            gradebook.save_component_scores(
                offering=case["offering"],
                entries=[
                    {"component_id": midterm.id, "enrollment_id": first.id, "score": "12"},
                    {"component_id": midterm.id, "enrollment_id": second.id, "score": "15"},
                ],
                by_user=self.teacher,
                bypass_edit_window=True,
            )
            audit_before = set(AuditLog.objects.values_list("pk", flat=True))
            result = gradebook.save_component_scores(
                offering=case["offering"],
                entries=[
                    {"component_id": midterm.id, "enrollment_id": first.id, "score": ""},  # silinir
                    {"component_id": midterm.id, "enrollment_id": second.id, "score": "abc"},  # rədd
                    {"component_id": midterm.id, "enrollment_id": third.id, "score": "999"},  # tavana kəsilir
                    {"component_id": midterm.id, "enrollment_id": fourth.id, "score": "5"},
                    {"component_id": midterm.id, "enrollment_id": fourth.id, "score": "7"},  # təkrar: sonuncu qalır
                    {"component_id": midterm.id, "enrollment_id": "yad", "score": "5"},  # yad hədəf
                ],
                by_user=self.teacher,
                bypass_edit_window=True,
                report=True,
            )
            self.assertEqual(result, {"written": 3, "rejected": 1})
            scores = self._scores(case)
            self.assertNotIn(first.id, scores)
            self.assertEqual(scores[second.id].score, Decimal("15"))
            self.assertEqual(scores[third.id].score, Decimal(midterm.max_score))
            self.assertEqual(scores[fourth.id].score, Decimal("7"))
            log = AuditLog.objects.exclude(pk__in=audit_before).get()  # TƏK aqreqat audit sətri
            # silinmə + tavan + 5 + 5→7 — dəyişiklik sətirləri əvvəlki kimi (təkrar ikisi də yazılır).
            self.assertEqual(len(log.changes), 4)
            self.assertTrue(all(change["student"] for change in log.changes))

    def test_generic_component_edit_window_is_still_enforced(self):
        case = self.small
        generic = case["generic"]
        enrollment = case["enrollments"][0]
        with bypass_rls():
            gradebook.save_component_scores(
                offering=case["offering"],
                entries=[{"component_id": generic.id, "enrollment_id": enrollment.id, "score": "4"}],
                by_user=self.teacher,
            )
            ComponentScore.objects.filter(component=generic).update(
                created_at=timezone.now() - gradebook.mark_edit_window() - datetime.timedelta(minutes=5)
            )
            written = gradebook.save_component_scores(
                offering=case["offering"],
                entries=[
                    {"component_id": generic.id, "enrollment_id": enrollment.id, "score": "9"},
                    {"component_id": generic.id, "enrollment_id": case["enrollments"][1].id, "score": "6"},
                    # Midterm sütunu generic yoldan yazılmır (pəncərə yan keçilmir).
                    {"component_id": case["midterm"].id, "enrollment_id": enrollment.id, "score": "6"},
                ],
                by_user=self.teacher,
            )
            self.assertEqual(written, 1)
            values = dict(ComponentScore.objects.filter(component=generic).values_list("enrollment_id", "score"))
            self.assertEqual(values[enrollment.id], Decimal("4"))  # 2 saatdan köhnə — toxunulmadı
            self.assertEqual(values[case["enrollments"][1].id], Decimal("6"))
            self.assertFalse(ComponentScore.objects.filter(component=case["midterm"]).exists())
