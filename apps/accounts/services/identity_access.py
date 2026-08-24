"""Fail-closed staging and activation for imported account identities."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.audit.public import log_action
from core.constants import AuditAction
from core.permissions import has_permission, is_superadmin_user

from ..identity import canonical_identity, canonical_identity_queryset, user_access_is_staged
from ..models import AccountActivationEvidence, UserProfile

User = get_user_model()

_EVIDENCE_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_EMAIL_AUTHORITY_REASON_CODES = frozenset(AccountActivationEvidence.Reason.values)


class IdentityAccessError(Exception):
    """Sanitized identity lifecycle failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class IdentityCollisionError(IdentityAccessError):
    pass


@dataclass(frozen=True)
class StagedAccountResult:
    user: object
    created: bool


@dataclass(frozen=True)
class AccountActivationResult:
    user: object
    activated: bool


def _real_actor(actor, request):
    request_actor = None
    if request is not None:
        request_actor = getattr(request, "real_user", None) or getattr(request, "user", None)
    if actor is None:
        actor = request_actor
    if request_actor is not None and getattr(actor, "pk", None) != getattr(request_actor, "pk", None):
        raise PermissionDenied("identity_actor_mismatch")
    if actor is None or not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False):
        raise PermissionDenied("identity_actor_required")
    if user_access_is_staged(actor):
        raise PermissionDenied("identity_staged_actor_denied")
    return actor


def _assert_tenant_permission(actor, organization, permission):
    if (
        organization is None
        or not getattr(organization, "pk", None)
        or not getattr(organization, "is_active", False)
        or getattr(organization, "status", None) != "active"
    ):
        raise PermissionDenied("identity_active_tenant_required")
    if is_superadmin_user(actor):
        return

    from apps.organizations.models import Membership

    memberships = Membership.objects.filter(
        user=actor,
        organization=organization,
        is_active=True,
        role__is_active=True,
    ).select_related("role")
    permissions = {item for membership in memberships for item in (membership.role.permissions or [])}
    if not has_permission(list(permissions), permission):
        raise PermissionDenied("identity_permission_denied")


def _validate_new_identity(*, username, email, organization, student_identifier):
    username = str(username or "").strip()
    email = str(email or "").strip()
    student_identifier = str(student_identifier or "").strip()
    username_key = canonical_identity(username)
    email_key = canonical_identity(email)
    student_key = canonical_identity(student_identifier)

    if not username_key:
        raise IdentityAccessError("identity_username_required")
    try:
        User._meta.get_field("username").validators[0](username)
    except (IndexError, ValidationError):
        raise IdentityAccessError("identity_username_invalid") from None
    if email:
        try:
            validate_email(email)
        except ValidationError:
            raise IdentityAccessError("identity_email_invalid") from None

    users = User._default_manager.all()
    if canonical_identity_queryset(users, "username", username_key, alias="_stage_username_key").exists():
        raise IdentityCollisionError("identity_username_collision")
    if (
        email_key
        and canonical_identity_queryset(
            users,
            "email",
            email_key,
            alias="_stage_email_key",
        ).exists()
    ):
        raise IdentityCollisionError("identity_email_collision")
    username_hits_email = canonical_identity_queryset(
        users,
        "email",
        username_key,
        alias="_stage_username_email_key",
    ).exists()
    email_hits_username = (
        bool(email_key)
        and canonical_identity_queryset(
            users,
            "username",
            email_key,
            alias="_stage_email_username_key",
        ).exists()
    )
    if username_hits_email or email_hits_username:
        raise IdentityCollisionError("identity_cross_field_collision")

    if student_key:
        profiles = UserProfile.objects.filter(organization=organization)
        if canonical_identity_queryset(
            profiles,
            "institutional_identifier",
            student_key,
            alias="_stage_student_key",
        ).exists():
            raise IdentityCollisionError("identity_student_identifier_collision")

    return username, email, student_identifier


def _preserved_existing_user(existing_user, organization):
    """Validate an explicit match without writing any account/business field."""

    if existing_user is None or not getattr(existing_user, "pk", None):
        raise IdentityAccessError("identity_existing_user_invalid")
    belongs_to_tenant = existing_user.memberships.filter(organization=organization).exists()
    profile_org_id = UserProfile.objects.filter(user=existing_user).values_list("organization_id", flat=True).first()
    if not belongs_to_tenant and str(profile_org_id or "") != str(organization.pk):
        raise PermissionDenied("identity_existing_user_cross_tenant")
    return StagedAccountResult(user=existing_user, created=False)


