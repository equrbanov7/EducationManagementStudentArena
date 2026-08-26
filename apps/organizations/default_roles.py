"""
Default role templates for different organization types.

RİM hesab-idarəetmə icazələri üçün bax ``RIM_ACCOUNT_PERMISSIONS`` şərhinə.
"""

from core.constants import OrganizationType, RoleScopeType

from .default_roles_shared import RIM_ACCOUNT_PERMISSIONS  # noqa: F401
from .default_roles_university import UNIVERSITY_ROLES

DEFAULT_ROLES = {
    OrganizationType.UNIVERSITY: UNIVERSITY_ROLES,
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
                "unit.*",
                "member.*",
                "course.*",
                "grade.*",
                # org_admin-alias davranış qorunması (level 90 >= 80).
                "group.view",
                "group.manage",
                "exam.*",
                *RIM_ACCOUNT_PERMISSIONS,
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
                "member.view",
                "course.*",
                "grade.*",
                # org_admin-alias davranış qorunması (section_head → department_head).
                "group.view",
                "group.manage",
                "exam.*",
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
                "course.create",
                "course.edit",
                "grade.view",
                "grade.input",
                "exam.view",
                "exam.create",
                "exam.edit",
                "exam.host",
                "exam.delete",
                "assignment.delete",
                "project.delete",
                "lab.delete",
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
            "name": "member",
            "display_name": "Member",
            "level": 20,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": [
                "course.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Default onboarding role before student/teacher assignment",
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
                "member.*",
                "course.*",
                "grade.*",
                # org_admin-alias davranış qorunması (level 80 >= 80).
                "group.view",
                "group.manage",
                "exam.*",
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
                "grade.view",
                "grade.input",
                "exam.*",
                "assignment.delete",
                "project.delete",
                "lab.delete",
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
        {
            "name": "member",
            "display_name": "Member",
            "level": 20,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": [
                "course.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Default onboarding role",
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
                "grade.*",
                "exam.*",
                "assignment.delete",
                "project.delete",
                "lab.delete",
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
        {
            "name": "member",
            "display_name": "Member",
            "level": 20,
            "scope_type": RoleScopeType.ORGANIZATION,
            "permissions": [
                "course.view",
                "exam.view",
                "analytics.view_own",
            ],
            "description": "Default onboarding role",
        },
    ],
}


# ---------------------------------------------------------------------------
# Apellyasiya icazələrinin avtomatik əlavəsi
#
# Tək mənbədən qayda: apellyasiya qərarı mərkəzləşdirilib və yalnız
# "exam_center" roluna verilir; imtahanı görən rollar apellyasiya yarada bilər.
# "*" rolları onsuz da hər şeyi əhatə edir. Bu qayda mövcud rollar üçün
# organizations data migration-da da eyni cür tətbiq olunur.
# ---------------------------------------------------------------------------
_EXAM_MANAGEMENT_PERMS = ("exam.*", "exam.create", "exam.edit", "exam.host", "exam.manage")


def _augment_with_appeal_permissions(roles_by_type):
    for roles in roles_by_type.values():
        for role in roles:
            perms = role["permissions"]
            if "*" in perms:
                continue
            manages_exams = any(perm in perms for perm in _EXAM_MANAGEMENT_PERMS)
            views_exams = "exam.view" in perms or "exam.*" in perms
            to_add = []
            if role.get("name") in ("exam_center", "exam_center_head") and manages_exams:
                to_add = ["appeal.create", "appeal.respond", "appeal.decide"]
            elif views_exams:
                to_add = ["appeal.create"]
            for perm in to_add:
                if perm not in perms:
                    perms.append(perm)


_augment_with_appeal_permissions(DEFAULT_ROLES)


def get_default_roles_for_org_type(org_type: str):
    """
    Get default role templates for a specific organization type.

    Args:
        org_type: Organization type constant

    Returns:
        List of role dictionaries for that organization type
    """
    return DEFAULT_ROLES.get(org_type, [])
