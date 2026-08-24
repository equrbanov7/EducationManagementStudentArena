from importlib import import_module
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, authenticate, get_user_model
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.identity import StagedAccountAccessError
from apps.accounts.models import AccountActivationEvidence, EmailOTP, UserProfile
from apps.accounts.services import (
    AccountDeletionError,
    IdentityAccessError,
    IdentityCollisionError,
    activate_staged_account,
    activate_user_account,
    issue_email_otp,
    restore_account,
    stage_imported_account,
    verify_email_otp,
)
from apps.accounts.services.account_deletion import unblock_account
from apps.accounts.services.view_as import (
    MODE_FULL,
    VIEW_AS_SESSION_KEY,
    build_target_queryset,
    resolve_view_as_request,
    start_view_as,
)
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


class IdentityAccessServiceTests(TestCase):
    evidence_digest = "a" * 64
    evidence_reason = "signed_authoritative_export"

    def setUp(self):
        self.actor = User.objects.create_superuser(
            username="identity_root",
            email="identity-root@example.com",
            password="Root-Password-123!",
        )
        self.organization = Organization.objects.create(
            name="Identity University",
            slug="identity-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.actor,
            status="active",
            is_active=True,
        )
        self.student_role = self.organization.roles.get(name="student")

    def _stage(self, **overrides):
        values = {
            "organization": self.organization,
            "role": self.student_role,
            "actor": self.actor,
            "username": "legacy_student_1001",
            "email": "legacy.student.1001@example.com",
            "student_identifier": "STU-1001",
        }
        values.update(overrides)
        return stage_imported_account(**values)

    def test_new_import_is_locked_unusable_and_sends_nothing(self):
        result = self._stage()
        user = result.user
        user.refresh_from_db()
        profile = user.profile
        membership = Membership.objects.get(user=user, organization=self.organization)

        self.assertTrue(result.created)
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(profile.access_state, UserProfile.AccessState.STAGED)
        self.assertEqual(profile.institutional_identifier, "STU-1001")
        self.assertFalse(profile.email_verified)
        self.assertFalse(profile.password_change_required)
        self.assertFalse(membership.is_active)
        self.assertEqual(mail.outbox, [])
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.actor,
                organization=self.organization,
                reason="legacy_account_staged",
            ).exists()
        )

    def test_explicit_existing_match_is_byte_for_byte_preserved(self):
        existing = User.objects.create_user(
            username="existing_identity",
            email="existing.identity@example.com",
            password="Existing-Password-123!",
            is_active=True,
        )
        profile = existing.profile
        profile.organization = self.organization
        profile.email_verified = True
        profile.student_specialization = "Existing specialization"
        profile.save(
            update_fields=[
                "organization",
                "email_verified",
                "student_specialization",
                "updated_at",
            ]
        )
        membership = Membership.objects.create(
            user=existing,
            organization=self.organization,
            role=self.student_role,
            is_active=True,
            is_primary=True,
            assigned_by=self.actor,
        )
        before = {
            "user": tuple(
                User.objects.filter(pk=existing.pk).values_list(
                    "password",
                    "is_active",
                    "email",
                    "first_name",
                    "last_name",
                )[0]
            ),
            "profile": tuple(
                UserProfile.objects.filter(pk=profile.pk).values_list(
                    "organization_id",
                    "access_state",
                    "email_verified",
                    "student_specialization",
                    "updated_at",
                )[0]
            ),
            "membership": tuple(
                Membership.objects.filter(pk=membership.pk).values_list(
                    "role_id",
                    "is_active",
                    "is_primary",
                    "updated_at",
                )[0]
            ),
        }

        result = self._stage(existing_user=existing, username="ignored", email="ignored@example.com")

        after = {
            "user": tuple(
                User.objects.filter(pk=existing.pk).values_list(
                    "password",
                    "is_active",
                    "email",
                    "first_name",
                    "last_name",
                )[0]
            ),
            "profile": tuple(
                UserProfile.objects.filter(pk=profile.pk).values_list(
                    "organization_id",
                    "access_state",
                    "email_verified",
                    "student_specialization",
                    "updated_at",
                )[0]
            ),
            "membership": tuple(
                Membership.objects.filter(pk=membership.pk).values_list(
                    "role_id",
                    "is_active",
                    "is_primary",
                    "updated_at",
                )[0]
            ),
        }
        self.assertFalse(result.created)
        self.assertEqual(result.user.pk, existing.pk)
        self.assertEqual(after, before)
        self.assertEqual(mail.outbox, [])

    def test_existing_match_cross_tenant_stops_without_mutation(self):
        outsider = User.objects.create_user("identity_outside", email="outside@example.com")
        before = tuple(User.objects.filter(pk=outsider.pk).values_list("password", "is_active", "email")[0])

        with self.assertRaisesRegex(PermissionDenied, "identity_existing_user_cross_tenant"):
            self._stage(existing_user=outsider)

        self.assertEqual(
            tuple(User.objects.filter(pk=outsider.pk).values_list("password", "is_active", "email")[0]),
            before,
        )

    def test_canonical_collisions_stop_instead_of_merging(self):
        User.objects.create_user("ExistingCase", email="canonical@example.com")
        with self.assertRaisesRegex(IdentityCollisionError, "identity_username_collision"):
            self._stage(username=" existingcase ", email="other@example.com")
        with self.assertRaisesRegex(IdentityCollisionError, "identity_email_collision"):
            self._stage(username="new_identity", email=" CANONICAL@example.COM ")
        with self.assertRaisesRegex(IdentityCollisionError, "identity_cross_field_collision"):
            self._stage(username="canonical@example.com", email="cross-field@example.com")
        with self.assertRaisesRegex(IdentityCollisionError, "identity_username_collision"):
            self._stage(username="ＥｘｉｓｔｉｎｇＣａｓｅ", email="nfkc@example.com")

        owner = User.objects.create_user("identifier_owner", email="identifier-owner@example.com")
        owner.profile.organization = self.organization
        owner.profile.institutional_identifier = " Stu-Existing "
        owner.profile.save(update_fields=["organization", "institutional_identifier", "updated_at"])
        with self.assertRaisesRegex(IdentityCollisionError, "identity_student_identifier_collision"):
            self._stage(
                username="new_identifier_owner",
                email="new-identifier@example.com",
                student_identifier="stu-existing",
            )

    def test_staging_audit_failure_rolls_back_every_write(self):
        with patch("apps.accounts.services.identity_access.log_action", side_effect=RuntimeError("audit down")):
            with self.assertRaisesRegex(RuntimeError, "audit down"):
                self._stage()

        self.assertFalse(User.objects.filter(username="legacy_student_1001").exists())
        self.assertEqual(mail.outbox, [])

    def test_activation_is_authoritative_audited_idempotent_and_mail_free(self):
        staged = self._stage().user

        with self.assertRaisesRegex(IdentityAccessError, "identity_authoritative_email_required"):
            activate_staged_account(
                user=staged,
                organization=self.organization,
                expected_role=self.student_role,
                actor=self.actor,
                email_authoritative=False,
                email_authority_evidence_digest=self.evidence_digest,
                email_authority_reason_code=self.evidence_reason,
            )

        result = activate_staged_account(
            user=staged,
            organization=self.organization,
            expected_role=self.student_role,
            actor=self.actor,
            email_authoritative=True,
            email_authority_evidence_digest=self.evidence_digest,
            email_authority_reason_code=self.evidence_reason,
        )
        staged.refresh_from_db()
        staged.profile.refresh_from_db()
        membership = Membership.objects.get(user=staged, organization=self.organization)
        self.assertTrue(result.activated)
        self.assertTrue(staged.is_active)
        self.assertFalse(staged.has_usable_password())
        self.assertEqual(staged.profile.access_state, UserProfile.AccessState.ACTIVE)
        self.assertFalse(staged.profile.email_verified)
        self.assertTrue(membership.is_active)
        self.assertEqual(mail.outbox, [])
        evidence = AccountActivationEvidence.objects.get(
            organization=self.organization,
            user_ref=str(staged.pk),
        )
        self.assertEqual(evidence.role_ref, str(self.student_role.pk))
        self.assertEqual(evidence.actor_ref, str(self.actor.pk))
        self.assertEqual(evidence.evidence_digest, self.evidence_digest)
        self.assertEqual(evidence.reason_code, self.evidence_reason)
        self.assertIsNotNone(evidence.consumed_at)
        self.assertEqual(
            AuditLog.objects.filter(
                organization=self.organization,
                object_id=str(staged.pk),
                reason="legacy_account_activated",
            ).count(),
            1,
        )
        activation_log = AuditLog.objects.get(
            organization=self.organization,
            object_id=str(staged.pk),
            reason="legacy_account_activated",
        )
        self.assertEqual(
            activation_log.changes,
            {
                "activation_evidence_id": str(evidence.pk),
                "email_authority_evidence_digest": self.evidence_digest,
                "email_authority_reason_code": self.evidence_reason,
                "role_id": str(self.student_role.pk),
            },
        )

        repeated = activate_staged_account(
            user=staged,
            organization=self.organization,
            expected_role=self.student_role,
            actor=self.actor,
            email_authoritative=True,
            email_authority_evidence_digest=self.evidence_digest,
            email_authority_reason_code=self.evidence_reason,
        )
        self.assertFalse(repeated.activated)
        self.assertEqual(
            AuditLog.objects.filter(
                organization=self.organization,
                object_id=str(staged.pk),
                reason="legacy_account_activated",
            ).count(),
            1,
        )
        self.assertEqual(AccountActivationEvidence.objects.filter(user_ref=str(staged.pk)).count(), 1)
        with self.assertRaisesRegex(IdentityAccessError, "identity_activation_evidence_mismatch"):
            activate_staged_account(
                user=staged,
                organization=self.organization,
                expected_role=self.student_role,
                actor=self.actor,
                email_authoritative=True,
                email_authority_evidence_digest="b" * 64,
                email_authority_reason_code=self.evidence_reason,
            )

    def test_normal_active_account_is_not_mislabeled_as_idempotent_activation(self):
        normal = User.objects.create_user(
            "normal_active_identity",
            email="normal-active-identity@example.com",
            password="Normal-Password-123!",
        )
        normal.profile.organization = self.organization
        normal.profile.save(update_fields=["organization", "updated_at"])
        Membership.objects.create(
            user=normal,
            organization=self.organization,
            role=self.student_role,
            assigned_by=self.actor,
            is_active=True,
            is_primary=True,
        )
        with self.assertRaisesRegex(IdentityAccessError, "identity_active_without_activation_evidence"):
            activate_staged_account(
                user=normal,
                organization=self.organization,
                expected_role=self.student_role,
                actor=self.actor,
                email_authoritative=True,
                email_authority_evidence_digest=self.evidence_digest,
                email_authority_reason_code=self.evidence_reason,
            )

    def test_activation_audit_failure_rolls_back_user_profile_and_membership(self):
        staged = self._stage().user
        with patch("apps.accounts.services.identity_access.log_action", side_effect=RuntimeError("audit down")):
            with self.assertRaisesRegex(RuntimeError, "audit down"):
                activate_staged_account(
                    user=staged,
                    organization=self.organization,
                    expected_role=self.student_role,
                    actor=self.actor,
                    email_authoritative=True,
                    email_authority_evidence_digest=self.evidence_digest,
                    email_authority_reason_code=self.evidence_reason,
                )

        staged.refresh_from_db()
        staged.profile.refresh_from_db()
        membership = Membership.objects.get(user=staged, organization=self.organization)
        self.assertFalse(staged.is_active)
        self.assertEqual(staged.profile.access_state, UserProfile.AccessState.STAGED)
        self.assertFalse(membership.is_active)
        self.assertFalse(AccountActivationEvidence.objects.filter(user_ref=str(staged.pk)).exists())

    def test_activation_requires_evidence_reason_and_exact_locked_membership_set(self):
        staged = self._stage().user
        common = {
            "user": staged,
            "organization": self.organization,
            "expected_role": self.student_role,
            "actor": self.actor,
            "email_authoritative": True,
        }
        with self.assertRaisesRegex(IdentityAccessError, "identity_email_authority_evidence_required"):
            activate_staged_account(
                **common,
                email_authority_evidence_digest="not-a-digest",
                email_authority_reason_code=self.evidence_reason,
            )
        with self.assertRaisesRegex(IdentityAccessError, "identity_email_authority_reason_invalid"):
            activate_staged_account(
                **common,
                email_authority_evidence_digest=self.evidence_digest,
                email_authority_reason_code="free_text_is_not_a_reason_code",
            )

        second_role = self.organization.roles.get(name="member")
        Membership.objects.create(
            user=staged,
            organization=self.organization,
            role=second_role,
            assigned_by=self.actor,
            is_active=False,
        )
        with self.assertRaisesRegex(IdentityAccessError, "identity_membership_set_mismatch"):
            activate_staged_account(
                **common,
                email_authority_evidence_digest=self.evidence_digest,
                email_authority_reason_code=self.evidence_reason,
            )
        staged.refresh_from_db()
        staged.profile.refresh_from_db()
        self.assertFalse(staged.is_active)
        self.assertEqual(staged.profile.access_state, UserProfile.AccessState.STAGED)

    def test_non_member_actor_cannot_stage_or_activate(self):
        outsider = User.objects.create_user("identity_operator_outside", password="Strong-Password-123!")
        with self.assertRaisesRegex(PermissionDenied, "identity_permission_denied"):
            self._stage(actor=outsider)

        staged = self._stage().user
        with self.assertRaisesRegex(PermissionDenied, "identity_permission_denied"):
            activate_staged_account(
                user=staged,
                organization=self.organization,
                expected_role=self.student_role,
                actor=outsider,
                email_authoritative=True,
                email_authority_evidence_digest=self.evidence_digest,
                email_authority_reason_code=self.evidence_reason,
            )


class StagedAuthenticationFlowTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(
            "flow_owner",
            "flow-owner@example.com",
            "Owner-Password-123!",
        )
        self.organization = Organization.objects.create(
            name="Staged Flow Org",
            slug="staged-flow-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.role = self.organization.roles.get(name="student")
        self.staged = stage_imported_account(
            organization=self.organization,
            role=self.role,
            actor=self.owner,
            username="staged_flow_user",
            email="staged-flow@example.com",
            student_identifier="FLOW-1",
        ).user
        self.staged.set_password("Staged-Password-123!")
        self.staged.save(update_fields=["password"])
        # SQLite has no PostgreSQL trigger; deliberately model a corrupted raw
        # is_active flag to prove access_state remains an independent deny gate.
        User.objects.filter(pk=self.staged.pk).update(is_active=True)
        self.staged.refresh_from_db()

    def test_only_staged_aware_backend_is_configured_and_normal_auth_still_works(self):
        self.assertEqual(settings.AUTHENTICATION_BACKENDS, ["apps.accounts.backends.EmailOrUsernameBackend"])
        normal = User.objects.create_user(
            "NormalCaseUser",
            email="normal-case@example.com",
            password="Normal-Password-123!",
        )
        self.assertEqual(
            authenticate(username=" normalcaseuser ", password="Normal-Password-123!").pk,
            normal.pk,
        )
        self.assertEqual(
            authenticate(username=" NORMAL-CASE@example.COM ", password="Normal-Password-123!").pk,
            normal.pk,
        )
        self.assertEqual(
            authenticate(username="ＮｏｒｍａｌＣａｓｅＵｓｅｒ", password="Normal-Password-123!").pk,
            normal.pk,
        )
        self.assertEqual(
            authenticate(
                username="ＮＯＲＭＡＬ－ＣＡＳＥ＠ＥＸＡＭＰＬＥ．ＣＯＭ",
                password="Normal-Password-123!",
            ).pk,
            normal.pk,
        )
        self.assertIsNone(authenticate(username="missing-user", password="Normal-Password-123!"))
        self.assertEqual(
            authenticate(username="flow_owner", password="Owner-Password-123!").pk,
            self.owner.pk,
        )

    def test_staged_account_cannot_password_or_otp_login(self):
        self.assertIsNone(authenticate(username=self.staged.username, password="Staged-Password-123!"))
        self.assertIsNone(authenticate(username=self.staged.email, password="Staged-Password-123!"))
        self.assertIsNone(authenticate(username="Ｓｔａｇｅｄ＿Ｆｌｏｗ＿Ｕｓｅｒ", password="Staged-Password-123!"))
        self.assertIsNone(
            authenticate(
                username="ｓｔａｇｅｄ－ｆｌｏｗ＠ｅｘａｍｐｌｅ．ｃｏｍ",
                password="Staged-Password-123!",
            )
        )
        with self.assertRaises(StagedAccountAccessError):
            issue_email_otp(self.staged, purpose=EmailOTP.Purpose.LOGIN)
        with self.assertRaises(StagedAccountAccessError):
            issue_email_otp(
                email="ｓｔａｇｅｄ－ｆｌｏｗ＠ｅｘａｍｐｌｅ．ｃｏｍ",
                purpose=EmailOTP.Purpose.LOGIN,
            )
        self.assertFalse(EmailOTP.objects.filter(user=self.staged).exists())

        verification = verify_email_otp(
            email=self.staged.email,
            code="123456",
            user=self.staged,
            purpose=EmailOTP.Purpose.LOGIN,
        )
        self.assertFalse(verification.success)
        self.assertEqual(verification.reason, "access_denied")

    def test_password_reset_and_login_otp_endpoint_send_nothing(self):
        reset = self.client.post(reverse("accounts:password_reset"), {"email": self.staged.email})
        self.assertEqual(reset.status_code, 302)
        response = self.client.post(
            reverse("accounts:send_otp_api"),
            {"email": self.staged.email, "purpose": EmailOTP.Purpose.LOGIN},
        )
        self.assertEqual(response.status_code, 202)
        self.assertFalse(EmailOTP.objects.filter(user=self.staged).exists())
        self.assertEqual(mail.outbox, [])

    def test_old_modelbackend_session_is_logged_out_before_the_view(self):
        session = self.client.session
        session[SESSION_KEY] = str(self.staged.pk)
        session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
        session[HASH_SESSION_KEY] = self.staged.get_session_auth_hash()
        session.save()

        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertNotIn(SESSION_KEY, response.wsgi_request.session)

    def test_staged_account_cannot_use_signup_activation_restore_or_unblock(self):
        with self.assertRaises(StagedAccountAccessError):
            activate_user_account(self.staged)
        with self.assertRaisesRegex(AccountDeletionError, "staged_account_activation_forbidden"):
            restore_account(self.staged)
        with self.assertRaisesRegex(AccountDeletionError, "staged_account_activation_forbidden"):
            unblock_account(self.staged)

    def test_staged_target_is_absent_from_view_as_and_cached_session_is_revoked(self):
        Membership.objects.filter(user=self.staged, organization=self.organization).update(is_active=True)
        targets = build_target_queryset(
            self.owner,
            self.organization,
            mode=MODE_FULL,
            actor_level=999,
            memberships=[],
        )
        self.assertFalse(targets.filter(pk=self.staged.pk).exists())

        request = self.client.request().wsgi_request
        request.user = self.owner
        request.real_user = self.owner
        request.session = self.client.session
        with self.assertRaisesRegex(PermissionError, "view_as_staged_account_denied"):
            start_view_as(request, self.staged, self.organization, MODE_FULL)

        request.session[VIEW_AS_SESSION_KEY] = {
            "target_id": str(self.staged.pk),
            "org_id": str(self.organization.pk),
            "org_slug": self.organization.slug,
            "mode": MODE_FULL,
            "real_id": str(self.owner.pk),
            "prev_org_slug": "",
            "started_at": "2026-08-25T00:00:00+00:00",
            "checked_at": "2999-01-01T00:00:00+00:00",
        }
        request.session["active_organization"] = self.organization.slug
        target, mode = resolve_view_as_request(request)
        self.assertIsNone(target)
        self.assertIsNone(mode)
        self.assertNotIn(VIEW_AS_SESSION_KEY, request.session)


class IdentitySchemaSQLiteTests(TestCase):
    def test_normal_accounts_default_to_active_access(self):
        user = User.objects.create_user("normal_default_identity", email="normal-default@example.com")
        self.assertEqual(user.profile.access_state, UserProfile.AccessState.ACTIVE)

    def test_raw_canonical_username_email_and_tenant_student_duplicates_reject(self):
        owner = User.objects.create_user("canonical_owner", email="canonical-owner@example.com")
        org = Organization.objects.create(
            name="Canonical Org",
            slug="canonical-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        first = User.objects.create_user("CanonicalUser", email="Canonical.Email@example.com")
        first.profile.organization = org
        first.profile.institutional_identifier = "STU-Canonical"
        first.profile.save(update_fields=["organization", "institutional_identifier", "updated_at"])

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(username=" canonicaluser ", email="other-canonical@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(username="other_canonical", email=" canonical.email@EXAMPLE.com ")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(username="canonical.email@example.com", email="cross-column@example.com")

        second = User.objects.create_user("canonical_second", email="canonical-second@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProfile.objects.filter(pk=second.profile.pk).update(
                organization=org,
                institutional_identifier=" stu-canonical ",
            )

        # Blank email and null institutional identifiers retain their prior
        # multi-row semantics.
        User.objects.create_user("blank_email_one", email="")
        User.objects.create_user("blank_email_two", email="")

    def test_migration_precheck_is_deterministic_and_reverse_stops_for_staged(self):
        migration = import_module("apps.accounts.migrations.0013_identity_staging_and_canonical_guards")
        rows = (
            (3, " Same ", "z"),
            (1, "same", "x"),
            (2, "other", "y"),
        )
        self.assertEqual(migration._collision_ids(rows, value_position=1), ((1, 3),))

        user = User.objects.create_user("reverse_stop_user", is_active=False)
        user.profile.access_state = UserProfile.AccessState.STAGED
        user.profile.save(update_fields=["access_state", "updated_at"])
        with self.assertRaisesRegex(RuntimeError, "accounts_identity_reverse_stop:staged_accounts_exist"):
            migration.reverse_stop_if_staged(import_module("django.apps").apps, None)
        user.profile.access_state = UserProfile.AccessState.ACTIVE
        user.profile.institutional_identifier = "REVERSE-EVIDENCE"
        user.profile.save(update_fields=["access_state", "institutional_identifier", "updated_at"])
        with self.assertRaisesRegex(RuntimeError, "accounts_identity_reverse_stop:institutional_identifiers_exist"):
            migration.reverse_stop_if_staged(import_module("django.apps").apps, None)
        user.profile.institutional_identifier = None
        user.profile.save(update_fields=["institutional_identifier", "updated_at"])
        organization = Organization.objects.create(
            name="Reverse Evidence Org",
            slug="reverse-evidence-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=user,
            status="active",
            is_active=True,
        )
        AccountActivationEvidence.objects.create(
            organization=organization,
            user_ref=str(user.pk),
            role_ref="role-ref",
            actor_ref=str(user.pk),
            evidence_digest="e" * 64,
            reason_code=AccountActivationEvidence.Reason.MANUAL_REGISTRY_VERIFICATION,
            transaction_id=0,
        )
        with self.assertRaisesRegex(RuntimeError, "accounts_identity_reverse_stop:activation_evidence_exists"):
            migration.reverse_stop_if_staged(import_module("django.apps").apps, None)

    def test_expected_identity_indexes_are_installed(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, "auth_user")
            profile_constraints = connection.introspection.get_constraints(cursor, "accounts_userprofile")
            evidence_constraints = connection.introspection.get_constraints(
                cursor,
                "accounts_accountactivationevidence",
            )
        self.assertIn("accounts_auth_username_canon_uniq", constraints)
        self.assertIn("accounts_auth_email_canon_uniq", constraints)
        self.assertIn("accounts_student_ident_canon_uniq", profile_constraints)
        self.assertIn("accounts_activation_evidence_user_uniq", evidence_constraints)
        self.assertIn("accounts_act_org_created_idx", evidence_constraints)
