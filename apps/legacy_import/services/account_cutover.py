"""Read-only safety classification for projected legacy account identities.

This module is deliberately *not* an account provisioning service.  It accepts
only rows produced by the credential-safe legacy projection, performs
normalisation and read-only collision checks, and returns stable rule codes.
There is no commit mode and no email-delivery dependency.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol

from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
    LegacyProjectedRow,
)

_USERNAME_MAX_LENGTH = 150
_USERNAME_VALIDATOR = UnicodeUsernameValidator()
TARGET_IDENTITY_SNAPSHOT_CHUNK_SIZE = 1_000


class LegacyAccountCutoverError(ValueError):
    """Sanitized contract failure containing only a stable rule code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class EmailTrustDecision(Enum):
    """The only authoritative decision accepted from the injected policy."""

    AUTHORITATIVE = "authoritative"
    DENIED = "denied"


class AccountCutoverOutcome(Enum):
    """Classification outcomes; none of them performs account activation."""

    LOCKED_STAGING_ELIGIBLE = "locked_staging_eligible"
    CONTACT_VERIFICATION_REQUIRED = "contact_verification_required"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class AuthoritativeEmailPolicy(Protocol):
    """Pure policy boundary for authoritative legacy email evidence."""

    def __call__(self, identity: ProjectedAccountIdentity) -> EmailTrustDecision: ...


def deny_all_email_trust(_identity: ProjectedAccountIdentity) -> EmailTrustDecision:
    """Explicit default-deny policy for callers without approved evidence."""

    return EmailTrustDecision.DENIED


def _source_kind(projected_row: LegacyProjectedRow) -> str:
    try:
        field_names = tuple(projected_row.keys())
    except Exception:
        raise LegacyAccountCutoverError("legacy_account_projection_invalid") from None
    if field_names == STUDENT_IDENTITY_FIELDS.allowed_fields:
        return "student"
    if field_names == WORKER_IDENTITY_FIELDS.allowed_fields:
        return "worker"
    raise LegacyAccountCutoverError("legacy_account_projection_not_audited")


@dataclass(frozen=True, repr=False)
class ProjectedAccountIdentity:
    """Credential-safe row plus a proposed username, with a sanitized repr."""

    projected_row: LegacyProjectedRow
    proposed_username: object
    source_kind: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.projected_row, LegacyProjectedRow):
            raise LegacyAccountCutoverError("legacy_account_projection_required")
        object.__setattr__(self, "source_kind", _source_kind(self.projected_row))

    def __repr__(self) -> str:
        return f"ProjectedAccountIdentity(source_kind={self.source_kind!r})"

    def to_safe_log_dict(self) -> dict[str, str]:
        return {
            "source_kind": self.source_kind,
            "validation_result": "projected",
        }


@dataclass(frozen=True, repr=False)
class AccountCutoverClassification:
    """Sanitized, stable classification result in the same order as input."""

    cohort_index: int
    source_kind: str
    outcome: AccountCutoverOutcome
    rule_codes: tuple[str, ...]

    def __repr__(self) -> str:
        return (
            "AccountCutoverClassification("
            f"cohort_index={self.cohort_index}, source_kind={self.source_kind!r}, "
            f"outcome={self.outcome.value!r}, rule_codes={self.rule_codes!r})"
        )

    def to_safe_log_dict(self) -> dict[str, object]:
        return {
            "cohort_index": self.cohort_index,
            "outcome": self.outcome.value,
            "rule_codes": self.rule_codes,
            "source_kind": self.source_kind,
            "validation_result": "eligible" if not self.rule_codes else "blocked",
        }


@dataclass(frozen=True)
class _NormalizedIdentity:
    identity: ProjectedAccountIdentity
    username: str | None
    username_key: str | None
    email: str | None
    email_key: str | None
    initial_rules: tuple[str, ...]


@dataclass(frozen=True, repr=False)
class TargetIdentitySnapshot:
    """Opaque canonical target snapshot built by one chunked read query."""

    usernames: Mapping[str, int]
    emails: Mapping[str, int]
    row_count: int

    def __repr__(self) -> str:
        return f"TargetIdentitySnapshot(row_count={self.row_count})"

    def to_safe_log_dict(self) -> dict[str, int | str]:
        return {
            "canonicalization": "unicode-nfkc-trim-lower-v1",
            "email_duplicate_record_count": sum(count for count in self.emails.values() if count > 1),
            "query_count": 1,
            "row_count": self.row_count,
            "username_duplicate_record_count": sum(count for count in self.usernames.values() if count > 1),
        }


