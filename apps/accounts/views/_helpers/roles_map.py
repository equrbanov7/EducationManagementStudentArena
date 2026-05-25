"""
Role mapping helpers.

Thin wrappers around ``apps.accounts.policies`` plus mappings between
``ProfileRole`` values and ``MembershipRequestRoleType`` values.
"""

from django.utils.translation import pgettext

from apps.notifications.models import MembershipRequestRoleType

from ...models import ProfileRole
from ...policies import (
    map_org_role_to_profile_role,
    map_signup_role_to_profile_role,
    resolve_membership_role,
)
from ...queries import get_signup_lookup_payload


def _map_signup_role_to_profile_role(initial_role):
    return map_signup_role_to_profile_role(initial_role)


def _map_org_role_to_profile_role(role):
    return map_org_role_to_profile_role(role)


def _resolve_membership_role(organization, initial_role):
    return resolve_membership_role(organization, initial_role)


def _get_signup_lookup_payload():
    return get_signup_lookup_payload()


def _membership_request_role_type_for_profile_role(profile_role):
    if profile_role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
        return MembershipRequestRoleType.STUDENT
    if profile_role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}:
        return MembershipRequestRoleType.TEACHER
    return MembershipRequestRoleType.STAFF


def _profile_role_for_membership_request_type(role_type):
    if role_type == MembershipRequestRoleType.STUDENT:
        return ProfileRole.STUDENT
    if role_type == MembershipRequestRoleType.TEACHER:
        return ProfileRole.TEACHER
    return ProfileRole.MEMBER


def _membership_request_role_label(role_type):
    if role_type == MembershipRequestRoleType.STUDENT:
        return pgettext("membership_request.role", "Student")
    if role_type == MembershipRequestRoleType.TEACHER:
        return pgettext("membership_request.role", "Teacher")
    return pgettext("membership_request.role", "Staff")
