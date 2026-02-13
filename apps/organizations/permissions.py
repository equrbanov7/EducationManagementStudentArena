"""
Permission definitions and checking functions for the organizations app.
"""

from typing import List, Set

# Permission definitions by category
PERMISSION_CATEGORIES = {
    "organization": [
        "org.view",
        "org.edit",
        "org.settings",
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

    Args:
        user_permissions: List of permission strings the user has
        required_permission: The permission string to check for

    Returns:
        True if user has the permission, False otherwise
    """
    if not user_permissions:
        return False

    # Check for full wildcard
    if "*" in user_permissions:
        return True

    # Check for exact match
    if required_permission in user_permissions:
        return True

    # Check for category wildcard (e.g., 'course.*')
    if "." in required_permission:
        category = required_permission.split(".")[0]
        if f"{category}.*" in user_permissions:
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

    # Allow wildcard
    if "*" in permissions:
        return True

    all_valid_perms = set(get_all_permissions())

    # Also allow category wildcards
    for category in PERMISSION_CATEGORIES.keys():
        all_valid_perms.add(f"{category}.*")

    # Check each permission
    for perm in permissions:
        if perm not in all_valid_perms:
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

    for perm in permissions:
        if perm.endswith(".*"):
            # Category wildcard
            category = perm[:-2]
            category_perms = get_permissions_for_category(category)
            expanded.update(category_perms)
        else:
            # Regular permission
            expanded.add(perm)

    return expanded
