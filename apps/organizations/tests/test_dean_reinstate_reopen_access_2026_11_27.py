"""«Bərpa et» təşkilatsız profilin də girişini açır (2026-11-27).

Hal (QA klonu, tətbiq rolu ilə yoxlanılıb): xaric əmri girişi ``registrar.movements._sync_access_state``-də bağlayır və
o, ``organization IS NULL`` profili də tutur; bərpa yolu isə yalnız ``organization = org`` axtarırdı — tələbə akademik
olaraq bərpa olunur, hesabı ``archived`` qalırdı (xəbərdarlıq da çıxmırdı). Bu fayl həm dekan (fakültə scope-u), həm
RİM (təşkilat geneli) yolunu, başqa fakültənin dekanının rəddini, dondurma/məzun yollarını, tenant sərhədini və
``reopen_reinstated_student_access_20261127`` əmrini yoxlayır. ``RlsAppRoleTest`` axını məhdud ``rls_app_role`` ilə
(RLS siyasətləri tətbiq olunur) Postgres-də işlədir.
"""

from __future__ import annotations

import datetime
from io import StringIO

from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import connection, transaction

import pytest

from apps.accounts.identity_models import AccountRestoreEvidence
from apps.accounts.models import UserProfile
from apps.accounts.services.identity_reinstate import order_evidence_digest, reinstate_student_access
from apps.accounts.services.people import movements as movement_service
from apps.accounts.services.people.permissions import PeopleActor
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization
from apps.organizations.tests.test_dean_office_student_movement_2026_11_27 import DeanOfficeBase
from apps.registrar.models import StudentMovement
from apps.registrar.public import movements as domain
from core.constants import OrganizationType
from core.rls import apply_rls_request_context, bypass_rls

CMD = "reopen_reinstated_student_access_20261127"


class OrglessBase(DeanOfficeBase):
    PREFIX = "dro"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.rim = cls._member("dro_rim", cls.org.roles.get(name="ikt_rehber"))
            cls.superadmin = cls._member("dro_sa", cls.org.roles.get(name="ikt_rehber"))
            cls.superadmin.is_superuser = True
            cls.superadmin.save(update_fields=["is_superuser"])
            for user in (cls.real_dean, cls.rim, cls.superadmin):
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])
            # Köhnə idxal / nümunə hesab forması: profil təşkilatsızdır (klonda video.telebe*, numune.telebe.*).
            UserProfile.objects.filter(user__in=[cls.student, cls.host]).update(organization=None)

    def profile_of(self, user):
        with bypass_rls():
            return UserProfile.objects.get(user=user)

    def expel(self, user, student, kind="expulsion"):
        response = self.post(user, self.record_of(student), kind)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.profile_of(student).access_state, "archived")

    def reinstate(self, user, student):
        record = self.record_of(student)
        return self.post(user, record, "reinstatement", target_group=str(record.group_id))


class OrglessReinstateTest(OrglessBase):
    def assert_reopened(self, response, student):
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["movement"]["access_notice"], "")
        self.assertEqual(self.record_of(student).status, "enrolled")
        profile = self.profile_of(student)
        self.assertEqual(profile.access_state, "active")
        # Təşkilatsız profil bərpa təşkilatına bağlanır (DB funksiyası 0039 ilə eyni).
        self.assertEqual(profile.organization_id, self.org.pk)
        with bypass_rls():
            self.assertTrue(
                AccountRestoreEvidence.objects.filter(
                    organization=self.org, user_ref=str(student.pk), reason_code="student_reinstatement_order"
                ).exists()
            )
            self.assertTrue(
                AuditLog.objects.filter(object_id=str(student.pk), reason="student_reinstatement_order").exists()
            )

    def test_dean_expels_then_reinstates_orgless_profile(self):
        self.expel(self.real_dean, self.student)
        self.assert_reopened(self.reinstate(self.real_dean, self.student), self.student)

    def test_dean_office_assistant_and_vice_dean_reopen_too(self):
        for user, student in ((self.doa, self.student), (self.vice, self.host)):
            self.expel(user, student)
            self.assert_reopened(self.reinstate(user, student), student)

    def test_rim_actor_expels_then_reinstates_orgless_profile(self):
        self.expel(self.rim, self.host)
        self.assert_reopened(self.reinstate(self.rim, self.host), self.host)

    def test_rim_path_with_org_bound_profile_is_unchanged(self):
        with bypass_rls():
            UserProfile.objects.filter(user=self.far_student).update(organization=self.org)
        self.expel(self.rim, self.far_student)
        self.assert_reopened(self.reinstate(self.rim, self.far_student), self.far_student)

    def test_graduation_then_reinstatement_reopens(self):
        self.expel(self.real_dean, self.student, kind="graduation")
        self.assert_reopened(self.reinstate(self.real_dean, self.student), self.student)

    def test_other_faculty_dean_is_still_refused(self):
        self.expel(self.real_dean, self.host)
        response = self.reinstate(self.far, self.host)
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(self.record_of(self.host).status, "expelled")
        self.assertEqual(self.profile_of(self.host).access_state, "archived")

    def test_freeze_does_not_archive_and_reinstatement_is_silent(self):
        record = self.freeze(self.real_dean, self.student)
        self.assertEqual(self.profile_of(self.student).access_state, "active")
        response = self.post(self.real_dean, record, "reinstatement", target_group=str(record.group_id))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["movement"]["access_notice"], "")
        profile = self.profile_of(self.student)
        self.assertEqual(profile.access_state, "active")
        self.assertIsNone(profile.organization_id)  # toxunulmur — bərpa yolu açılmadı


