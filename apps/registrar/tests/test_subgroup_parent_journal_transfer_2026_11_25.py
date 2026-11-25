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
    Lesson,
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

    # ── Review PR #472 ────────────────────────────────────────────────────────────────────────────────────────────

    def _second_student(self, username, group):
        with bypass_rls():
            user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
            Membership.objects.create(
                user=user,
                organization=self.org,
                role=self.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            return StudentAcademicRecord.objects.create(
                organization=self.org,
                student=user,
                program=self.record.program,
                curriculum=self.record.curriculum,
                group=group,
                admission_year=2024,
            )

    def _rows(self, student):
        with bypass_rls():
            return {
                (row.offering.group_id, row.status, row.offering.is_active)
                for row in Enrollment.objects.filter(student=student).select_related("offering")
            }

    def test_leaving_family_after_split_carries_parent_journal_rows(self):
        self._move(self.subs[0], keep_parent_journal=True)
        result = self._move(self.other)
        self._refresh()
        self.assertEqual(self.record.group_id, self.other.pk)
        self.assertEqual(result["moved"], 1)
        self.assertEqual(self.parent_row.status, Enrollment.Status.DROPPED)
        self.assertEqual(self.parent_row.superseded_by.offering.group_id, self.other.pk)
        enrolled = self._enrolled()
        self.assertEqual(len(enrolled), 1)
        with bypass_rls():
            self.assertEqual(enrolled[0].offering.group_id, self.other.pk)
            audit = AuditLog.objects.filter(
                resource_type="registrar.subgroup_parent_journal", resource_id=str(self.record.pk)
            ).latest("created_at")
        self.assertEqual(audit.changes["family_carried_enrollment_ids"], [str(self.parent_row.pk)])

    def test_coming_back_from_outside_returns_to_parent_journal(self):
        self._move(self.subs[0], keep_parent_journal=True)
        self._move(self.other)
        self._move(self.subs[0])  # B → A1: A1-in açılışı passivdir → ana jurnal
        self._refresh()
        self.assertEqual(self.record.group_id, self.subs[0].pk)
        self.assertEqual(self.parent_row.status, Enrollment.Status.ENROLLED)
        self.assertEqual(self.parent_row.seminar_group, self._number(self.subs[0]))
        self.assertEqual(self._enrolled(), [self.parent_row])

    def test_outside_student_entering_split_subgroup_lands_in_parent_journal(self):
        self._move(self.subs[0], keep_parent_journal=True)
        newcomer = self._second_student("spj_new", self.other)
        with bypass_rls():
            services.enroll_student_in_subject(
                record=newcomer, subject=self.subject, period=self.period, kind=EnrollmentKind.MANDATORY
            )
            result = transfer.transfer_student_group(
                record=newcomer, new_group=self.subs[0], period=self.period, by_user=self.owner, reason="QA"
            )
            row = Enrollment.objects.get(student=newcomer.student, status=Enrollment.Status.ENROLLED)
        self.assertEqual(result["kept"], 1)
        self.assertEqual(row.offering_id, self.parent_row.offering_id)
        self.assertEqual(row.source_group_id, self.subs[0].pk)
        self.assertEqual(row.seminar_group, self._number(self.subs[0]))
        self.assertIsNotNone(row.added_at)
        self.assertNotIn((self.subs[0].pk, Enrollment.Status.ENROLLED, False), self._rows(newcomer.student))

    def test_mandatory_enrollment_of_split_subgroup_student_uses_parent_journal(self):
        self._move(self.subs[0], keep_parent_journal=True)
        newcomer = self._second_student("spj_mand", self.subs[0])
        with bypass_rls():
            row, created = services.enroll_student_in_subject(
                record=newcomer,
                subject=self.subject,
                period=self.period,
                kind=EnrollmentKind.MANDATORY,
                prefer_parent_journal=True,
            )
        self.assertTrue(created)
        self.assertEqual(row.offering_id, self.parent_row.offering_id)
        self.assertEqual(row.source_group_id, self.subs[0].pk)
        self.assertEqual(row.seminar_group, self._number(self.subs[0]))

    def test_split_into_subgroup_with_live_own_journal_is_refused(self):
        with bypass_rls():
            own = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, period=self.period, group=self.subs[0]
            )
            Lesson.objects.create(organization=self.org, offering=own, date=self.period.start_date, kind="lecture")
        with self.assertRaises(ValidationError) as raised:
            self._move(self.subs[0], keep_parent_journal=True)
        self.assertIn("ayrıca aktiv jurnalı var", " ".join(raised.exception.messages))
        self._refresh()
        self.assertEqual(self.record.group_id, self.parent.pk)
        self.assertEqual(self.parent_row.status, Enrollment.Status.ENROLLED)
