"""Ana qrup ↔ alt qrup köçürmələri ana jurnalı TƏK jurnal saxlayır (sahib 2026-11-07/08).

Hər köçürmə ayrıca tranzaksiyadır (DB sübutu: bir qeyd × bir tranzaksiya) — ona görə ``TransactionTestCase``.

* bölmə (``keep_parent_journal=True``) → ana sətir aktiv, varis tarixçədə, boş varis açılışı passiv;
* ana qrupa geri qayıdış «tarixi qeydiyyat var» xətası vermir, seminar yeri boşalır;
* qardaş alt qrupa keçid seminar yerini dəyişir;
* yenidən alt qrupa (adi köçürmə) — passiv alt qrup açılışına düşmür, ana jurnalda qalır;
* bayraqsız adi köçürmə köhnə qayda ilə gedir (mövcud alətlər dəyişmir);
* köhnə forma zənciri A → A1 → A2 → A geri qaytarılır, ailədən kənar zəncir isə yenə yoxlama tələb edir.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services, transfer
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    EnrollmentKind,
    Program,
    SeminarGroup,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class SubgroupParentJournalTransferTest(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL group-transfer evidence required")
        self.owner = User.objects.create_user("spj_owner", "spj_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="SPJ Univ",
                slug="spj-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.parent = OrgUnit.objects.create(
                organization=self.org, name="KM", slug="spj-km", unit_type=OrgUnitType.GROUP
            )
            self.subs = [
                OrgUnit.objects.create(
                    organization=self.org,
                    name=f"KM-{index}",
                    slug=f"spj-km-{index}",
                    unit_type=OrgUnitType.GROUP,
                    settings={"parent_group": str(self.parent.pk)},
                )
                for index in (1, 2)
            ]
            self.other = OrgUnit.objects.create(
                organization=self.org, name="Başqa", slug="spj-other", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            program = Program.objects.create(organization=self.org, code="KM", name="Kompüter mühəndisliyi")
            curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
            self.subject = Subject.objects.create(organization=self.org, code="DR101", name="Diskret riyaziyyat")
            self.student = User.objects.create_user("spj_student", "spj_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.student,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            self.record = StudentAcademicRecord.objects.create(
                organization=self.org,
                student=self.student,
                program=program,
                curriculum=curriculum,
                group=self.parent,
                admission_year=2024,
            )
            services.enroll_student_in_subject(
                record=self.record, subject=self.subject, period=self.period, kind=EnrollmentKind.MANDATORY
            )
            self.parent_row = Enrollment.objects.get(student=self.student, offering__group=self.parent)

    def _move(self, group, **options):
        with bypass_rls():
            return transfer.transfer_student_group(
                record=self.record, new_group=group, period=self.period, by_user=self.owner, reason="QA", **options
            )

    def _refresh(self):
        with bypass_rls():
            self.record.refresh_from_db()
            self.parent_row.refresh_from_db()

    def _number(self, unit):
        with bypass_rls():
            return SeminarGroup.objects.get(offering=self.parent_row.offering, unit=unit).number

    def _enrolled(self):
        with bypass_rls():
            return list(Enrollment.objects.filter(student=self.student, status=Enrollment.Status.ENROLLED))

    def test_split_keeps_parent_row_and_retires_empty_successor_offering(self):
        result = self._move(self.subs[0], keep_parent_journal=True)
        self._refresh()
        self.assertEqual(result["kept"], 1)
        self.assertEqual(self.record.group_id, self.subs[0].pk)
        self.assertEqual(self.parent_row.status, Enrollment.Status.ENROLLED)
        self.assertIsNone(self.parent_row.superseded_by_id)
        self.assertEqual(self.parent_row.source_group_id, self.subs[0].pk)
        self.assertEqual(self.parent_row.seminar_group, self._number(self.subs[0]))
        self.assertEqual(self._enrolled(), [self.parent_row])
        with bypass_rls():
            shell = CourseOffering.objects.get(group=self.subs[0])
            successor = Enrollment.objects.get(offering=shell)
            self.assertFalse(shell.is_active)
            self.assertIsNone(shell.instructor_id)
            self.assertEqual(successor.status, Enrollment.Status.DROPPED)
            self.assertEqual(successor.superseded_by_id, self.parent_row.pk)
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="registrar.subgroup_parent_journal", resource_id=str(self.record.pk)
                ).exists()
            )

    def test_move_back_to_parent_works_and_clears_seminar_place(self):
        self._move(self.subs[0], keep_parent_journal=True)
        self._move(self.parent)  # «Qrupu dəyiş» — bayraqsız adi köçürmə
        self._refresh()
        self.assertEqual(self.record.group_id, self.parent.pk)
        self.assertEqual(self.parent_row.status, Enrollment.Status.ENROLLED)
        self.assertIsNone(self.parent_row.seminar_group)
        self.assertEqual(self._enrolled(), [self.parent_row])

    def test_sibling_move_switches_seminar_place(self):
        self._move(self.subs[0], keep_parent_journal=True)
        self._move(self.subs[1])
        self._refresh()
        self.assertEqual(self.record.group_id, self.subs[1].pk)
        self.assertEqual(self.parent_row.status, Enrollment.Status.ENROLLED)
        self.assertEqual(self.parent_row.seminar_group, self._number(self.subs[1]))
        self.assertEqual(self._enrolled(), [self.parent_row])

    def test_plain_move_into_retired_subgroup_offering_stays_in_parent(self):
        self._move(self.subs[0], keep_parent_journal=True)
        self._move(self.parent)
        self._move(self.subs[0])  # adi köçürmə: alt qrupun açılışı passivdir → ana jurnal
        self._refresh()
        self.assertEqual(self.record.group_id, self.subs[0].pk)
        self.assertEqual(self.parent_row.status, Enrollment.Status.ENROLLED)
        self.assertEqual(self.parent_row.seminar_group, self._number(self.subs[0]))
        self.assertEqual(self._enrolled(), [self.parent_row])

    def test_plain_transfer_to_subgroup_keeps_existing_rule(self):
        result = self._move(self.subs[0])
        self._refresh()
        self.assertEqual(result["kept"], 0)
        self.assertEqual(self.parent_row.status, Enrollment.Status.DROPPED)
        self.assertEqual(self.parent_row.superseded_by.offering.group_id, self.subs[0].pk)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(group=self.subs[0]).is_active)

    def test_old_shape_chain_back_to_parent_reactivates_parent_row(self):
        self._move(self.subs[0])
        self._move(self.subs[1])
        self._move(self.parent)
        self._refresh()
        self.assertEqual(self.record.group_id, self.parent.pk)
        self.assertEqual(self.parent_row.status, Enrollment.Status.ENROLLED)
        self.assertIsNone(self.parent_row.superseded_by_id)
        with bypass_rls():
            current = Enrollment.objects.get(student=self.student, offering__group=self.subs[1])
        self.assertEqual(current.status, Enrollment.Status.DROPPED)
        self.assertEqual(current.superseded_by_id, self.parent_row.pk)
        self.assertEqual(self._enrolled(), [self.parent_row])

    def test_chain_outside_family_still_requires_review(self):
        self._move(self.subs[0])
        self._move(self.other)
        with self.assertRaises(ValidationError):
            self._move(self.parent)
        self._refresh()
        self.assertEqual(self.record.group_id, self.other.pk)
