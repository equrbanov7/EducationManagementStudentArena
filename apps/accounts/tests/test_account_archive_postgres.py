"""PostgreSQL-only: arxiv hesab CANLI trigger-lərlə üz-üzə.

Bu dəst spec A-nın əsl sübutudur, çünki qapıların hər ikisi yalnız PostgreSQL-də
mövcuddur:

* ``registrar_guard_active_member`` (0041 trigger + 0042 funksiya) —
  ``Enrollment``/``StudentAcademicRecord`` yalnız aktiv üzvlük + AKTİV
  ``auth_user`` ilə yazıla bilir;
* ``accounts_reject_active_staged_profile`` (0013 + 0016) — ``archived``
  vəziyyətindən çıxmaq evidence tələb edir.

Sənəd markerlə işlədilir: ``pytest -m postgres``.
"""

import datetime

from django.contrib.auth import authenticate, get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import TestCase

import pytest

from apps.accounts.identity import user_access_is_login_blocked
from apps.accounts.models import UserProfile
from apps.accounts.public import ARCHIVE_ROLE_NAME, archive_staged_account, stage_imported_account
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Curriculum, Enrollment, Program, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType

User = get_user_model()

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="Live registrar/account guards require PostgreSQL."),
]

PASSWORD = "Archive-PG-Password-123!"

_SAR_INSERT = (
    "INSERT INTO registrar_studentacademicrecord "
    "(id, created_at, updated_at, organization_id, student_id, program_id, "
    " curriculum_id, group_id, admission_year, status, is_active) "
    "VALUES (gen_random_uuid(), now(), now(), %s, %s, %s, %s, NULL, 2019, 'enrolled', TRUE)"
)


class ArchivedAccountPostgresTests(TestCase):
    evidence_digest = "c" * 64
    evidence_reason = "signed_authoritative_export"

    def setUp(self):
        self.actor = User.objects.create_superuser(
            "archive_pg_root",
            "archive-pg-root@example.com",
            "Root-Password-123!",
        )
        self.organization = Organization.objects.create(
            name="Archive PG University",
            slug="archive-pg-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.actor,
            status="active",
            is_active=True,
        )
        self.student_role = self.organization.roles.get(name="student")
        self.alumni_role = self.organization.roles.get(name=ARCHIVE_ROLE_NAME)

    # -- köməkçilər ------------------------------------------------------

    def _stage(self, suffix):
        return stage_imported_account(
            organization=self.organization,
            role=self.student_role,
            actor=self.actor,
            username=f"myedu.alumni.{suffix}",
            email=f"myedu-alumni-{suffix}@example.test",
            student_identifier=f"ALM-{suffix}",
        ).user

    def _archive(self, user):
        Membership.objects.filter(user=user, organization=self.organization).update(role=self.alumni_role)
        return archive_staged_account(
            user=user,
            organization=self.organization,
            expected_role=self.alumni_role,
            actor=self.actor,
            email_authoritative=True,
            email_authority_evidence_digest=self.evidence_digest,
            email_authority_reason_code=self.evidence_reason,
        )

    def _program(self, code):
        speciality = OrgUnit.objects.create(
            organization=self.organization,
            slug=f"archive-spec-{code.lower()}",
            unit_type=OrgUnitType.SPECIALTY,
            name=f"İxtisas {code}",
        )
        return Program.objects.create(
            organization=self.organization,
            specialty_unit=speciality,
            code=code,
            name=f"İxtisas {code}",
            degree_level="bachelor",
            ects_total=240,
        )

    def _offering(self, code):
        subject = Subject.objects.create(organization=self.organization, code=code, name=f"Fənn {code}", ects=5)
        period = AcademicPeriod.objects.create(
            organization=self.organization,
            name=f"Payız {code}",
            academic_year="2021/2022",
            period_type=AcademicPeriodType.SEMESTER,
            start_date=datetime.date(2021, 9, 15),
            end_date=datetime.date(2022, 1, 20),
        )
        return CourseOffering.objects.create(
            organization=self.organization, subject=subject, period=period, lesson_hours=0, is_active=True
        )

    # -- əsas sübut ------------------------------------------------------

    def test_archiving_opens_the_registrar_guard_without_opening_the_login(self):
        user = self._stage("a1")
        program = self._program("ARC-1")
        curriculum = Curriculum.objects.create(organization=self.organization, program=program, admission_year=2019)
        arguments = [str(self.organization.pk), user.pk, str(program.pk), str(curriculum.pk)]
        offering = self._offering("ARC-64")

        # ƏVVƏL: staged hesab → trigger rədd edir (mövcud problemin sübutu).
        with pytest.raises(DatabaseError) as refused:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(_SAR_INSERT, arguments)
        self.assertIn("lacks an active authorized membership", str(refused.value))

        self._archive(user)
        user.refresh_from_db()
        user.set_password(PASSWORD)
        user.save(update_fields=["password"])

        # SONRA: eyni statement keçir — trigger-ə HEÇ NƏ dəyişdirilmədən.
        with connection.cursor() as cursor:
            cursor.execute(_SAR_INSERT, arguments)

        # A-nın əsas məqsədi: tarixi jurnal yazılışı da yaradıla bilir.
        enrollment = Enrollment.objects.create(
            organization=self.organization, student=user, offering=offering, kind="mandatory"
        )
        self.assertIsNotNone(enrollment.pk)

        # …və giriş HƏLƏ DƏ bağlıdır.
        self.assertEqual(user.profile.access_state, UserProfile.AccessState.ARCHIVED)
        self.assertTrue(user.is_active)
        self.assertTrue(user_access_is_login_blocked(user))
        self.assertIsNone(authenticate(username=user.username, password=PASSWORD))

    def test_leaving_the_archived_state_needs_the_same_evidence_as_staged(self):
        """0016: ``archived → active`` evidence-siz UPDATE-lə açıla bilməz."""

        user = self._stage("a2")
        self._archive(user)

        with pytest.raises(DatabaseError) as refused:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE accounts_userprofile SET access_state = 'active' WHERE user_id = %s",
                        [user.pk],
                    )
        self.assertIn("accounts_staged_activation_service_required", str(refused.value))

        user.refresh_from_db()
        self.assertEqual(user.profile.access_state, UserProfile.AccessState.ARCHIVED)

    def test_the_staged_guard_is_untouched_by_the_archive_state(self):
        """Reqressiya: ``staged`` budaqları 0016-dan sonra da hərfi qalır."""

        user = self._stage("a3")

        with pytest.raises(DatabaseError) as refused:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE accounts_userprofile SET access_state = 'active' WHERE user_id = %s",
                        [user.pk],
                    )
        self.assertIn("accounts_staged_activation_service_required", str(refused.value))

        # ``staged`` hesabın ``is_active``-i hələ də birbaşa qaldırıla bilmir.
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE auth_user SET is_active = TRUE WHERE id = %s", [user.pk])
