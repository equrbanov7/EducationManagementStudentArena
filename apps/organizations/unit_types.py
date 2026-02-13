"""
Unit type configuration and validation for different organization types.
"""

from core.constants import OrganizationType, OrgUnitType

# Valid unit types for each organization type
UNIT_TYPES_BY_ORG = {
    OrganizationType.UNIVERSITY: [
        (OrgUnitType.RECTORATE, "Rectorate"),
        (OrgUnitType.VICE_RECTORATE, "Vice Rectorate"),
        (OrgUnitType.FACULTY, "Faculty"),
        (OrgUnitType.DEANERY, "Deanery"),
        (OrgUnitType.CHAIR, "Chair"),
        (OrgUnitType.DEPARTMENT, "Department"),
        (OrgUnitType.LAB, "Laboratory"),
        (OrgUnitType.INSTITUTE, "Institute"),
        (OrgUnitType.CENTER, "Center"),
    ],
    OrganizationType.SCHOOL: [
        (OrgUnitType.DIRECTORATE, "Directorate"),
        (OrgUnitType.SECTION, "Section"),
        (OrgUnitType.PARALLEL, "Parallel"),
        (OrgUnitType.CLASS, "Class"),
        (OrgUnitType.GRADE_LEVEL, "Grade Level"),
    ],
    OrganizationType.COURSE_CENTER: [
        (OrgUnitType.BRANCH, "Branch"),
        (OrgUnitType.DIVISION, "Division"),
        (OrgUnitType.GROUP, "Group"),
        (OrgUnitType.CLASSROOM, "Classroom"),
    ],
    OrganizationType.INDIVIDUAL: [
        (OrgUnitType.UNIT, "Unit"),
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
    return unit_type.replace("_", " ").title()
