"""Email-trust manifest köməkçiləri — identity rehearsal fazasının dəstək modulu.

PII-siz sübut manifesti: canonical email açarlarının sha256 digest-ləri.
Bölünmə səbəbi: modul-ölçü büdcəsi (SOFT_CAP=600); semantika dəyişməyib.
"""

from __future__ import annotations

import hashlib
import os
import unicodedata

from .account_cutover import (
    AuthoritativeEmailPolicy,
    EmailTrustDecision,
    ProjectedAccountIdentity,
    deny_all_email_trust,
)
from .rehearsal_contracts import (
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    RehearsalPolicy,
    encoded_part,
)

MAX_EMAIL_TRUST_MANIFEST_BYTES = 1 << 20


def _canonical_identity_key(value: object) -> str:
    """Canonicalise byte-identically to ``account_cutover._load_existing_identity_snapshot``."""

    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


def email_evidence_digest(value: object) -> str:
    """Digest one canonical email key for the PII-free evidence manifest."""

    digest = hashlib.sha256(b"legacy-rehearsal-email-evidence-v1\x00")
    digest.update(encoded_part(_canonical_identity_key(value)))
    return digest.hexdigest()


def load_email_trust_manifest(path: str) -> tuple[frozenset[str], str]:
    """Read a reviewer-attested digest manifest and return it with its own sha256."""

    if type(path) is not str or not path:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid")
    try:
        if os.path.islink(path):
            raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid")
        with open(path, "rb") as handle:
            payload = handle.read(MAX_EMAIL_TRUST_MANIFEST_BYTES + 1)
    except LegacyRehearsalConfigError:
        raise
    except Exception:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_unreadable") from None
    if len(payload) > MAX_EMAIL_TRUST_MANIFEST_BYTES:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_too_large")
    manifest_digest = hashlib.sha256(payload).hexdigest()
    digests: set[str] = set()
    try:
        lines = payload.decode("ascii", "strict").splitlines()
    except Exception:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid") from None
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if len(entry) != 64 or any(character not in "0123456789abcdef" for character in entry):
            raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid")
        digests.add(entry)
    if not digests:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid")
    return frozenset(digests), manifest_digest


def build_email_trust_policy(policy: RehearsalPolicy, manifest_digests: frozenset[str]) -> AuthoritativeEmailPolicy:
    """Return the only email-authority policy this run is allowed to inject."""

    if not isinstance(policy, RehearsalPolicy):
        raise LegacyRehearsalConfigError("legacy_rehearsal_policy_invalid")
    if policy.email_trust_policy is EmailTrustPolicy.DENY_ALL:
        if manifest_digests:
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_email_trust_invalid")
        return deny_all_email_trust
    if not isinstance(manifest_digests, frozenset) or not manifest_digests:
        raise LegacyRehearsalConfigError("legacy_rehearsal_policy_email_trust_invalid")

    def evidence_manifest_trust(identity: ProjectedAccountIdentity) -> EmailTrustDecision:
        if not isinstance(identity, ProjectedAccountIdentity):
            return EmailTrustDecision.DENIED
        try:
            key = _canonical_identity_key(identity.projected_row["email"])
        except Exception:
            return EmailTrustDecision.DENIED
        if key and email_evidence_digest(key) in manifest_digests:
            return EmailTrustDecision.AUTHORITATIVE
        return EmailTrustDecision.DENIED

    return evidence_manifest_trust


__all__ = [
    "MAX_EMAIL_TRUST_MANIFEST_BYTES",
    "build_email_trust_policy",
    "email_evidence_digest",
    "load_email_trust_manifest",
]