_SNAPSHOT_UNSUPPORTED = object()
_SNAPSHOT_FAILED = object()


def _normalized_username(value: object) -> tuple[str | None, str | None, tuple[str, ...]]:
    if type(value) is not str:
        return None, None, ("legacy_account_username_invalid",)
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        return None, None, ("legacy_account_username_blank",)
    try:
        if len(normalized) > _USERNAME_MAX_LENGTH:
            raise ValidationError("invalid")
        _USERNAME_VALIDATOR(normalized)
    except ValidationError:
        return None, None, ("legacy_account_username_invalid",)
    return normalized, normalized.lower(), ()


def _normalized_email(value: object) -> tuple[str | None, str | None, tuple[str, ...]]:
    if value is None or value == "":
        return None, None, ("legacy_account_email_blank",)
    if type(value) is not str:
        return None, None, ("legacy_account_email_invalid",)
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        return None, None, ("legacy_account_email_blank",)
    try:
        validate_email(normalized)
    except ValidationError:
        return None, None, ("legacy_account_email_invalid",)
    return normalized, normalized.lower(), ()


def _normalize_identity(identity: object) -> _NormalizedIdentity:
    if not isinstance(identity, ProjectedAccountIdentity):
        raise LegacyAccountCutoverError("legacy_account_identity_contract_required")
    try:
        raw_email = identity.projected_row["email"]
    except Exception:
        raise LegacyAccountCutoverError("legacy_account_projection_invalid") from None

    username, username_key, username_rules = _normalized_username(identity.proposed_username)
    email, email_key, email_rules = _normalized_email(raw_email)
    return _NormalizedIdentity(
        identity=identity,
        username=username,
        username_key=username_key,
        email=email,
        email_key=email_key,
        initial_rules=(*username_rules, *email_rules),
    )


def _probe_collision_count(
    probe: Callable[[], int],
) -> tuple[int | None, str | None]:
    try:
        count = probe()
    except Exception:
        return None, "legacy_account_identity_probe_unavailable"
    if type(count) is not int or count < 0:
        return None, "legacy_account_identity_probe_unavailable"
    return count, None


def _load_existing_identity_snapshot(manager):
    """Load canonical target identities using one bounded, chunked query."""

    order_by = getattr(manager, "order_by", None)
    if not callable(order_by):
        return _SNAPSHOT_UNSUPPORTED
    try:
        queryset = order_by("pk").values_list("username", "email")
        iterator = getattr(queryset, "iterator", None)
        rows = iterator(chunk_size=TARGET_IDENTITY_SNAPSHOT_CHUNK_SIZE) if callable(iterator) else iter(queryset)
        usernames: Counter[str] = Counter()
        emails: Counter[str] = Counter()
        row_count = 0
        for username, email in rows:
            row_count += 1
            username_key = unicodedata.normalize("NFKC", str(username or "")).strip().lower()
            email_key = unicodedata.normalize("NFKC", str(email or "")).strip().lower()
            if username_key:
                usernames[username_key] += 1
            if email_key:
                emails[email_key] += 1
    except Exception:
        return _SNAPSHOT_FAILED
    return TargetIdentitySnapshot(
        usernames=MappingProxyType(dict(usernames)),
        emails=MappingProxyType(dict(emails)),
        row_count=row_count,
    )


def load_target_identity_snapshot(*, user_model=None) -> TargetIdentitySnapshot:
    """Return a fail-closed target snapshot suitable for cohort classification."""

    model = user_model or get_user_model()
    manager = getattr(model, "_default_manager", None)
    if manager is None:
        raise LegacyAccountCutoverError("legacy_account_identity_probe_invalid")
    snapshot = _load_existing_identity_snapshot(manager)
    if not isinstance(snapshot, TargetIdentitySnapshot):
        raise LegacyAccountCutoverError("legacy_account_identity_probe_unavailable")
    return snapshot


_MANUAL_REVIEW_RULES = frozenset(
    {
        "legacy_account_email_collision",
        "legacy_account_email_duplicate_existing",
        "legacy_account_email_duplicate_source",
        "legacy_account_identity_probe_unavailable",
        "legacy_account_username_blank",
        "legacy_account_username_collision",
        "legacy_account_username_email_collision",
        "legacy_account_username_email_duplicate_source",
        "legacy_account_username_duplicate_source",
        "legacy_account_username_invalid",
    }
)