@transaction.atomic
def stage_imported_account(
    *,
    organization,
    role,
    actor,
    username="",
    email="",
    student_identifier="",
    existing_user=None,
    request=None,
):
    """Preserve an explicit existing match or create one locked staged account.

    This service never sends mail, activates an account, imports a password, or
    changes an existing user's email/profile/membership fields.
    """

    actor = _real_actor(actor, request)
    _assert_tenant_permission(actor, organization, "member.invite")
    if existing_user is not None:
        return _preserved_existing_user(existing_user, organization)
    if role is None or str(getattr(role, "organization_id", "")) != str(organization.pk):
        raise PermissionDenied("identity_role_cross_tenant")
    if not getattr(role, "is_active", False):
        raise PermissionDenied("identity_active_role_required")

    username, email, student_identifier = _validate_new_identity(
        username=username,
        email=email,
        organization=organization,
        student_identifier=student_identifier,
    )

    try:
        with transaction.atomic():
            user = User(username=username, email=email, is_active=False)
            user.set_unusable_password()
            user.full_clean(exclude={"password"})
            user.save(force_insert=True)

            profile = UserProfile.objects.select_for_update().get(user=user)
            profile.organization = organization
            profile.access_state = UserProfile.AccessState.STAGED
            profile.institutional_identifier = student_identifier or None
            profile.save(
                update_fields=[
                    "organization",
                    "access_state",
                    "institutional_identifier",
                    "updated_at",
                ]
            )
            # Profile-creation signal cached the initial ACTIVE instance on
            # this User object; replace that stale reverse OneToOne cache.
            user.profile = profile

            from apps.organizations.models import Membership

            Membership.objects.create(
                user=user,
                organization=organization,
                role=role,
                assigned_by=actor,
                is_primary=True,
                is_active=False,
            )
            log_action(
                action=AuditAction.CREATE,
                user=actor,
                organization=organization,
                obj=user,
                reason="legacy_account_staged",
                changes={"access_state": "staged", "membership_active": False},
                request=request,
            )
    except IntegrityError:
        raise IdentityCollisionError("identity_canonical_collision") from None

    return StagedAccountResult(user=user, created=True)


def _activate_with_postgres_function(
    *, evidence_id, locked_user, organization, expected_role, actor, evidence_digest, reason_code
):
    """Call the only PostgreSQL transition surface for a staged identity."""

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.current_user_id', true)")
        current_actor = cursor.fetchone()[0] or ""
        if current_actor and current_actor != str(actor.pk):
            raise PermissionDenied("identity_actor_database_context_mismatch")
        cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(actor.pk)])
        cursor.execute(
            """
            SELECT public.accounts_activate_staged_identity(
                %s, %s, %s, %s, %s, %s, %s
            )
            """,
            [
                str(evidence_id),
                locked_user.pk,
                str(organization.pk),
                str(expected_role.pk),
                actor.pk,
                evidence_digest,
                reason_code,
            ],
        )


