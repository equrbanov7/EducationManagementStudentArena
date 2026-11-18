"""Sahib 2026-11-18 — «İmtahan balının daxil edilməsi»: alt qrup tələbələri jurnaldakı kimi, ən aşağıda.

«imtahan nəticələri yüklənərkən midterm ya da final alt qrup nəticələrini də jurnalda nədirsə orada da görünsün
qrupu seçərkən. Ən aşağıda alt qrup yazısı gəlsin, balını oradan yazmaq olsun.»

* siyahı = jurnalın sətirləri (açılışın ``enrolled`` qeydiyyatları), hər tələbə BİR dəfə;
* sənədli alt qrup sətri (cari qrupu jurnalın qrupu deyil) siyahının SONUNDA, «Alt qrup» başlığı altında;
* sənədsiz köçürmə izi (``source_group`` dolu, sənəd yoxdur) və rəsmi köçürülmüş tələbə öz sırasında qalır;
* bal eyni yolla yazılır — final ``FinalGrade.exam_score``, midterm jurnalın «Midterm» xanası.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_midterm
from apps.registrar import exam_score_sheets as sheets
from apps.registrar import interim_components
from apps.registrar.models import (
    ComponentScore,
    Curriculum,
    Enrollment,
    ExamAssessment,
    FinalGrade,
    GuestRosterDocument,
    Program,
    StudentAcademicRecord,
)
from apps.registrar.tests.subgroup_evidence_fixture import attach_guest_document
from apps.registrar.tests.test_exam_score_assessment_2026_10_25 import _MEDIA, MidtermPeriodFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls

from .test_exam_score_appeal_cell_2026_11_17 import INT


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class ExamScoreSubgroupRowsTest(MidtermPeriodFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.build_fixture("esg")
            cls.other_group = OrgUnit.objects.create(
                organization=cls.org, name="ESG-102", slug="esg-g2", unit_type=OrgUnitType.GROUP
            )
            own_record = StudentAcademicRecord.objects.get(student=cls.enrollments[0].student)
            # Ad sırası ilə ƏN BİRİNCİ olacaq soyad — aşağı düşməsi sıralamadan yox, alt qrup qaydasındandır.
            cls.guest = cls._guest("esg_guest", "Aaa", source_group=cls.other_group, record_from=own_record)
            attach_guest_document(cls.guest)
            # Sənədsiz köçürmə izi — «alt qrup» deyil (sahib 2026-10-25: «bilməsən yazma»).
            cls.trace = cls._guest("esg_trace", "Aab", source_group=cls.other_group, record_from=own_record)

    @classmethod
    def _guest(cls, username, last_name, *, source_group, record_from):
        student = cls._member(username, "student")
        student.last_name = last_name
        student.first_name = "Tələbə"
        student.save(update_fields=["last_name", "first_name"])
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=record_from.program,
            curriculum=record_from.curriculum,
            group=source_group,
            admission_year=2026,
        )
        return Enrollment.objects.create(
            organization=cls.org, student=student, offering=cls.offering, source_group=source_group
        )

    def _client(self, user):
        from django.test import Client

        client = Client(REMOTE_ADDR=INT)
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _page(self, assessment):
        response = self._client(self.center).get(
            reverse("accounts:profile"),
            {"section": "exam-score-entry", "ese_offering": str(self.offering.pk), "ese_assessment": assessment},
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def _assert_subgroup_last(self, rows):
        ids = [row["enrollment"].pk for row in rows]
        self.assertEqual(len(ids), len(set(ids)))  # hər tələbə bir dəfə
        self.assertEqual(ids[-1], self.guest.pk)
        self.assertEqual([row["enrollment"].pk for row in rows if row["is_subgroup"]], [self.guest.pk])
        # Öz sətirləri (sənədsiz iz də daxil) əvvəlki ad sırasında qalır (fikstur tələbələrinin soyadı boşdur).
        self.assertEqual(ids[:-1], [self.enrollments[0].pk, self.enrollments[1].pk, self.trace.pk])

    # ── siyahı ────────────────────────────────────────────────────────────────
    def test_final_roster_puts_documented_subgroup_student_last(self):
        with bypass_rls():
            self._assert_subgroup_last(service.roster_for_offering(offering=self.offering)["rows"])

    def test_midterm_roster_puts_documented_subgroup_student_last(self):
        with bypass_rls():
            self._assert_subgroup_last(exam_score_midterm.roster_for_offering(offering=self.offering)["rows"])

    def test_officially_transferred_student_is_not_subgroup(self):
        with bypass_rls():
            # Rəsmi köçürmə yeni aktiv qeyd yaradır (reyestr trigger-i qrup UPDATE-ini qadağan edir).
            program = Program.objects.create(organization=self.org, code="CS2", name="İkinci ixtisas")
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.guest.student,
                program=program,
                curriculum=Curriculum.objects.create(organization=self.org, program=program, admission_year=2026),
                group=self.group,
                admission_year=2026,
            )
            rows = service.roster_for_offering(offering=self.offering)["rows"]
        self.assertFalse(any(row["is_subgroup"] for row in rows))
        ids = [row["enrollment"].pk for row in rows]
        self.assertLess(ids.index(self.guest.pk), ids.index(self.trace.pk))  # «Aaa» < «Aab» — ad sırasına qayıdır

    def test_search_filter_keeps_subgroup_rows_at_bottom(self):
        with bypass_rls():
            rows = service.roster_for_offering(offering=self.offering)["rows"]
        shown = service.filter_roster_rows(rows, search="Tələbə")
        self.assertEqual(shown[-1]["enrollment"].pk, self.guest.pk)

    # ── ekran ─────────────────────────────────────────────────────────────────
    def test_screen_shows_alt_qrup_heading_above_subgroup_rows(self):
        for assessment in ("final", "midterm"):
            with self.subTest(assessment=assessment):
                html = self._page(assessment)
                self.assertEqual(html.count("data-ese-guest-divider"), 1)
                divider = html.index("data-ese-guest-divider")
                for enrollment in (self.trace, *self.enrollments):
                    self.assertLess(html.index(f'name="score__{enrollment.pk}"'), divider)
                self.assertGreater(html.index(f'name="score__{self.guest.pk}"'), divider)
                self.assertIn("Alt qrup", html[divider : html.index(f'name="score__{self.guest.pk}"')])
                guest_input = html.split(f'name="score__{self.guest.pk}"')[1].split(">")[0]
                self.assertNotIn("disabled", guest_input)

    def test_screen_without_subgroup_rows_has_no_heading(self):
        with bypass_rls():
            GuestRosterDocument.objects.filter(enrollment=self.guest).delete()  # sənədsiz → «alt qrup» deyil
        self.assertNotIn("data-ese-guest-divider", self._page("final"))

    # ── yazı ──────────────────────────────────────────────────────────────────
    def test_final_score_for_subgroup_student_saves_like_own_students(self):
        client = self._client(self.center)
        response = client.post(
            reverse("accounts:exam_score_entry"),
            {
                "action": "save_scores",
                "offering_id": str(self.offering.pk),
                "assessment": "final",
                "question_maxes": "50",
                f"score__{self.guest.pk}": "",
                f"q__{self.guest.pk}__1": "42",
                f"score__{self.enrollments[0].pk}": "",
                f"q__{self.enrollments[0].pk}__1": "35",
            },
        )
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.assertEqual(FinalGrade.objects.get(enrollment=self.guest).exam_score, Decimal("42"))
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollments[0]).exam_score, Decimal("35"))
            row = service.roster_for_offering(offering=self.offering)["rows"][-1]
        self.assertEqual((row["enrollment"].pk, row["exam_score"]), (self.guest.pk, Decimal("42")))

    def test_midterm_score_for_subgroup_student_lands_in_journal(self):
        with bypass_rls():
            sheet = sheets.create_sheet(
                offering=self.offering,
                by_user=self.center,
                assessment=ExamAssessment.MIDTERM,
                question_maxes=[30],
                checked_on=timezone.localdate(),
            )
            result = service.save_roster_scores(
                offering=self.offering,
                rows=[{"enrollment_id": str(self.guest.pk), "question_scores": ["21"]}],
                by_user=self.center,
                sheet=sheet,
            )
            self.assertEqual(result["written"], 1, result)
            component = interim_components.ensure_kollokviums(self.offering)[0]
            cell = ComponentScore.objects.get(component=component, enrollment=self.guest)
            self.assertEqual(cell.score, Decimal("21"))
            row = exam_score_midterm.roster_for_offering(offering=self.offering)["rows"][-1]
        self.assertEqual((row["enrollment"].pk, row["exam_score"]), (self.guest.pk, Decimal("21")))
