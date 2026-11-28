"""Operational FAQ authorization. Cabinet visibility is checked separately by the catalog."""

from apps.hr_contracts.public import contract_management_allowed
from apps.organizations.public import (
    get_permission_scope,
    has_org_permission,
    membership_assignment_scope,
    unit_registry_flags,
)
from apps.registrar.public import (
    can_edit_plans,
    can_manage_catalog,
    can_merge_subjects,
    can_open_semester,
    catalog_console,
    lab_groups_section,
    retake_access,
    schedule_exports,
    schedule_manage,
)
from apps.subject_folder.public import teaching_folder_authority
from apps.surveys.public import can_manage_campaigns, can_view_results
from apps.syllabus import public as syllabus
from apps.workload import public as workload
from core.permissions import has_permission, is_superadmin_user, request_has_permission

from ...services.accounting.policy import resolve_actor as accounting_actor
from ...services.hr_analytics.policy import resolve_actor as hr_actor
from ...services.intake.policy import can_import, can_import_staff
from ...services.password_reset_admin import PasswordResetError, operator_for
from ...services.people.permissions import resolve_actor as people_actor
from .._helpers.rbac import _collect_actor_permissions
from ..group_lead import can_manage_group_leads

# Only distinct operation gates are added here. For read-only or strictly personal guides the
# original section and its own flags still apply. Flags constrain the *entire* playable file.
_GROUPS = {
    "faq_manage_workload_row": (
        "workload-hours",
        "workload-groups",
        "workload-new-row",
        "load-lab-hours",
        "load-lab-edit",
        "section-workload-center",
    ),
    "faq_edit_and_distribute_workload": (
        "workload-split",
        "workload-transfer",
        "load-consult",
        "load-exam",
        "load-thesis",
        "load-postgrad",
    ),
    "faq_distribute_workload": ("section-workload-distribution", "practice-assign"),
    "faq_object_workload": ("section-my-workload", "practice-personal"),
    "faq_view_own_workload": ("teacher-load-hours", "section-my-workload", "practice-personal"),
    "faq_review_workload": ("section-workload-visa",),
    "faq_approve_workload": ("section-workload-approval",),
    "faq_manage_schedule": ("schedule-admin", "section-schedule-manage"),
    "faq_export_schedule": ("schedule-excel-admin",),
    "faq_export_personal_schedule": ("schedule-excel-personal",),
    "faq_edit_syllabus": ("syllabus", "section-syllabus-editor"),
    "faq_revise_syllabus": ("section-syllabus-review",),
    "faq_manage_lab_groups": ("lab-group-create", "section-lab-groups", "laborant-department"),
    "faq_manage_folder": ("material", "section-subject-folders"),
    "faq_review_folder": ("review-homework", "section-subject-folder-review"),
    "can_create_support": ("section-applications",),
    "is_student": ("section-dashboard", "section-my-subjects", "section-my-transcript", "section-overall-academic"),
    "can_view_student_assignments": (
        "homework",
        "section-my-subject-folders",
        "section-assigned-courses",
        "section-pending-answers",
    ),
    "faq_manage_group_leads": ("section-groups-registry",),
    "faq_create_org_unit": ("section-org-structure",),
    "faq_manage_unit_tree": ("section-org-structure-tree",),
    "faq_assign_unit_head": ("section-org-faculties", "section-org-kafedras"),
    "faq_assign_unit_members": ("section-org-kafedras",),
    "faq_assign_roles": ("section-role-assignment", "section-manage-roles"),
    "faq_import_students": ("section-student-intake", "section-student-admission"),
    "faq_import_staff": ("section-teacher-intake",),
    "faq_manage_programs": ("section-programs-registry",),
    "faq_merge_subjects": ("section-subject-catalog",),
    "faq_create_rubric": ("section-registrar-catalog",),
    "faq_edit_curriculum": ("section-curriculum-editor",),
    "faq_open_semester": ("section-semester-opening",),
    "faq_reset_accounts": ("reset", "section-account-password-reset"),
    "faq_manage_hr_contracts": ("section-hr-contracts",),
    "faq_read_hr_analytics": ("section-hr-analytics",),
    "faq_read_accounting_report": ("section-accounting",),
    "faq_verify_retake_payment": ("section-retake-desk",),
    "faq_manage_retake_placement": ("section-subgroup-placement",),
    "faq_write_course": ("section-my-courses",),
    "faq_edit_role_permissions": ("section-permission-editor",),
    "faq_record_movement": ("section-student-registry",),
    "faq_manage_surveys": ("section-surveys-builder", "section-evaluation-campaigns"),
    "faq_view_survey_results": ("section-evaluation-results",),
    "can_approve_posts": ("section-pending-post-approvals",),
    "can_review_submissions": ("section-pending-review", "section-review-results"),
    "can_view_audit": ("section-org-overview",),
}
REQUIRED_FLAGS = {
    guide: tuple(flag for flag, guides in _GROUPS.items() if guide in guides)
    for guide in {guide for guides in _GROUPS.values() for guide in guides}
}


