"""student-org management section — public builder (setup + guard + orkestrasiya, FAZA 3.5)."""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import pgettext

from ....models import ProfileRole
from ..constants import STUDENT_ORG_MANAGEMENT_MIN_LEVEL
from ._pagination import _mgmt_section_pagination
from ._queries import _mgmt_section_queries

User = get_user_model()


def _staff_management_script_data():
    return {
        "i18n": {
            "addSelectedUsers": pgettext("staff.management", "Add selected users to the organization"),
            "addSelectedUsersCount": pgettext(
                "staff.management",
                "Add selected users to the organization ({count} selected)",
            ),
            "selectAtLeastOneStudent": pgettext("staff.management", "Select at least 1 student"),
            "selectAtLeastOneUser": pgettext("staff.management", "Select at least 1 user"),
            "studentRole": pgettext("membership_request.role", "Student"),
            "thisUser": pgettext("staff.management", "This user"),
            "withdrawSelectedInvites": pgettext(
                "staff.management",
                "Please confirm that you want to withdraw the selected invites.",
            ),
            "selectedInvites": pgettext("staff.management", "Selected invites:"),
            "selectInviteFirst": pgettext("staff.management", "Please select at least one invite first."),
            "confirmButtonDisabled": pgettext(
                "staff.management",
                "The confirm button is disabled in this state.",
            ),
            "confirmAddSelected": pgettext(
                "staff.management",
                "Please confirm that you want to add the selected user(s) to the organization.",
            ),
            "confirmAddSingle": pgettext(
                "staff.management",
                "Please confirm that you want to add this user to the organization.",
            ),
            "selectedUsers": pgettext("staff.management", "Selected users:"),
            "confirmInviteSelected": pgettext(
                "staff.management",
                "Please confirm that you want to invite the selected user(s).",
            ),
            "confirmInviteSingle": pgettext("staff.management", "Please confirm that you want to invite this user."),
        },
    }