class TenantBoundaryTest(OrglessBase):
    """Təşkilatsız profil yalnız hesabın BAŞQA tenant-da üzvlüyü yoxdursa qəbul olunur."""

    def test_orgless_profile_with_foreign_membership_is_refused(self):
        self.expel(self.real_dean, self.student)
        with bypass_rls():
            other = Organization.objects.create(
                name="DRO Other",
                slug="dro-other",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            Membership.objects.create(
                user=self.student, organization=other, role=other.roles.get(name="student"), is_active=True
            )
            with self.assertRaises(PermissionDenied):
                with transaction.atomic():
                    reinstate_student_access(
                        user=self.student, organization=self.org, actor=self.rim, evidence_digest="d" * 64
                    )
        self.assertEqual(self.profile_of(self.student).access_state, "archived")
        # Xidmət qatı yan keçilsə də: bərpa forması `reopen_access` xəbərdarlığı verir, giriş açılmır.
        response = self.reinstate(self.real_dean, self.student)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotEqual(response.json()["movement"]["access_notice"], "")
        self.assertEqual(self.profile_of(self.student).access_state, "archived")

    def test_db_function_refuses_foreign_membership_too(self):
        if connection.vendor != "postgresql":
            self.skipTest("DB funksiyası yalnız PostgreSQL-də")
        self.expel(self.real_dean, self.student)
        with bypass_rls():
            other = Organization.objects.create(
                name="DRO Other2",
                slug="dro-other2",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            Membership.objects.create(
                user=self.student, organization=other, role=other.roles.get(name="student"), is_active=True
            )
        from django.db import DatabaseError

        with self.assertRaisesMessage(DatabaseError, "accounts_reinstate_profile_cross_tenant"):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(self.rim.pk)])
                cursor.execute(
                    "SELECT public.accounts_reinstate_student_identity(gen_random_uuid(), %s, %s, %s, %s)",
                    [self.student.pk, str(self.org.pk), self.rim.pk, "e" * 64],
                )
        self.assertEqual(self.profile_of(self.student).access_state, "archived")


