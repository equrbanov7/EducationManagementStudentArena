"""
Permission definitions and checking functions for the organizations app.
"""

from typing import List, Set

# DEPRECATED (FAZA 10) — legacy permission-prefix aliases.
#
# Canonical names are: grade.*, course.*, exam.*, member.*, role.*, unit.*.
# default_roles.py now emits only the canonical names, and migration
# organizations.0006 rewrites every existing Role.permissions row to the
# canonical spelling.
#
# M3 (2026-07-02): permission-matching core.permissions-a köçürülüb;
# import səthi qorunur (AGENTS §1).
from core.permissions import (  # noqa: F401
    PERMISSION_PREFIX_ALIASES,
    _permission_variants,
    _wildcard_variants,
    has_permission,
)

# Permission definitions by category
PERMISSION_CATEGORIES = {
    "organization": [
        "org.view",
        "org.edit",
        "org.settings",
        "org.manage_members",
        "org.admin.assign",
        "org.owner.assign",
        "org.delete",
    ],
    "structure": [
        "unit.view",
        "unit.create",
        "unit.edit",
        "unit.delete",
    ],
    "members": [
        "member.view",
        "member.invite",
        "member.edit",
        "member.remove",
        "member.student_manage",
    ],
    "roles": [
        "role.view",
        "role.create",
        "role.edit",
        "role.assign",
        "role.delete",
    ],
    "courses": [
        "course.view",
        "course.create",
        "course.edit",
        "course.delete",
        "assignment.delete",
        "project.delete",
        "lab.delete",
    ],
    "grading": [
        "grade.view",
        "grade.input",
        "grade.publish",
        "grade.override",
        "grade.approve_chair",
        "grade.approve_final",
    ],
    # Jurnal düzəlişi (correction) — 2 saat/bitmiş-semestr limitlərini sənədli
    # (PDF + audit) keçmə hüququ. İKT Rəhbəri rolunun açar icazəsi.
    "journal": [
        "journal.view",
        "journal.correct",
    ],
    "exams": [
        "exam.view",
        "exam.create",
        "exam.edit",
        "exam.manage",
        "exam.host",
        "exam.delete",
    ],
    "appeal": [
        "appeal.create",
        "appeal.respond",
        "appeal.decide",
    ],
    "analytics": [
        "analytics.view_own",
        "analytics.view_unit",
        "analytics.view_all",
    ],
    "qa": [
        "qa.view",
        "qa.review",
        "qa.flag",
    ],
    "audit": [
        "audit.view",
        "audit.export",
    ],
}


def get_all_permissions() -> List[str]:
    """
    Get a flat list of all available permissions.

    Returns:
        List of all permission strings
    """
    all_perms = []
    for category_perms in PERMISSION_CATEGORIES.values():
        all_perms.extend(category_perms)
    return all_perms


def get_permissions_for_category(category: str) -> List[str]:
    """
    Get all permissions for a specific category.

    Args:
        category: The category name (e.g., 'courses', 'grading')

    Returns:
        List of permission strings for that category
    """
    return PERMISSION_CATEGORIES.get(category, [])


# Delegasiya prefiksi: `grant:<permission>` — rol bu icazəni başqa (aşağı) rola
# verə bilər, amma prefiks özü icazəni aktiv etmir. Yuxarı səlahiyyət sahibi
# bununla aşağıya "bu icazəni sən də paylaya bilərsən" hüququ ötürür.
GRANT_PREFIX = "grant:"


def is_grant_entry(permission: str) -> bool:
    return permission.startswith(GRANT_PREFIX)


def strip_grant_prefix(permission: str) -> str:
    return permission[len(GRANT_PREFIX) :].strip() if is_grant_entry(permission) else permission


def validate_permissions(permissions: List[str]) -> bool:
    """
    Validate that all permissions in a list are valid.
    `grant:<permission>` formalı delegasiya girişləri də qəbul olunur —
    suffix adi icazə kimi validasiya edilir.

    Args:
        permissions: List of permission strings to validate

    Returns:
        True if all permissions are valid, False otherwise
    """
    if not permissions:
        return True

    if "*" in permissions:
        return True

    # Delegasiya girişlərinin suffix-ini adi icazə kimi yoxla.
    permissions = [strip_grant_prefix(perm) for perm in permissions]

    all_valid_perms = set(get_all_permissions())

    for perm in permissions:
        if perm.endswith(".*"):
            prefix = perm[:-2]
            has_match = False
            for wildcard in _wildcard_variants(prefix):
                wildcard_prefix = wildcard[:-1]
                if any(valid_permission.startswith(wildcard_prefix) for valid_permission in all_valid_perms):
                    has_match = True
                    break
            if not has_match:
                return False
        elif not _permission_variants(perm).intersection(all_valid_perms):
            return False

    return True


def expand_wildcard_permissions(permissions: List[str]) -> Set[str]:
    """
    Expand wildcard permissions to their full permission set.

    Args:
        permissions: List of permission strings, may include wildcards

    Returns:
        Set of all expanded permission strings
    """
    if "*" in permissions:
        return set(get_all_permissions())

    expanded = set()
    all_perms = get_all_permissions()

    for perm in permissions:
        if perm.endswith(".*"):
            prefix = perm[:-2]
            for wildcard in _wildcard_variants(prefix):
                wildcard_prefix = wildcard[:-1]
                for valid_permission in all_perms:
                    if valid_permission.startswith(wildcard_prefix):
                        expanded.add(valid_permission)
        else:
            matching_permissions = _permission_variants(perm).intersection(all_perms)
            if matching_permissions:
                expanded.update(matching_permissions)
            else:
                expanded.add(perm)

    return expanded