def _outcome_for(rules: Sequence[str]) -> AccountCutoverOutcome:
    if _MANUAL_REVIEW_RULES.intersection(rules):
        return AccountCutoverOutcome.MANUAL_REVIEW_REQUIRED
    if rules:
        return AccountCutoverOutcome.CONTACT_VERIFICATION_REQUIRED
    return AccountCutoverOutcome.LOCKED_STAGING_ELIGIBLE


def classify_projected_account_cutover(
    identities: Sequence[ProjectedAccountIdentity],
    *,
    authoritative_email_policy: AuthoritativeEmailPolicy,
    user_model=None,
    target_identity_snapshot: TargetIdentitySnapshot | None = None,
) -> tuple[AccountCutoverClassification, ...]:
    """Classify a complete projected cohort without writing or sending mail.

    The complete cohort is accepted as one unit so case-insensitive duplicates
    are detected before any future staging operation.  Email authority is
    accepted only when the mandatory injected policy returns the exact enum
    member ``EmailTrustDecision.AUTHORITATIVE``.  Exceptions and every other
    return value fail closed.
    """

    if isinstance(identities, (str, bytes)) or not isinstance(identities, Sequence):
        raise LegacyAccountCutoverError("legacy_account_identity_cohort_invalid")
    if not callable(authoritative_email_policy):
        raise LegacyAccountCutoverError("legacy_account_email_trust_policy_required")
    try:
        normalized = tuple(_normalize_identity(identity) for identity in identities)
    except LegacyAccountCutoverError:
        raise
    except Exception:
        raise LegacyAccountCutoverError("legacy_account_identity_cohort_invalid") from None

    username_counts = Counter(item.username_key for item in normalized if item.username_key is not None)
    email_counts = Counter(item.email_key for item in normalized if item.email_key is not None)
    username_positions = {}
    email_positions = {}
    for index, item in enumerate(normalized):
        if item.username_key is not None:
            username_positions.setdefault(item.username_key, set()).add(index)
        if item.email_key is not None:
            email_positions.setdefault(item.email_key, set()).add(index)
    cross_source_keys = {
        key
        for key in set(username_positions) & set(email_positions)
        if len(username_positions[key] | email_positions[key]) > 1
    }
    model = user_model or get_user_model()
    manager = getattr(model, "_default_manager", None)
    if manager is None:
        raise LegacyAccountCutoverError("legacy_account_identity_probe_invalid")
    if target_identity_snapshot is not None and not isinstance(target_identity_snapshot, TargetIdentitySnapshot):
        raise LegacyAccountCutoverError("legacy_account_identity_probe_invalid")
    existing_snapshot = target_identity_snapshot or _load_existing_identity_snapshot(manager)

    results: list[AccountCutoverClassification] = []
    for index, item in enumerate(normalized):
        rules = list(item.initial_rules)

        if item.username_key is not None:
            if username_counts[item.username_key] > 1:
                rules.append("legacy_account_username_duplicate_source")
            if item.username_key in cross_source_keys:
                rules.append("legacy_account_username_email_duplicate_source")
            if isinstance(existing_snapshot, TargetIdentitySnapshot):
                username_matches, probe_error = existing_snapshot.usernames.get(item.username_key, 0), None
            elif existing_snapshot is _SNAPSHOT_FAILED:
                username_matches, probe_error = None, "legacy_account_identity_probe_unavailable"
            else:
                username_matches, probe_error = _probe_collision_count(
                    lambda value=item.username: manager.filter(username__iexact=value).count()
                )
            if probe_error:
                rules.append(probe_error)
            elif username_matches:
                rules.append("legacy_account_username_collision")
            if isinstance(existing_snapshot, TargetIdentitySnapshot):
                cross_matches, probe_error = existing_snapshot.emails.get(item.username_key, 0), None
            elif existing_snapshot is _SNAPSHOT_FAILED:
                cross_matches, probe_error = None, "legacy_account_identity_probe_unavailable"
            else:
                cross_matches, probe_error = _probe_collision_count(
                    lambda value=item.username: manager.filter(email__iexact=value).count()
                )
            if probe_error:
                rules.append(probe_error)
            elif cross_matches:
                rules.append("legacy_account_username_email_collision")

        if item.email_key is not None:
            if email_counts[item.email_key] > 1:
                rules.append("legacy_account_email_duplicate_source")
            if item.email_key in cross_source_keys:
                rules.append("legacy_account_username_email_duplicate_source")
            if isinstance(existing_snapshot, TargetIdentitySnapshot):
                email_matches, probe_error = existing_snapshot.emails.get(item.email_key, 0), None
            elif existing_snapshot is _SNAPSHOT_FAILED:
                email_matches, probe_error = None, "legacy_account_identity_probe_unavailable"
            else:
                email_matches, probe_error = _probe_collision_count(
                    lambda value=item.email: manager.filter(email__iexact=value).count()
                )
            if probe_error:
                rules.append(probe_error)
            elif email_matches:
                rules.append("legacy_account_email_collision")
                if email_matches > 1:
                    rules.append("legacy_account_email_duplicate_existing")
            if isinstance(existing_snapshot, TargetIdentitySnapshot):
                cross_matches, probe_error = existing_snapshot.usernames.get(item.email_key, 0), None
            elif existing_snapshot is _SNAPSHOT_FAILED:
                cross_matches, probe_error = None, "legacy_account_identity_probe_unavailable"
            else:
                cross_matches, probe_error = _probe_collision_count(
                    lambda value=item.email: manager.filter(username__iexact=value).count()
                )
            if probe_error:
                rules.append(probe_error)
            elif cross_matches:
                rules.append("legacy_account_username_email_collision")

        has_email_shape_blocker = any(
            rule
            in {
                "legacy_account_email_blank",
                "legacy_account_email_collision",
                "legacy_account_email_duplicate_existing",
                "legacy_account_email_duplicate_source",
                "legacy_account_email_invalid",
                "legacy_account_username_email_collision",
                "legacy_account_username_email_duplicate_source",
            }
            for rule in rules
        )
        if not has_email_shape_blocker:
            try:
                trust_decision = authoritative_email_policy(item.identity)
            except Exception:
                rules.append("legacy_account_email_trust_policy_unavailable")
            else:
                if trust_decision is not EmailTrustDecision.AUTHORITATIVE:
                    rules.append("legacy_account_email_untrusted")

        stable_rules = tuple(dict.fromkeys(rules))
        results.append(
            AccountCutoverClassification(
                cohort_index=index,
                source_kind=item.identity.source_kind,
                outcome=_outcome_for(stable_rules),
                rule_codes=stable_rules,
            )
        )

    return tuple(results)


