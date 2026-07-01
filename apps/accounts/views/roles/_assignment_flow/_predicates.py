"""role_assignment flow — rol predikatları + operation token mixin-i."""

from uuid import UUID

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import Q

from ....models import ProfileRole
from ..._helpers import ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS, ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT


class _PredicatesMixin:
    """rol predikatları + operation token (RoleAssignmentFlow MRO ilə istifadə edir)."""

    def _parse_uuid(self, raw_value):
        try:
            return UUID(str(raw_value))
        except (TypeError, ValueError, AttributeError):
            return None

    def _is_owner_role(self, role):
        if role is None:
            return False
        role_name = (role.name or "").strip().lower()
        return role.level >= 100 or "owner" in role_name or role_name in {"rector", "director", "manager"}

    def _is_admin_role(self, role):
        if role is None:
            return False
        role_name = (role.name or "").strip().lower()
        return (
            self._is_owner_role(role)
            or role.level >= ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80)
            or "admin" in role_name
        )

    def _owner_membership_queryset(self):
        return self.Membership.objects.filter(organization=self.org, is_active=True, role__is_active=True).filter(
            Q(role__level__gte=100)
            | Q(role__name__icontains="owner")
            | Q(role__name__iexact="rector")
            | Q(role__name__iexact="director")
            | Q(role__name__iexact="manager")
        )

    def _validate_operation_token(self, *, action_name, target_role, target_membership=None, target_user=None):
        raw_token = (self.request.POST.get("operation_token") or "").strip()
        if not raw_token:
            return None
        try:
            operation_signer = TimestampSigner(salt=ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT)
            payload = operation_signer.unsign_object(raw_token, max_age=ROLE_ASSIGNMENT_OPERATION_TOKEN_MAX_AGE_SECONDS)
        except SignatureExpired:
            return self._deny_assignment(
                "operation_token_expired",
                "Əməliyyat tokeninin vaxtı bitib. Yenidən təsdiqləyin.",
                status=409,
                action_name=action_name,
                target_membership=target_membership,
                target_user=target_user,
                target_role=target_role,
            )
        except BadSignature:
            return self._deny_assignment(
                "operation_token_invalid",
                "Əməliyyat tokeni etibarsızdır.",
                action_name=action_name,
                target_membership=target_membership,
                target_user=target_user,
                target_role=target_role,
            )
        expected_target_id = str(target_membership.id if target_membership is not None else target_user.id)
        if (
            str(payload.get("actor_user_id")) != str(self.request.user.id)
            or str(payload.get("organization_id")) != str(self.org.id)
            or str(payload.get("target_action")) != str(action_name)
            or (str(payload.get("target_id")) != expected_target_id)
            or (str(payload.get("role_id")) != str(target_role.id))
        ):
            return self._deny_assignment(
                "operation_token_mismatch",
                "Təsdiq tokeni seçilmiş əməliyyatla uyğun gəlmir.",
                action_name=action_name,
                target_membership=target_membership,
                target_user=target_user,
                target_role=target_role,
            )
        return None

    def _build_operation_token(self, *, action_name, target_role, target_membership=None, target_user=None):
        if target_membership is None and target_user is None:
            return None
        target_id = str(target_membership.id if target_membership is not None else target_user.id)
        payload = {
            "actor_user_id": str(self.request.user.id),
            "organization_id": str(self.org.id),
            "target_action": action_name,
            "target_id": target_id,
            "role_id": str(target_role.id),
        }
        operation_signer = TimestampSigner(salt=ROLE_ASSIGNMENT_OPERATION_TOKEN_SALT)
        return operation_signer.sign_object(payload)