def _build_student_org_management_section(
    *,
    request,
    organization,
    is_superadmin,
    user_level,
    default_view=None,
    teacher_student_only=False,
    can_manage_students=True,
    can_invite_members=True,
):
    student_search = request.GET.get("student_org_search", "")
    pending_search = request.GET.get("student_org_pending_search", "")
    unassigned_search = request.GET.get("student_org_unassigned_search", "")
    sent_invite_search = request.GET.get("student_org_sent_invite_search", "")
    teacher_staff_search = request.GET.get("student_org_ts_search", "")
    organization_search = request.GET.get("organization_search", "")
    organization_status_filter = (request.GET.get("organization_status", "") or "").strip().lower()
    organization_type_filter = (request.GET.get("organization_type", "") or "").strip().lower()
    superadmin_user_ids = list(
        User.objects.filter(Q(is_superuser=True) | Q(profile__role=ProfileRole.SUPERADMIN)).values_list("id", flat=True)
    )

    allowed_management_views = {"students", "teachers", "staff"}
    if teacher_student_only:
        allowed_management_views = {"students"}
    if is_superadmin:
        allowed_management_views.add("organizations")

    fallback_management_view = default_view or (
        "organizations" if is_superadmin and organization is None else "students"
    )
    management_view = (request.GET.get("management_view") or fallback_management_view).strip().lower()
    if management_view not in allowed_management_views:
        management_view = (
            fallback_management_view if fallback_management_view in allowed_management_views else "students"
        )

    student_tab = (request.GET.get("student_tab") or "members").strip().lower()
    if student_tab not in {"members", "pending", "unassigned", "invites"}:
        student_tab = "members"

    teacher_tab = (request.GET.get("teacher_tab") or "members").strip().lower()
    if teacher_tab not in {"members", "requests", "unassigned", "invites"}:
        teacher_tab = "members"

    staff_tab = (request.GET.get("staff_tab") or "members").strip().lower()
    if staff_tab not in {"members", "requests", "unassigned", "invites"}:
        staff_tab = "members"

    section = {
        "organization": organization,
        "is_superadmin": is_superadmin,
        "teacher_student_only": teacher_student_only,
        "active_management_view": management_view,
        "active_student_tab": student_tab,
        "active_teacher_tab": teacher_tab,
        "active_staff_tab": staff_tab,
        "management_view_options": [],
        "student_tab_options": [],
        "teacher_tab_options": [],
        "staff_tab_options": [],
        "students": [],
        "pending_requested_students": [],
        "unassigned_students": [],
        "sent_student_invites": [],
        "teacher_members": [],
        "staff_members": [],
        "unassigned_teachers": [],
        "sent_teacher_invites": [],
        "unassigned_staff": [],
        "sent_staff_invites": [],
        "pending_teacher_requests": [],
        "pending_staff_requests": [],
        "pending_teacher_staff_requests": [],
        "students_total_count": 0,
        "pending_requested_students_total_count": 0,
        "unassigned_students_total_count": 0,
        "sent_student_invites_total_count": 0,
        "teacher_members_total_count": 0,
        "pending_teacher_requests_total_count": 0,
        "unassigned_teachers_total_count": 0,
        "sent_teacher_invites_total_count": 0,
        "staff_members_total_count": 0,
        "pending_staff_requests_total_count": 0,
        "unassigned_staff_total_count": 0,
        "sent_staff_invites_total_count": 0,
        "organization_records": [],
        "student_search_query": student_search,
        "pending_search_query": pending_search,
        "unassigned_search_query": unassigned_search,
        "sent_invite_search_query": sent_invite_search,
        "teacher_staff_search_query": teacher_staff_search,
        "organization_search_query": organization_search,
        "organization_status_filter": organization_status_filter,
        "organization_type_filter": organization_type_filter,
        "post_next_url": "",
        "access_denied_message": "",
        "can_manage_students": False,
        "can_invite_members": False,
        "pending_org_count": 0,
        "students_page_param": "student_org_members_page",
        "students_pagination_query": "",
        "pending_page_param": "student_org_pending_page",
        "pending_pagination_query": "",
        "unassigned_page_param": "student_org_unassigned_page",
        "unassigned_pagination_query": "",
        "sent_invites_page_param": "student_org_sent_invites_page",
        "sent_invites_pagination_query": "",
        "teacher_staff_page_param": "student_org_ts_page",
        "teacher_staff_pagination_query": "",
        "teacher_members_page_param": "teacher_members_page",
        "teacher_members_pagination_query": "",
        "staff_members_page_param": "staff_members_page",
        "staff_members_pagination_query": "",
        "teacher_requests_page_param": "teacher_requests_page",
        "teacher_requests_pagination_query": "",
        "teacher_unassigned_page_param": "teacher_unassigned_page",
        "teacher_unassigned_pagination_query": "",
        "teacher_invites_page_param": "teacher_invites_page",
        "teacher_invites_pagination_query": "",
        "staff_requests_page_param": "staff_requests_page",
        "staff_requests_pagination_query": "",
        "staff_unassigned_page_param": "staff_unassigned_page",
        "staff_unassigned_pagination_query": "",
        "staff_invites_page_param": "staff_invites_page",
        "staff_invites_pagination_query": "",
        "organizations_page_param": "organization_page",
        "organizations_pagination_query": "",
        "staff_management_script_data": _staff_management_script_data(),
    }

    if organization is None:
        if is_superadmin and management_view == "organizations":
            # Superadmin "organizations" view — extracted to a dedicated,
            # unit-testable service (FAZA 9). Lazy import keeps the
            # _helpers <-> services dependency one-directional.
            from ....services.org_management import build_superadmin_organizations_view

            return build_superadmin_organizations_view(
                request=request,
                section=section,
                organization_search=organization_search,
                organization_status_filter=organization_status_filter,
                organization_type_filter=organization_type_filter,
            )

        section["access_denied_message"] = "Aktiv təşkilat tapılmadı."
        return section

    if not is_superadmin and not teacher_student_only and user_level < STUDENT_ORG_MANAGEMENT_MIN_LEVEL:
        section["access_denied_message"] = (
            "Bu bölmə üçün minimum HR, təşkilat admini və ya daha yüksək səviyyə tələb olunur."
        )
        return section

    teacher_members, staff_members = _mgmt_section_queries(
        section=section,
        request=request,
        organization=organization,
        is_superadmin=is_superadmin,
        superadmin_user_ids=superadmin_user_ids,
        student_search=student_search,
        pending_search=pending_search,
        unassigned_search=unassigned_search,
        sent_invite_search=sent_invite_search,
        teacher_staff_search=teacher_staff_search,
    )
    return _mgmt_section_pagination(
        section=section,
        request=request,
        organization=organization,
        is_superadmin=is_superadmin,
        management_view=management_view,
        student_tab=student_tab,
        teacher_tab=teacher_tab,
        staff_tab=staff_tab,
        can_manage_students=can_manage_students,
        can_invite_members=can_invite_members,
        organization_search=organization_search,
        organization_status_filter=organization_status_filter,
        organization_type_filter=organization_type_filter,
        student_search=student_search,
        pending_search=pending_search,
        unassigned_search=unassigned_search,
        sent_invite_search=sent_invite_search,
        teacher_staff_search=teacher_staff_search,
        teacher_members=teacher_members,
        staff_members=staff_members,
    )