def stage_classified_account_cutover(
    *,
    identity: ProjectedAccountIdentity,
    classification: AccountCutoverClassification,
    organization,
    role,
    actor,
    student_identifier: object = "",
    request=None,
):
    """Bridge one approved classification into accounts' locked staging API.

    Mapping of the student identifier remains an explicit upstream decision;
    this adapter never guesses it from ``fincode`` or another legacy column.
    """

    normalized = _normalize_identity(identity)
    if not isinstance(classification, AccountCutoverClassification):
        raise LegacyAccountCutoverError("legacy_account_classification_required")
    if classification.source_kind != identity.source_kind:
        raise LegacyAccountCutoverError("legacy_account_classification_mismatch")
    if classification.outcome is not AccountCutoverOutcome.LOCKED_STAGING_ELIGIBLE or classification.rule_codes:
        raise LegacyAccountCutoverError("legacy_account_staging_not_approved")
    if normalized.username is None or normalized.email is None:
        raise LegacyAccountCutoverError("legacy_account_staging_identity_invalid")

    normalized_student_identifier = unicodedata.normalize("NFKC", str(student_identifier or "")).strip()
    if identity.source_kind == "student" and not normalized_student_identifier:
        raise LegacyAccountCutoverError("legacy_account_student_identifier_required")
    if len(normalized_student_identifier) > 120:
        raise LegacyAccountCutoverError("legacy_account_student_identifier_invalid")

    # Correct dependency direction: legacy_import consumes the accounts public
    # facade; accounts never imports legacy_import.
    from apps.accounts.public import stage_imported_account

    return stage_imported_account(
        organization=organization,
        role=role,
        actor=actor,
        username=normalized.username,
        email=normalized.email,
        student_identifier=normalized_student_identifier,
        request=request,
    )


__all__ = [
    "AccountCutoverClassification",
    "AccountCutoverOutcome",
    "AuthoritativeEmailPolicy",
    "EmailTrustDecision",
    "LegacyAccountCutoverError",
    "ProjectedAccountIdentity",
    "TARGET_IDENTITY_SNAPSHOT_CHUNK_SIZE",
    "TargetIdentitySnapshot",
    "classify_projected_account_cutover",
    "deny_all_email_trust",
    "load_target_identity_snapshot",
    "stage_classified_account_cutover",
]
