"""
Permission definitions and checking functions for the organizations app.
"""

from typing import List, Set

PERMISSION_PREFIX_ALIASES = {
    "grade": "grading",
    "grading": "grade",
    "course": "courses",
    "courses": "course",
    "exam": "exams",
    "exams": "exam",
    "member": "members",
    "members": "member",
    "role": "roles",
    "roles": "role",
}


def _permission_variants(permission: str) -> Set[str]:
    variants = {permission}
    if "." not in permission:
        return variants

    prefix, suffix = permission.split(".", 1)
    alias_prefix = PERMISSION_PREFIX_ALIASES.get(prefix)
    if alias_prefix:
        variants.add(f"{alias_prefix}.{suffix}")
    return variants


def _wildcard_variants(prefix: str) -> Set[str]:
    variants = {f"{prefix}.*"}
    alias_prefix = PERMISSION_PREFIX_ALIASES.get(prefix)
    if alias_prefix:
        variants.add(f"{alias_prefix}.*")
    return variants


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


def has_permission(user_permissions: List[str], required_permission: str) -> bool:
    """
    Check if a user has a specific permission.
    Supports wildcard permissions (e.g., '*' for all, 'course.*' for all course permissions).
    Also tolerates the legacy `grading.*` prefix when checking `grade.*` permissions.

    Args:
        user_permissions: List of permission strings the user has
        required_permission: The permission string to check for

    Returns:
        True if user has the permission, False otherwise
    """
    if not user_permissions:
        return False

    if "*" in user_permissions:
        return True

    if _permission_variants(required_permission).intersection(user_permissions):
        return True

    if "." in required_permission:
        prefix = required_permission.split(".", 1)[0]
        if _wildcard_variants(prefix).intersection(user_permissions):
            return True

    return False


def get_permissions_for_category(category: str) -> List[str]:
    """
    Get all permissions for a specific category.

    Args:
        category: The category name (e.g., 'courses', 'grading')

    Returns:
        List of permission strings for that category
    """
    return PERMISSION_CATEGORIES.get(category, [])


def validate_permissions(permissions: List[str]) -> bool:
    """
    Validate that all permissions in a list are valid.

    Args:
        permissions: List of permission strings to validate

    Returns:
        True if all permissions are valid, False otherwise
    """
    if not permissions:
        return True

    if "*" in permissions:
        return True

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
