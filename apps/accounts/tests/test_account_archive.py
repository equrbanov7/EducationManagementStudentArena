"""Arxiv hesab (məzun/xaric) — giriş BAĞLI, data AÇIQ.

Bu dəst spec A-nın sübutudur: ``UserProfile.access_state='archived'`` hesabın
``is_active=True`` olmasına BAXMAYARAQ bütün autentifikasiya səthlərini bağlayır
(``registrar_guard_active_member`` üçün ``is_active`` qəsdən True saxlanılır),
adi tələbə isə heç bir şəkildə təsirlənmir.
"""

from django.contrib.auth import authenticate, get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.identity import user_access_is_login_blocked, user_access_is_staged
from apps.accounts.models import UserProfile
from apps.accounts.public import ARCHIVE_ROLE_NAME, archive_staged_account, stage_imported_account
from apps.accounts.services import IdentityAccessError
from apps.accounts.services.rim import account_status, search_users
from apps.accounts.services.rim.policy import RimActor, resolve_actor
from apps.accounts.services.rim.search import STATUS_ACTIVE, STATUS_ARCHIVED
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

PASSWORD = "Archive-Password-123!"


class ArchivedAccountTests(TestCase):
    evidence_digest = "b" * 64
    evidence_reason = "signed_authoritative_export"

    def setUp(self):
        self.actor = User.objects.create_superuser(
            username="archive_root",
            email="archive-root@example.com",
            password="Root-Password-123!",
        )
        self.organization = Organization.objects.create(
            name="Archive University",
            slug="archive-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.actor,
            status="active",
            is_active=True,
        )
        self.student_role = self.organization.roles.get(name="student")
        self.alumni_role = self.organization.roles.get(name=ARCHIVE_ROLE_NAME)

    # -- köməkçilər ------------------------------------------------------

    def _stage(self, *, username, email, identifier, role=None):
        return stage_imported_account(
            organization=self.organization,
            role=role or self.student_role,
            actor=self.actor,
            username=username,
            email=email,
            student_identifier=identifier,
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

    def _archived_user(self):
        user = self._stage(
            username="legacy_alumni_9001",
            email="legacy.alumni.9001@example.com",
            identifier="ALM-9001",
        )
        self._archive(user)
        user.refresh_from_db()
        user.set_password(PASSWORD)
        user.save(update_fields=["password"])
        return user

    def _active_student(self):
        user = User.objects.create_user(
            username="live_student_9002",
            email="live.student.9002@example.com",
            password=PASSWORD,
            is_active=True,
        )
        profile = user.profile
        profile.organization = self.organization
        profile.save(update_fields=["organization", "updated_at"])
        Membership.objects.create(
            user=user,
            organization=self.organization,
            role=self.student_role,
            is_primary=True,
            is_active=True,
        )
        return user

    # -- A1/A2: vəziyyət və rol ------------------------------------------

    def test_archiving_keeps_the_account_active_for_the_registrar_triggers(self):
        user = self._stage(
            username="legacy_alumni_1",
            email="legacy.alumni.1@example.com",
            identifier="ALM-1",
        )
        result = self._archive(user)
        user.refresh_from_db()
        membership = Membership.objects.get(user=user, organization=self.organization)

        self.assertTrue(result.archived)
        # `registrar_member_has_permission` DÖRD şərti tələb edir; hamısı ödənir.
        self.assertTrue(user.is_active)
        self.assertTrue(membership.is_active)
        self.assertTrue(membership.role.is_active)
        self.assertTrue(self.organization.is_active)
        self.assertEqual(user.profile.access_state, UserProfile.AccessState.ARCHIVED)
        # A1: rol HÜQUQ vermir.
        self.assertEqual(membership.role.name, ARCHIVE_ROLE_NAME)
        self.assertEqual(membership.role.permissions, [])
        self.assertTrue(
            AuditLog.objects.filter(organization=self.organization, reason="legacy_account_archived").exists()
        )

    def test_archiving_is_idempotent(self):
        user = self._stage(
            username="legacy_alumni_2",
            email="legacy.alumni.2@example.com",
            identifier="ALM-2",
        )
        self._archive(user)
        second = self._archive(user)

        self.assertFalse(second.archived)
        user.refresh_from_db()
        self.assertEqual(user.profile.access_state, UserProfile.AccessState.ARCHIVED)

    def test_an_archived_account_can_never_be_an_actor(self):
        archived = self._archived_user()
        target = self._stage(
            username="legacy_alumni_3",
            email="legacy.alumni.3@example.com",
            identifier="ALM-3",
        )
        Membership.objects.filter(user=archived, organization=self.organization).update(role=self.alumni_role)

        with self.assertRaises(Exception) as ctx:
            archive_staged_account(
                user=target,
                organization=self.organization,
                expected_role=self.alumni_role,
                actor=archived,
                email_authoritative=True,
                email_authority_evidence_digest=self.evidence_digest,
                email_authority_reason_code=self.evidence_reason,
            )
        self.assertIn("identity_staged_actor_denied", str(ctx.exception))

    # -- A2: giriş qapıları ----------------------------------------------

    def test_the_login_predicates_separate_staged_from_login_blocked(self):
        staged = self._stage(
            username="legacy_alumni_4",
            email="legacy.alumni.4@example.com",
            identifier="ALM-4",
        )
        archived = self._archived_user()
        live = self._active_student()

        self.assertTrue(user_access_is_staged(staged))
        self.assertTrue(user_access_is_login_blocked(staged))
        # Arxiv `staged` DEYİL, amma girişi eyni dərəcədə bağlıdır.
        self.assertFalse(user_access_is_staged(archived))
        self.assertTrue(user_access_is_login_blocked(archived))
        self.assertFalse(user_access_is_login_blocked(live))

    def test_the_auth_backend_refuses_an_archived_account(self):
        archived = self._archived_user()
        self.assertIsNone(authenticate(username=archived.username, password=PASSWORD))
        # Nəzarət nümunəsi: eyni parolla adi tələbə girə bilir.
        live = self._active_student()
        self.assertIsNotNone(authenticate(username=live.username, password=PASSWORD))

    def test_an_archived_account_cannot_use_the_staff_portal(self):
        archived = self._archived_user()
        client = Client()
        response = client.post(
            reverse("accounts:staff_login"),
            {"username": archived.username, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)  # forma yenidən göstərilir
        self.assertNotIn("_auth_user_id", client.session)

    def test_an_archived_account_cannot_use_the_student_portal(self):
        archived = self._archived_user()
        client = Client()
        response = client.post(
            reverse("accounts:student_login"),
            {"username": archived.username, "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

    def test_a_live_student_still_logs_in_through_the_student_portal(self):
        live = self._active_student()
        client = Client()
        response = client.post(
            reverse("accounts:student_login"),
            {"username": live.username, "password": PASSWORD},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(str(client.session.get("_auth_user_id")), str(live.pk))

    def test_a_session_that_survives_archiving_is_logged_out_by_the_middleware(self):
        user = self._stage(
            username="legacy_alumni_5",
            email="legacy.alumni.5@example.com",
            identifier="ALM-5",
        )
        # Əvvəlcə adi aktivasiya yolu ilə girişi olan hesab qururuq.
        Membership.objects.filter(user=user, organization=self.organization).update(role=self.alumni_role)
        self._archive(user)
        user.refresh_from_db()
        user.set_password(PASSWORD)
        user.save(update_fields=["password"])

        client = Client()
        client.force_login(user)
        response = client.get(reverse("accounts:profile"))
        # Middleware sessiyanı ilk request-də söndürür → login-ə yönləndirmə.
        self.assertIn(response.status_code, (302, 301))
        self.assertNotIn("_auth_user_id", client.session)

    def test_the_otp_login_endpoint_never_issues_a_code_for_an_archived_account(self):
        """OTP GİRİŞ yoludur — parolsuz keçid burada da bağlı olmalıdır."""

        from django.core import mail

        archived = self._archived_user()
        mail.outbox = []
        response = Client().post(
            reverse("accounts:send_otp_api"),
            data={"email": archived.email, "purpose": "login"},
            content_type="application/json",
        )
        # Səssiz 202 (email sızdırılmır) + HEÇ BİR məktub.
        self.assertEqual(response.status_code, 202)
        self.assertEqual(mail.outbox, [])

    def test_password_reset_never_reaches_an_archived_account(self):
        from apps.accounts.forms import CustomPasswordResetForm

        archived = self._archived_user()
        form = CustomPasswordResetForm(data={"email": archived.email})
        self.assertTrue(form.is_valid())
        self.assertEqual(list(form.get_users(archived.email)), [])

    # -- A4: RİM görünürlüyü ---------------------------------------------

    def test_rim_search_finds_and_labels_the_archived_account(self):
        archived = self._archived_user()
        live = self._active_student()
        actor = RimActor(user=self.actor, organization=self.organization, level=999, is_superadmin=True)

        self.assertEqual(account_status(archived), STATUS_ARCHIVED)
        self.assertEqual(account_status(live), STATUS_ACTIVE)

        found = search_users(actor, query="legacy_alumni_9001", status="all")
        self.assertEqual([row.pk for row in found["results"]], [archived.pk])

        archived_only = search_users(actor, query="", status=STATUS_ARCHIVED)
        self.assertEqual([row.pk for row in archived_only["results"]], [archived.pk])

        active_only = search_users(actor, query="", status=STATUS_ACTIVE)
        self.assertNotIn(archived.pk, [row.pk for row in active_only["results"]])
        self.assertIn(live.pk, [row.pk for row in active_only["results"]])

    def test_a_tenant_scoped_rim_operator_also_sees_the_archived_account(self):
        """A4: arxiv üzvlüyü AKTİV olduğu üçün RİM sahəsinə öz-özünə düşür."""

        archived = self._archived_user()
        operator = User.objects.create_user(
            username="rim_operator",
            email="rim.operator@example.com",
            password=PASSWORD,
            is_active=True,
        )
        operator.profile.organization = self.organization
        operator.profile.save(update_fields=["organization", "updated_at"])
        Membership.objects.create(
            user=operator,
            organization=self.organization,
            role=self.organization.roles.get(name="ikt_rehber"),
            is_primary=True,
            is_active=True,
        )
        actor = RimActor(
            user=operator,
            organization=self.organization,
            level=88,
            is_superadmin=False,
            permissions={"user.search"},
        )

        found = search_users(actor, query="legacy_alumni_9001", status=STATUS_ARCHIVED)
        self.assertEqual([row.pk for row in found["results"]], [archived.pk])

    def test_rim_cannot_unblock_an_archived_account_into_a_working_login(self):
        from apps.accounts.services.rim import RimAccessError
        from apps.accounts.services.rim.lifecycle import unblock_user

        archived = self._archived_user()
        actor = RimActor(user=self.actor, organization=self.organization, level=999, is_superadmin=True)
        with self.assertRaises(RimAccessError) as ctx:
            unblock_user(actor, archived, reason="")
        self.assertEqual(ctx.exception.reason_code, "archived_account")

    # -- fail-closed -----------------------------------------------------

    def test_archiving_refuses_a_membership_set_that_is_not_the_archive_role(self):
        user = self._stage(
            username="legacy_alumni_6",
            email="legacy.alumni.6@example.com",
            identifier="ALM-6",
        )
        with self.assertRaises(IdentityAccessError) as ctx:
            archive_staged_account(
                user=user,
                organization=self.organization,
                expected_role=self.alumni_role,  # üzvlük hələ `student` rolundadır
                actor=self.actor,
                email_authoritative=True,
                email_authority_evidence_digest=self.evidence_digest,
                email_authority_reason_code=self.evidence_reason,
            )
        self.assertEqual(ctx.exception.code, "identity_membership_set_mismatch")
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.access_state, UserProfile.AccessState.STAGED)

    def test_resolve_actor_is_importable_for_the_rim_surface(self):
        # Sadə smoke: RİM aktoru həll edən funksiya arxiv dəyişikliyindən sonra da işləyir.
        self.assertTrue(callable(resolve_actor))
