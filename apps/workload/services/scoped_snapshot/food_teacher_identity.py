"""Read-only, bounded source-name probe across all own-tenant profiles.

A match is a review candidate, never proof of a teacher role or permission.
Unmatched profiles and plaintext identity fields never enter the payload.
"""

import hashlib
import html
import json
import unicodedata
from collections import defaultdict

from django.apps import apps
from django.db.models import Q

from core.permissions import has_permission

from .food_teacher_identity_spec import ORG, SOURCE_PAIRS, SOURCE_SHA256


def identity_hash(*parts):
    """Preserve letters, punctuation and name boundaries; no fuzzy matching."""
    normalized = []
    for part in parts:
        value = unicodedata.normalize("NFKC", html.unescape(part or ""))
        value = value.replace("İ", "i").replace("I", "ı").casefold().replace("i\u0307", "i")
        normalized.append(" ".join(value.split()))
    encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def collect_food_teacher_identity():
    profiles = (
        apps.get_model("accounts", "UserProfile")
        .objects.filter(organization_id=ORG)
        .order_by("user_id")
        .values("user_id", "user__first_name", "user__last_name", "user__is_active", "patronymic", "access_state")
    )
    matched = []
    counts = defaultdict(int)
    exact_counts = defaultdict(int)
    scanned = 0
    for profile in profiles.iterator(chunk_size=2000):
        scanned += 1
        first, last = profile["user__first_name"], profile["user__last_name"]
        pair = identity_hash(first, last)
        if pair not in SOURCE_PAIRS:
            continue
        father = profile["patronymic"]
        father_missing = identity_hash(father) == identity_hash("")
        triple = None if father_missing else identity_hash(first, last, father)
        source_triple = SOURCE_PAIRS[pair]
        exact = None if source_triple is None else triple == source_triple
        counts[pair] += 1
        exact_counts[pair] += exact is True
        matched.append(
            {
                "user_id": profile["user_id"],
                "source_pair_hash": pair,
                "full_triple_identity_hash": triple,
                "source_father_missing": source_triple is None,
                "profile_father_missing": father_missing,
                "source_full_triple_matches": exact,
                "user_is_active": profile["user__is_active"],
                "access_state": profile["access_state"],
                "memberships": [],
            }
        )
    by_user = {row["user_id"]: row for row in matched}
    memberships = (
        apps.get_model("organizations", "Membership")
        .objects.filter(organization_id=ORG, role__organization_id=ORG, user_id__in=by_user)
        .filter(Q(scope_unit__isnull=True) | Q(scope_unit__organization_id=ORG))
        .order_by("user_id", "role__name", "scope_unit_id", "id")
        .values("user_id", "role__name", "role__is_active", "role__permissions", "is_active", "scope_unit_id")
    )
    for membership in memberships:
        by_user[membership["user_id"]]["memberships"].append(
            {
                "role_code": membership["role__name"],
                "role_is_active": membership["role__is_active"],
                "membership_is_active": membership["is_active"],
                "scope_unit_id": membership["scope_unit_id"],
                "role_has_grade_input": has_permission(membership["role__permissions"] or [], "grade.input"),
            }
        )
    summaries = [
        {
            "source_pair_hash": pair,
            "source_father_missing": triple is None,
            "candidate_count": counts[pair],
            "full_triple_match_count": exact_counts[pair],
            "status": (
                "ambiguous_pair"
                if counts[pair] > 1
                else "unique_pair_candidate_unverified" if counts[pair] else "no_pair_match_in_scanned_tenant_profiles"
            ),
        }
        for pair, triple in sorted(SOURCE_PAIRS.items())
    ]
    return {
        "food_source_identity_candidates": matched,
        "food_source_identity_pairs": summaries,
        "food_source_identity_coverage": {
            "source_sha256": SOURCE_SHA256,
            "profile_organization_id": ORG,
            "scanned_tenant_profiles": scanned,
            "source_pair_count": len(SOURCE_PAIRS),
            "matched_profile_count": len(matched),
            "matched_pair_count": sum(count > 0 for count in counts.values()),
            "automatic_authorization": False,
        },
    }