_WORKLOAD_SCOPES = {
    "faq_manage_workload_row": workload.PERM_MANAGE,
    "faq_distribute_workload": workload.PERM_DISTRIBUTE,
    "faq_review_workload": "workload.review",
    "faq_approve_workload": "workload.approve",
}


def _workload_flags(request, sections, wanted):
    if not any(s.startswith("workload-") or s == "my-workload" for s in sections):
        return {}
    actor = workload.resolve_actor(request.user, request.organization, request=request)

    def scoped(key):
        return actor.has(key) and actor.scope_for(key).has_structure_access

    values = {flag: scoped(key) for flag, key in _WORKLOAD_SCOPES.items() if flag in wanted}
    if "faq_object_workload" in wanted:
        values["faq_object_workload"] = actor.has("workload.object")
    if "faq_view_own_workload" in wanted:
        values["faq_view_own_workload"] = "my-workload" in sections and actor.has(workload.PERM_VIEW)
    if "faq_edit_and_distribute_workload" in wanted:
        shared = False
        if scoped(workload.PERM_MANAGE) and scoped(workload.PERM_DISTRIBUTE):
            if (
                actor.scope_for(workload.PERM_MANAGE).is_org_wide
                or actor.scope_for(workload.PERM_DISTRIBUTE).is_org_wide
            ):
                shared = True
            else:
                edits = workload.manageable_chairs(actor, permission=workload.PERM_MANAGE)
                assignments = workload.manageable_chairs(actor, permission=workload.PERM_DISTRIBUTE)
                shared = edits.filter(pk__in=assignments.order_by().values("pk")).exists()
        values["faq_edit_and_distribute_workload"] = shared
    return values


def _structure_flags(request, sections):
    if not sections.intersection({"org-structure-tree", "org-structure", "org-faculties", "org-kafedras"}):
        return {}
    org = request.organization
    if not get_permission_scope(request.user, org, "unit.view", request=request).has_structure_access:
        return {}
    flags = unit_registry_flags(request, org)
    return {
        "faq_create_org_unit": flags["can_create"],
        "faq_manage_unit_tree": flags["can_edit"] or has_org_permission(request, "unit.tree_manage"),
        "faq_assign_unit_head": flags["can_assign_head"],
        "faq_assign_unit_members": flags["can_assign_members"],
    }


def _can_reset(request):
    try:
        operator_for(request, for_write=True)
    except PasswordResetError:
        return False
    return True


