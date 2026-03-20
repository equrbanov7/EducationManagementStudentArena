"""
Unit type configuration and validation for different organization types.
"""

from django.utils.translation import pgettext, pgettext_lazy

from core.constants import OrganizationType, OrgUnitType

# Valid unit types for each organization type
UNIT_TYPES_BY_ORG = {
    OrganizationType.UNIVERSITY: [
        (OrgUnitType.RECTORATE, pgettext_lazy("organizations.unit_type", "rectorate")),
        (OrgUnitType.VICE_RECTORATE, pgettext_lazy("organizations.unit_type", "vice_rectorate")),
        (OrgUnitType.FACULTY, pgettext_lazy("organizations.unit_type", "faculty")),
        (OrgUnitType.DEANERY, pgettext_lazy("organizations.unit_type", "deanery")),
        (OrgUnitType.CHAIR, pgettext_lazy("organizations.unit_type", "chair")),
        (OrgUnitType.DEPARTMENT, pgettext_lazy("organizations.unit_type", "department")),
        (OrgUnitType.LAB, pgettext_lazy("organizations.unit_type", "laboratory")),
        (OrgUnitType.INSTITUTE, pgettext_lazy("organizations.unit_type", "institute")),
        (OrgUnitType.CENTER, pgettext_lazy("organizations.unit_type", "center")),
    ],
    OrganizationType.SCHOOL: [
        (OrgUnitType.DIRECTORATE, pgettext_lazy("organizations.unit_type", "directorate")),
        (OrgUnitType.SECTION, pgettext_lazy("organizations.unit_type", "section")),
        (OrgUnitType.PARALLEL, pgettext_lazy("organizations.unit_type", "parallel")),
        (OrgUnitType.CLASS, pgettext_lazy("organizations.unit_type", "class")),
        (OrgUnitType.GRADE_LEVEL, pgettext_lazy("organizations.unit_type", "grade_level")),
    ],
    OrganizationType.COURSE_CENTER: [
        (OrgUnitType.BRANCH, pgettext_lazy("organizations.unit_type", "branch")),
        (OrgUnitType.DIVISION, pgettext_lazy("organizations.unit_type", "division")),
        (OrgUnitType.GROUP, pgettext_lazy("organizations.unit_type", "group")),
        (OrgUnitType.CLASSROOM, pgettext_lazy("organizations.unit_type", "classroom")),
    ],
    OrganizationType.INDIVIDUAL: [
        (OrgUnitType.UNIT, pgettext_lazy("organizations.unit_type", "unit")),
    ],
}


def get_valid_unit_types_for_org(org_type: str):
    """
    Get valid unit type choices for a specific organization type.

    Args:
        org_type: Organization type constant

    Returns:
        List of (value, label) tuples for unit type choices
    """
    return UNIT_TYPES_BY_ORG.get(org_type, [])


def validate_unit_type_for_org(org_type: str, unit_type: str) -> bool:
    """
    Validate that a unit type is valid for a given organization type.

    Args:
        org_type: Organization type constant
        unit_type: Unit type constant to validate

    Returns:
        True if valid, False otherwise
    """
    valid_types = [ut[0] for ut in get_valid_unit_types_for_org(org_type)]
    return unit_type in valid_types


def get_unit_type_display(unit_type: str) -> str:
    """
    Get display name for a unit type.

    Args:
        unit_type: Unit type constant

    Returns:
        Display name string
    """
    for _org_type, types in UNIT_TYPES_BY_ORG.items():
        for ut, display in types:
            if ut == unit_type:
                return display
    return pgettext("organizations.unit_type", "fallback").format(name=unit_type.replace("_", " ").title())
