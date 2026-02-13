"""
Default role templates for different organization types.
"""

from core.constants import OrganizationType, RoleScopeType

DEFAULT_ROLES = {
    OrganizationType.UNIVERSITY: [
        {
            "name": "rector",
            "display_name": "Rector",
            "level": 100,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": ["*"],
            "description": "University rector with full administrative access",
        },
        {
            "name": "vice_rector",
            "display_name": "Vice Rector",
            "level": 90,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": [
                "org.view",
                "org.edit",
                "structure.*",
                "members.*",
                "courses.*",
                "grading.*",
                "exams.*",
                "analytics.view_all",
                "audit.view",
            ],
            "description": "Vice rector with broad administrative permissions",
        },
        {
            "name": "dean",
            "display_name": "Dean",
            "level": 80,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "unit.view",
                "unit.edit",
                "members.view",
                "members.invite",
                "members.edit",
                "courses.*",
                "grading.*",
                "exams.*",
                "analytics.view_unit",
            ],
            "description": "Faculty dean managing a specific faculty",
        },
        {
            "name": "chair_head",
            "display_name": "Department Chair",
            "level": 70,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "unit.view",
                "members.view",
                "courses.*",
                "grading.view",
                "grading.input",
                "exams.*",
                "analytics.view_unit",
            ],
            "description": "Department chair managing courses and faculty",
        },
        {
            "name": "teacher",
            "display_name": "Teacher",
            "level": 50,
            "scope_type": RoleScopeType.COURSE,
            "permissions": [
                "course.view",
                "course.edit",
                "grading.view",
                "grading.input",
                "exam.view",
                "exam.create",
                "exam.edit",
                "exam.host",
                "analytics.view_own",
            ],
            "description": "Teacher with course management and grading permissions",
        },
        {
            "name": "assistant",
            "display_name": "Teaching Assistant",
            "level": 40,
            "scope_type": RoleScopeType.COURSE,
            "permissions": [
                "course.view",
                "grading.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Teaching assistant with limited permissions",
        },
        {
            "name": "student",
            "display_name": "Student",
            "level": 10,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "course.view",
                "exam.view",
                "appeal.create",
                "analytics.view_own",
            ],
            "description": "Student with view and self-service permissions",
        },
    ],
    OrganizationType.SCHOOL: [
        {
            "name": "director",
            "display_name": "Director",
            "level": 100,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": ["*"],
            "description": "School director with full administrative access",
        },
        {
            "name": "deputy_director",
            "display_name": "Deputy Director",
            "level": 90,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": [
                "org.view",
                "org.edit",
                "structure.*",
                "members.*",
                "courses.*",
                "grading.*",
                "exams.*",
                "analytics.view_all",
            ],
            "description": "Deputy director with broad permissions",
        },
        {
            "name": "section_head",
            "display_name": "Section Head",
            "level": 70,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "unit.view",
                "members.view",
                "courses.*",
                "grading.*",
                "exams.*",
                "analytics.view_unit",
            ],
            "description": "Section head managing teachers and courses",
        },
        {
            "name": "teacher",
            "display_name": "Teacher",
            "level": 50,
            "scope_type": RoleScopeType.COURSE,
            "permissions": [
                "course.view",
                "course.edit",
                "grading.view",
                "grading.input",
                "exam.view",
                "exam.create",
                "exam.edit",
                "exam.host",
                "analytics.view_own",
            ],
            "description": "Teacher with course and grading permissions",
        },
        {
            "name": "student",
            "display_name": "Student",
            "level": 10,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "course.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Student with view permissions",
        },
        {
            "name": "parent",
            "display_name": "Parent",
            "level": 5,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "analytics.view_own",
            ],
            "description": "Parent with view access to student data",
        },
    ],
    OrganizationType.COURSE_CENTER: [
        {
            "name": "manager",
            "display_name": "Center Manager",
            "level": 100,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": ["*"],
            "description": "Course center manager with full access",
        },
        {
            "name": "branch_manager",
            "display_name": "Branch Manager",
            "level": 80,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "unit.view",
                "unit.edit",
                "members.*",
                "courses.*",
                "grading.*",
                "exams.*",
                "analytics.view_unit",
            ],
            "description": "Branch manager",
        },
        {
            "name": "instructor",
            "display_name": "Instructor",
            "level": 50,
            "scope_type": RoleScopeType.COURSE,
            "permissions": [
                "course.view",
                "course.edit",
                "grading.view",
                "grading.input",
                "exam.*",
                "analytics.view_own",
            ],
            "description": "Course instructor",
        },
        {
            "name": "student",
            "display_name": "Student",
            "level": 10,
            "scope_type": RoleScopeType.UNIT,
            "permissions": [
                "course.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Student enrolled in courses",
        },
    ],
    OrganizationType.INDIVIDUAL: [
        {
            "name": "owner",
            "display_name": "Owner",
            "level": 100,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": ["*"],
            "description": "Individual owner with full access",
        },
        {
            "name": "collaborator",
            "display_name": "Collaborator",
            "level": 50,
            "scope_type": RoleScopeType.COURSE,
            "permissions": [
                "course.*",
                "grading.*",
                "exam.*",
                "analytics.view_own",
            ],
            "description": "Collaborator with course permissions",
        },
        {
            "name": "student",
            "display_name": "Student",
            "level": 10,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": [
                "course.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Student with view permissions",
        },
    ],
}


def get_default_roles_for_org_type(org_type: str):
    """
    Get default role templates for a specific organization type.

    Args:
        org_type: Organization type constant

    Returns:
        List of role dictionaries for that organization type
    """
    return DEFAULT_ROLES.get(org_type, [])