@pytest.mark.postgres
class RlsAppRoleTest(OrglessBase):
    """Bütün axın məhdud ``rls_app_role`` ilə — RLS siyasətləri dekanın kontekstində tətbiq olunur."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("RLS yalnız PostgreSQL-də")

    def run_as(self, user, kind, student, **extra):
        role = Membership.objects.select_related("role").get(user=user, organization=self.org).role
        actor = PeopleActor(
            user=user, organization=self.org, permissions=frozenset(role.permissions), is_superadmin=False
        )
        record = self.record_of(student)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE rls_app_role")
            apply_rls_request_context(user_id=user.pk, org_id=self.org.pk, local=True)
            row = movement_service.create_movement(
                actor,
                record_id=str(record.pk),
                kind=kind,
                order_number="27/R",
                order_date="2026-11-27",
                reason="",
                **extra,
            )
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
        return row

    def test_dean_under_rls_reopens_orgless_and_bound_profiles(self):
        with bypass_rls():
            UserProfile.objects.filter(user=self.host).update(organization=self.org)
        for student in (self.student, self.host):
            self.run_as(self.real_dean, "expulsion", student)
            self.assertEqual(self.profile_of(student).access_state, "archived")
            group = str(self.record_of(student).group_id)
            row = self.run_as(self.real_dean, "reinstatement", student, target_group_id=group)
            self.assertEqual(row["access_notice"], "", student.username)
            self.assertEqual(self.profile_of(student).access_state, "active", student.username)

    def test_other_faculty_dean_under_rls_is_refused(self):
        self.run_as(self.real_dean, "expulsion", self.student)
        from apps.accounts.services.rim.policy import RimAccessError

        with self.assertRaises(RimAccessError) as caught:
            self.run_as(
                self.far, "reinstatement", self.student, target_group_id=str(self.record_of(self.student).group_id)
            )
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(self.profile_of(self.student).access_state, "archived")


class ReopenCommandTest(OrglessBase):
    """Artıq verilmiş bərpa əmrləri (köhnə kod girişi açmamışdı) — əmr onları tapır, yalnız onları açır."""

    def stale_reinstatement(self, student):
        """Köhnə kodun nəticəsi: xaric → bərpa əmri (domen), giriş ARXİVDƏ qalır."""
        self.expel(self.real_dean, student)
        with bypass_rls():
            record = self.record_of(student)
            domain.create_movement(
                record=record,
                kind=domain.MovementKind.REINSTATEMENT,
                order_number="OLD-1",
                order_date=datetime.date(2026, 11, 20),
                reason="",
                actor=self.real_dean,
                period=self.period,
                new_group=record.group,
            )
        self.assertEqual(self.record_of(student).status, "enrolled")
        self.assertEqual(self.profile_of(student).access_state, "archived")

    def call(self, *extra):
        out = StringIO()
        with bypass_rls():
            call_command(CMD, "--org", self.org.slug, "--actor", self.superadmin.username, *extra, stdout=out)
        return out.getvalue()

    def test_dry_run_apply_and_undo(self):
        self.stale_reinstatement(self.student)
        # Köhnə köçürmə izi: arxiv hesab, enrolled qeyd, bərpa əmri YOX — toxunulmur.
        with bypass_rls():
            UserProfile.objects.filter(user=self.far_student).update(
                organization=self.org, access_state=UserProfile.AccessState.ARCHIVED
            )

        out = self.call()
        self.assertIn("mode=dry_run", out)
        self.assertIn("candidates=1", out)
        self.assertIn("reopened=1", out)
        self.assertIn("skip_no_reinstatement_order=1", out)
        self.assertIn("orgless_profile=1", out)
        self.assertEqual(self.profile_of(self.student).access_state, "archived")

        out = self.call("--apply")
        self.assertIn("reopened=1", out)
        batch = [line.split("batch=")[1].strip() for line in out.splitlines() if "batch=" in line][0]
        self.assertEqual(self.profile_of(self.student).access_state, "active")
        self.assertEqual(self.profile_of(self.far_student).access_state, "archived")
        self.assertNotIn("candidates=", self.call())

        out = self.call("--undo", batch, "--apply")
        self.assertIn("rearchived=1", out)
        self.assertEqual(self.profile_of(self.student).access_state, "archived")

    def test_requires_superadmin_actor(self):
        from django.core.management.base import CommandError

        with self.assertRaisesMessage(CommandError, "actor_must_be_active_superuser"):
            with bypass_rls():
                call_command(CMD, "--org", self.org.slug, "--actor", self.real_dean.username, stdout=StringIO())

    def test_digest_matches_the_reinstatement_order(self):
        self.stale_reinstatement(self.host)
        self.call("--apply")
        with bypass_rls():
            movement = StudentMovement.objects.filter(record=self.record_of(self.host), kind="reinstatement").latest(
                "created_at"
            )
            evidence = AccountRestoreEvidence.objects.get(organization=self.org, user_ref=str(self.host.pk))
        self.assertEqual(
            evidence.evidence_digest,
            order_evidence_digest(
                order_number=movement.order_number,
                order_date=movement.order_date,
                record_id=movement.record_id,
                actor_id=self.superadmin.pk,
            ),
        )
