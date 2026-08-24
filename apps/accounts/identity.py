"""Canonical identity and staged-access security helpers."""

from __future__ import annotations

import unicodedata

from django.contrib.auth import get_user_model
from django.db import connections
from django.db.models import CharField, F, Func
from django.db.models.functions import Lower, Trim


class StagedAccountAccessError(PermissionError):
    """Stable, PII-free denial for a staged account."""

    code = "staged_account_access_denied"

    def __init__(self):
        super().__init__(self.code)


def canonical_identity(value: object) -> str:
    """NFKC + trim + lowercase key shared with PostgreSQL expression indexes."""

    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


class _PostgresCanonicalIdentity(Func):
    """Expression identical to the production canonical unique indexes."""

    arity = 1
    output_field = CharField()
    template = "LOWER(NORMALIZE(BTRIM(%(expressions)s), NFKC))"


def canonical_identity_queryset(queryset, field_name: str, value: object, *, alias: str = "_identity_key"):
    """Bounded/indexable lookup using the same canonical form as the DB.

    PostgreSQL gets exact NFKC + trim + lower semantics and can use the 0013
    expression indexes.  SQLite has no built-in Unicode normalization, so its
    documented local/test fallback is LOWER(TRIM()); callers still normalize
    the search value in Python first.
    """

    key = canonical_identity(value)
    if not key:
        return queryset.none()
    try:
        field = queryset.model._meta.get_field(field_name)
    except Exception as exc:
        raise ValueError("identity_canonical_field_invalid") from exc
    if not getattr(field, "concrete", False) or getattr(field, "is_relation", False):
        raise ValueError("identity_canonical_field_invalid")

    vendor = connections[queryset.db].vendor
    if vendor == "postgresql":
        expression = _PostgresCanonicalIdentity(F(field_name))
    else:
        expression = Lower(Trim(F(field_name)))
    return queryset.annotate(**{alias: expression}).filter(**{alias: key})


def user_access_is_staged(user) -> bool:
    """Read the current DB state; never trust a stale related-object cache."""

    user_id = getattr(user, "pk", None)
    if not user_id:
        return False

    from .models import UserProfile

    return UserProfile.objects.filter(
        user_id=user_id,
        access_state=UserProfile.AccessState.STAGED,
    ).exists()


def assert_account_access_allowed(user) -> None:
    if user_access_is_staged(user):
        raise StagedAccountAccessError()


def staged_user_for_email(email: object):
    """Return a staged account for a canonical email, without leaking it."""

    key = canonical_identity(email)
    if not key:
        return None
    User = get_user_model()
    from .models import UserProfile

    candidates = list(
        canonical_identity_queryset(
            User._default_manager.filter(profile__access_state=UserProfile.AccessState.STAGED),
            "email",
            key,
            alias="_staged_email_key",
        )
        .only("id", "email")
        .order_by("pk")[:2]
    )
    # A collision should be impossible after 0013, but ambiguity remains a
    # fail-closed outcome during a drift/partial-deploy window.
    return candidates[0] if len(candidates) == 1 else None


__all__ = [
    "StagedAccountAccessError",
    "assert_account_access_allowed",
    "canonical_identity",
    "canonical_identity_queryset",
    "staged_user_for_email",
    "user_access_is_staged",
]