@transaction.atomic
def activate_staged_account(
    *,
    user,
    organization,
    expected_role,
    actor,
    email_authoritative,
    email_authority_evidence_digest,
    email_authority_reason_code,
    request=None,
):
    """Audit and atomically unlock one staged account in the same tenant."""

    actor = _real_actor(actor, request)
    _assert_tenant_permission(actor, organization, "member.edit")
    if email_authoritative is not True:
        raise IdentityAccessError("identity_authoritative_email_required")
    evidence_digest = str(email_authority_evidence_digest or "").strip().lower()
    reason_code = str(email_authority_reason_code or "").strip()
    if not _EVIDENCE_DIGEST_RE.fullmatch(evidence_digest):
        raise IdentityAccessError("identity_email_authority_evidence_required")
    if reason_code not in _EMAIL_AUTHORITY_REASON_CODES:
        raise IdentityAccessError("identity_email_authority_reason_invalid")
    if (
        expected_role is None
        or str(getattr(expected_role, "organization_id", "")) != str(organization.pk)
        or not getattr(expected_role, "is_active", False)
    ):
        raise IdentityAccessError("identity_expected_role_invalid")

    locked_user = User._default_manager.select_for_update().filter(pk=getattr(user, "pk", None)).first()
    if locked_user is None:
        raise IdentityAccessError("identity_target_missing")
    profile = (
        UserProfile.objects.select_for_update()
        .filter(
            user=locked_user,
            organization=organization,
        )
        .first()
    )
    if profile is None:
        raise PermissionDenied("identity_target_cross_tenant")

    from apps.organizations.models import Membership

    memberships = list(
        Membership.objects.select_for_update()
        .filter(user=locked_user, organization=organization)
        .select_related("role")
        .order_by("pk")
    )
    if not memberships:
        raise IdentityAccessError("identity_membership_missing")
    if len(memberships) != 1 or memberships[0].role_id != expected_role.pk:
        raise IdentityAccessError("identity_membership_set_mismatch")
    membership = memberships[0]

    if profile.access_state == UserProfile.AccessState.ACTIVE:
        if not locked_user.is_active or not membership.is_active:
            raise IdentityAccessError("identity_active_state_inconsistent")
        prior_evidence = AccountActivationEvidence.objects.filter(
            organization=organization,
            user_ref=str(locked_user.pk),
        ).first()
        if (
            prior_evidence is None
            or prior_evidence.consumed_at is None
            or prior_evidence.role_ref != str(expected_role.pk)
        ):
            raise IdentityAccessError("identity_active_without_activation_evidence")
        if prior_evidence.evidence_digest != evidence_digest or prior_evidence.reason_code != reason_code:
            raise IdentityAccessError("identity_activation_evidence_mismatch")
        locked_user.profile = profile
        return AccountActivationResult(user=locked_user, activated=False)
    if profile.access_state != UserProfile.AccessState.STAGED or locked_user.is_active:
        raise IdentityAccessError("identity_staged_state_inconsistent")
    if not canonical_identity(locked_user.email):
        raise IdentityAccessError("identity_authoritative_email_missing")

    if canonical_identity_queryset(
        User._default_manager.exclude(pk=locked_user.pk),
        "email",
        locked_user.email,
        alias="_activation_email_key",
    ).exists():
        raise IdentityCollisionError("identity_email_collision")

    evidence_id = uuid.uuid4()
    if connection.vendor == "postgresql":
        _activate_with_postgres_function(
            evidence_id=evidence_id,
            locked_user=locked_user,
            organization=organization,
            expected_role=expected_role,
            actor=actor,
            evidence_digest=evidence_digest,
            reason_code=reason_code,
        )
        locked_user.refresh_from_db(fields=["is_active"])
        profile.refresh_from_db(fields=["access_state", "updated_at"])
        membership.refresh_from_db(fields=["is_active", "is_primary", "assigned_by", "updated_at"])
    else:
        profile.access_state = UserProfile.AccessState.ACTIVE
        profile.save(update_fields=["access_state", "updated_at"])
        membership.is_active = True
        membership.is_primary = True
        membership.assigned_by = actor
        membership.save(update_fields=["is_active", "is_primary", "assigned_by", "updated_at"])
        locked_user.is_active = True
        locked_user.save(update_fields=["is_active"])
        AccountActivationEvidence.objects.create(
            id=evidence_id,
            organization=organization,
            user_ref=str(locked_user.pk),
            role_ref=str(expected_role.pk),
            actor_ref=str(actor.pk),
            evidence_digest=evidence_digest,
            reason_code=reason_code,
            transaction_id=0,
            consumed_at=timezone.now(),
        )
    locked_user.profile = profile

    # PostgreSQL writes this exact audit row inside the SECURITY DEFINER
    # transition so direct function callers cannot omit it.  Other supported
    # local/test backends keep the same atomic contract through the ORM helper.
    if connection.vendor != "postgresql":
        log_action(
            action=AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=locked_user,
            old_values={"access_state": "staged", "is_active": False},
            new_values={"access_state": "active", "is_active": True},
            reason="legacy_account_activated",
            changes={
                "email_authority_evidence_digest": evidence_digest,
                "email_authority_reason_code": reason_code,
                "activation_evidence_id": str(evidence_id),
                "role_id": str(expected_role.pk),
            },
            request=request,
        )
    return AccountActivationResult(user=locked_user, activated=True)


__all__ = [
    "AccountActivationResult",
    "IdentityAccessError",
    "IdentityCollisionError",
    "StagedAccountResult",
    "activate_staged_account",
    "stage_imported_account",
]