def operational_capabilities(request, capabilities, required=None):
    """Compute operation flags against this request's tenant. Absent flags deny access.

    The offline exporter must run this from the same synthetic request as the live profile,
    including middleware-resolved organization permissions. Never infer these from role names.
    """
    org = getattr(request, "organization", None)
    user = request.user
    if org is None or not user.is_authenticated or not user.is_active:
        return {}
    sections = frozenset(capabilities.get("allowed_sections", ()))
    wanted = set(_GROUPS if required is None else required)
    result = {}
    if wanted.intersection(
        (*_WORKLOAD_SCOPES, "faq_object_workload", "faq_view_own_workload", "faq_edit_and_distribute_workload")
    ):
        result.update(_workload_flags(request, sections, wanted))
    if wanted.intersection(
        {"faq_create_org_unit", "faq_manage_unit_tree", "faq_assign_unit_head", "faq_assign_unit_members"}
    ):
        result.update(_structure_flags(request, sections))

    if "faq_export_schedule" in wanted and "schedule-manage" in sections:
        result["faq_export_schedule"] = schedule_manage.can_view(user, org)
    if "faq_manage_schedule" in wanted and "schedule-manage" in sections:
        result["faq_manage_schedule"] = schedule_manage.can_manage(user, org)
    if "faq_export_personal_schedule" in wanted and "my-schedule" in sections:
        result["faq_export_personal_schedule"] = not capabilities.get(
            "is_student"
        ) and schedule_exports.can_access_personal_export(user, org)
    if wanted.intersection({"faq_edit_syllabus", "faq_revise_syllabus"}) and sections.intersection(
        {"syllabus-editor", "syllabus-review"}
    ):
        actor = syllabus.resolve_actor(user, org, request=request)
        if "faq_edit_syllabus" in wanted:
            result["faq_edit_syllabus"] = actor.has(syllabus.PERM_EDIT)
        if (
            "faq_revise_syllabus" in wanted
            and "syllabus-review" in sections
            and actor.has(syllabus.PERM_REVISE)
            and syllabus.has_review_scope(actor=actor)
        ):
            result["faq_revise_syllabus"] = syllabus.has_decision_scope(
                actor, syllabus.PERM_REVISE
            ) or syllabus.has_escalated_decision_scope(actor, syllabus.PERM_REVISE)
    if "faq_manage_lab_groups" in wanted and "lab-groups" in sections:
        result["faq_manage_lab_groups"] = lab_groups_section.visible(user, org)
    if wanted.intersection({"faq_manage_folder", "faq_review_folder"}) and sections.intersection(
        {"subject-folders", "subject-folder-review"}
    ):
        result["faq_manage_folder"], result["faq_review_folder"] = teaching_folder_authority(user, org)
    if "faq_manage_group_leads" in wanted and "groups-registry" in sections:
        result["faq_manage_group_leads"] = can_manage_group_leads(request, org)
    if "faq_assign_roles" in wanted and sections.intersection({"role-assignment", "manage-roles"}):
        result["faq_assign_roles"] = membership_assignment_scope(user, org).has_structure_access
    if "faq_import_students" in wanted and sections.intersection({"student-intake", "student-admission"}):
        result["faq_import_students"] = can_import(user, org)
    if "faq_import_staff" in wanted and "teacher-intake" in sections:
        result["faq_import_staff"] = can_import_staff(user, org)
    if "faq_manage_programs" in wanted and "programs-registry" in sections:
        result["faq_manage_programs"] = can_manage_catalog(request)
    if "faq_merge_subjects" in wanted and "subject-catalog" in sections:
        result["faq_merge_subjects"] = can_merge_subjects(request)
    if "faq_create_rubric" in wanted and "registrar-catalog" in sections:
        result["faq_create_rubric"] = catalog_console.can_manage(user, org)
    if "faq_edit_curriculum" in wanted and "curriculum-editor" in sections:
        result["faq_edit_curriculum"] = (
            can_edit_plans(request)
            and get_permission_scope(user, org, "plan.edit", request=request).has_structure_access
        )
    if "faq_open_semester" in wanted and "semester-opening" in sections:
        result["faq_open_semester"] = (
            can_open_semester(request)
            and get_permission_scope(user, org, "semester.open", request=request).has_structure_access
        )
    if "faq_reset_accounts" in wanted and "account-password-reset" in sections:
        result["faq_reset_accounts"] = _can_reset(request)
    if "faq_manage_hr_contracts" in wanted and "hr-contracts" in sections:
        result["faq_manage_hr_contracts"] = contract_management_allowed(request)
    if "faq_read_hr_analytics" in wanted and "hr-analytics" in sections:
        result["faq_read_hr_analytics"] = hr_actor(request).has_access
    if "faq_read_accounting_report" in wanted and "accounting" in sections:
        result["faq_read_accounting_report"] = accounting_actor(request).has_access
    if "faq_manage_retake_placement" in wanted and "subgroup-placement" in sections:
        result["faq_manage_retake_placement"] = retake_access.can_manage(user, org)
    if "faq_write_course" in wanted and "my-courses" in sections:
        result["faq_write_course"] = request_has_permission(request, "course.create") and request_has_permission(
            request, "course.edit"
        )
    if "faq_edit_role_permissions" in wanted and "permission-editor" in sections:
        held, _ = _collect_actor_permissions(user, org)
        result["faq_edit_role_permissions"] = is_superadmin_user(user) or (
            has_permission(list(held), "role.assign") and has_permission(list(held), "role.edit")
        )
    if "faq_record_movement" in wanted and "student-registry" in sections:
        actor = people_actor(request)
        result["faq_record_movement"] = actor.can_view_registry and actor.can_move_students
    if "faq_manage_surveys" in wanted and sections.intersection({"surveys-builder", "evaluation-campaigns"}):
        result["faq_manage_surveys"] = can_manage_campaigns(user, org, request=request)
    if "faq_view_survey_results" in wanted and "evaluation-results" in sections:
        result["faq_view_survey_results"] = can_view_results(user, org, request=request)
    result = {key: value for key, value in result.items() if key in wanted}
    if getattr(request, "is_view_as", False):
        read_only = {"faq_view_own_workload", "faq_view_survey_results"}
        return {key: value and key in read_only for key, value in result.items()}
    return result
