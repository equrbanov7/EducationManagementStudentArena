"""MR-534/555/558 (2026-11-19) — imtahan balı siyahısında başqa qrupdan gələn tələbənin CARİ QRUPU nişanla görünür.

İmtahan Mərkəzi sənədsiz (köhnə) əlavə olunmuş tələbəni «Alt qrup» hissəsində axtarırdı, ümumi siyahıda isə onu
tanımırdı. İndi:

* cari qrupu jurnalın qrupu olmayan hər sətirdə qrup adı nişanı var (sənədli və ya sənədsiz);
* «Alt qrup» başlığı və sıralama dəyişmir (yalnız sənədli sətirlər — sahib 2026-11-18);
* jurnalın öz ana/alt qrupu («ESG-101» ↔ «ESG-101-1») nişansızdır;
* öz qrupunun tələbəsində nişan yoxdur.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.organizations.models import OrgUnit
from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_midterm
from apps.registrar.models import Enrollment, StudentAcademicRecord
from apps.registrar.tests.subgroup_evidence_fixture import attach_guest_document
from apps.registrar.tests.test_exam_score_assessment_2026_10_25 import _MEDIA, MidtermPeriodFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class ExamScoreOtherGroupLabelTest(MidtermPeriodFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.build_fixture("eog")
            cls.other_group = OrgUnit.objects.create(
                organization=cls.org, name="EOG-233", slug="eog-g233", unit_type=OrgUnitType.GROUP
            )
            cls.sub_group = OrgUnit.objects.create(
                organization=cls.org, name="EOG-101-1", slug="eog-g101-1", unit_type=OrgUnitType.GROUP
            )
            record = StudentAcademicRecord.objects.get(student=cls.enrollments[0].student)
            # Sənədsiz köhnə əlavə (source_group boş) — əvvəl heç bir işarəsi yox idi.
            cls.plain = cls._enrol("eog_plain", group=cls.other_group, record_from=record)
            # Sənədli alt qrup sətri — «alt qrupdan» + qrup adı.
            cls.guest = cls._enrol("eog_guest", group=cls.other_group, record_from=record, source=cls.other_group)
            attach_guest_document(cls.guest)
            # Jurnalın öz alt qrupu — nişansız.
            cls.sibling = cls._enrol("eog_sib", group=cls.sub_group, record_from=record)

    @classmethod
    def _enrol(cls, username, *, group, record_from, source=None):
        student = cls._member(username, "student")
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=record_from.program,
            curriculum=record_from.curriculum,
            group=group,
            admission_year=2026,
        )
        return Enrollment.objects.create(
            organization=cls.org, student=student, offering=cls.offering, source_group=source
        )

    def _labels(self, rows):
        return {row["enrollment"].pk: row["other_group"] for row in rows}

    def test_final_and_midterm_rows_carry_current_group_of_outsiders_only(self):
        for roster in (service.roster_for_offering, exam_score_midterm.roster_for_offering):
            with self.subTest(roster=roster.__module__), bypass_rls():
                rows = roster(offering=self.offering)["rows"]
                labels = self._labels(rows)
                self.assertEqual(labels[self.plain.pk], "EOG-233")
                self.assertEqual(labels[self.guest.pk], "EOG-233")
                self.assertEqual(labels[self.sibling.pk], "")
                for own in self.enrollments:
                    self.assertEqual(labels[own.pk], "")
                # «Alt qrup» qaydası dəyişmir: yalnız sənədli sətir, ən sonda.
                self.assertEqual([row["enrollment"].pk for row in rows if row["is_subgroup"]], [self.guest.pk])
                self.assertEqual(rows[-1]["enrollment"].pk, self.guest.pk)

    def test_screen_shows_group_badge_for_undocumented_outsider(self):
        from django.test import Client
        from django.urls import reverse

        from .test_exam_score_appeal_cell_2026_11_17 import INT

        client = Client(REMOTE_ADDR=INT)
        client.force_login(self.center)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(
            reverse("accounts:profile"),
            {"section": "exam-score-entry", "ese_offering": str(self.offering.pk), "ese_assessment": "final"},
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        row = html.split(f'data-enrollment="{self.plain.pk}"')[1].split("</th>")[0]
        self.assertIn("EOG-233", row)
        own_row = html.split(f'data-enrollment="{self.enrollments[0].pk}"')[1].split("</th>")[0]
        self.assertNotIn("EOG-", own_row)
