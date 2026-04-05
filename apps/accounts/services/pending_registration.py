"""
Pending registration cache services.
"""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import transaction

from apps.accounts.models import EmailOTP
from core.utils import get_auth_pending_signup_ttl_seconds

from .organization_requests import activate_verified_membership
from .registration import create_user_with_organization, purge_stale_pending_registration


class PendingRegistrationError(Exception):
    """Base pending-registration exception."""


class PendingRegistrationNotFound(PendingRegistrationError):
    """Raised when cached signup data cannot be found."""


def _pending_registration_cache_key(email: str) -> str:
    return f"accounts:pending-registration:{EmailOTP.normalize_email(email)}"


def build_pending_registration_payload(cleaned_data: dict) -> dict:
    join_organization = cleaned_data.get("join_organization")
    return {
        "username": str(cleaned_data.get("username", "")).strip(),
        "email": EmailOTP.normalize_email(cleaned_data.get("email", "")),
        "password_hash": make_password(cleaned_data.get("password", "")),
        "first_name": str(cleaned_data.get("first_name", "")).strip(),
        "last_name": str(cleaned_data.get("last_name", "")).strip(),
        "signup_mode": cleaned_data.get("signup_mode", "individual"),
        "organization_type": cleaned_data.get("organization_type"),
        "country_code": cleaned_data.get("country", ""),
        "join_organization_id": getattr(join_organization, "pk", None),
        "institution_not_listed_name": cleaned_data.get("institution_not_listed_name", ""),
        "organization_identifier": cleaned_data.get("organization_identifier", ""),
        "organization_license_identifier": cleaned_data.get("organization_license_identifier", ""),
        "initial_role": cleaned_data.get("initial_role"),
        "phone": cleaned_data.get("phone", ""),
        "specialization": cleaned_data.get("specialization", ""),
        "group_number": cleaned_data.get("group_number", ""),
        "department": cleaned_data.get("department", ""),
        "staff_position": cleaned_data.get("staff_position", ""),
    }


def store_pending_registration(cleaned_data: dict) -> dict:
    payload = build_pending_registration_payload(cleaned_data)
    cache.set(
        _pending_registration_cache_key(payload["email"]),
        payload,
        timeout=get_auth_pending_signup_ttl_seconds(),
    )
    return payload


def get_pending_registration(email: str) -> dict | None:
    return cache.get(_pending_registration_cache_key(email))


def clear_pending_registration(email: str) -> None:
    cache.delete(_pending_registration_cache_key(email))


@transaction.atomic
def finalize_pending_registration(email: str):
    payload = get_pending_registration(email)
    if not payload:
        raise PendingRegistrationNotFound("Pending registration not found or expired.")

    from apps.organizations.models import Country, Organization

    purge_stale_pending_registration(username=payload["username"], email=payload["email"])

    join_organization = None
    if payload.get("join_organization_id"):
        join_organization = Organization.objects.filter(pk=payload["join_organization_id"]).first()

    country_obj = Country.objects.filter(code=payload["country_code"]).first()
    country_name = country_obj.name if country_obj else payload["country_code"]

    user, organization, requested_organization, profile = create_user_with_organization(
        username=payload["username"],
        email=payload["email"],
        password=payload["password_hash"],
        password_is_hashed=True,
        first_name=payload["first_name"],
        last_name=payload["last_name"],
        signup_mode=payload["signup_mode"],
        organization_type=payload["organization_type"],
        country_code=payload["country_code"],
        country_name=country_name,
        join_organization=join_organization,
        institution_not_listed_name=payload["institution_not_listed_name"],
        organization_identifier=payload["organization_identifier"],
        organization_license_identifier=payload["organization_license_identifier"],
        initial_role=payload["initial_role"],
        phone=payload["phone"],
        specialization=payload["specialization"],
        group_number=payload["group_number"],
        department=payload["department"],
        staff_position=payload["staff_position"],
        create_join_request=False,
    )
    user.is_active = True
    user.save(update_fields=["is_active"])
    user = user.__class__.objects.get(pk=user.pk)
    profile = user.profile
    activate_verified_membership(user)
    clear_pending_registration(payload["email"])
    return user, organization, requested_organization, profile


__all__ = [
    "PendingRegistrationError",
    "PendingRegistrationNotFound",
    "build_pending_registration_payload",
    "clear_pending_registration",
    "finalize_pending_registration",
    "get_pending_registration",
    "store_pending_registration",
]
