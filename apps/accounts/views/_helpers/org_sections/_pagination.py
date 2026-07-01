"""student-org management section — səhifələmə/tab (part 2)."""

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.urls import reverse

from apps.notifications.models import StudentOrganizationRequestStatus
from apps.organizations.models import Membership
from apps.organizations.models import Organization as OrganizationModel

from ..formatting import _append_query_params, _query_string


def _mgmt_section_pagination(
    *,
    section,
    request,
    organization,
    is_superadmin,
    management_view,
    student_tab,
    teacher_tab,
    staff_tab,
    can_manage_students,
    can_invite_members,
    organization_search,
    organization_status_filter,
    organization_type_filter,
    student_search,
    pending_search,
    unassigned_search,
    sent_invite_search,
    teacher_staff_search,
    teacher_members,
    staff_members,
):
    section["teacher_members"] = Paginator(
        teacher_members,
        12,
    ).get_page(request.GET.get(section["teacher_members_page_param"]))
    section["staff_members"] = Paginator(
        staff_members,
        12,
    ).get_page(request.GET.get(section["staff_members_page_param"]))

    for pending_request in section["pending_requested_students"].object_list:
        pending_request.request_display_status = (
            "Gözləyir" if pending_request.status == StudentOrganizationRequestStatus.PENDING else "Bağlanıb"
        )
        pending_request.request_display_class = (
            "warning" if pending_request.status == StudentOrganizationRequestStatus.PENDING else "secondary"
        )

        profile = getattr(pending_request.user, "profile", None)
        if (
            profile
            and profile.organization == organization
            and pending_request.status == StudentOrganizationRequestStatus.PENDING
        ):
            pending_request.request_note = "İstifadəçi artıq bu təşkilatın üzvüdür."
            pending_request.request_is_actionable = False
            continue

        active_other_org_name = ""
        if profile and profile.organization and profile.organization != organization:
            active_other_org_name = profile.organization.name

        if not active_other_org_name and pending_request.status == StudentOrganizationRequestStatus.PENDING:
            active_other_membership = (
                Membership.objects.filter(user=pending_request.user, is_active=True)
                .exclude(organization=organization)
                .select_related("organization", "role")
                .order_by("-is_primary", "-role__level")
                .first()
            )
            if active_other_membership:
                active_other_org_name = active_other_membership.organization.name

        if active_other_org_name and pending_request.status == StudentOrganizationRequestStatus.PENDING:
            pending_request.request_note = f"İstifadəçi artıq {active_other_org_name} təşkilatının üzvüdür."
            pending_request.request_is_actionable = False
        elif pending_request.status == StudentOrganizationRequestStatus.AUTO_CLOSED:
            pending_request.request_note = (
                pending_request.resolution_note or ""
            ).strip() or "Bu müraciət avtomatik bağlanıb."
            pending_request.request_is_actionable = False
        else:
            pending_request.request_note = (pending_request.resolution_note or "").strip()
            pending_request.request_is_actionable = True

    organization_records = OrganizationModel.objects.none()
    if is_superadmin:
        organization_records = (
            OrganizationModel.objects.select_related("owner")
            .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
            .order_by("name")
        )
        if organization_search:
            organization_records = organization_records.filter(
                Q(name__icontains=organization_search)
                | Q(slug__icontains=organization_search)
                | Q(organization_identifier__icontains=organization_search)
                | Q(license_identifier__icontains=organization_search)
                | Q(owner__username__icontains=organization_search)
                | Q(owner__email__icontains=organization_search)
            )
        if organization_type_filter:
            organization_records = organization_records.filter(org_type=organization_type_filter)
        if organization_status_filter == "active":
            organization_records = organization_records.filter(is_active=True, status="active")
        elif organization_status_filter == "pending":
            organization_records = organization_records.filter(status="pending")
        elif organization_status_filter == "suspended":
            organization_records = organization_records.filter(status="suspended")
        elif organization_status_filter == "inactive":
            organization_records = organization_records.filter(is_active=False)

        section["organization_records"] = Paginator(
            organization_records,
            12,
        ).get_page(request.GET.get(section["organizations_page_param"]))
        section["pending_org_count"] = OrganizationModel.objects.filter(status="pending").count()

    base_query_kwargs = {
        "section": "student-organization-management",
        "management_view": management_view,
        "student_tab": student_tab,
        "teacher_tab": teacher_tab,
        "staff_tab": staff_tab,
        "student_org_search": student_search,
        "student_org_pending_search": pending_search,
        "student_org_unassigned_search": unassigned_search,
        "student_org_sent_invite_search": sent_invite_search,
        "student_org_ts_search": teacher_staff_search,
        "organization_search": organization_search,
        "organization_status": organization_status_filter,
        "organization_type": organization_type_filter,
    }
    section["students_pagination_query"] = _query_string(**base_query_kwargs)
    section["pending_pagination_query"] = _query_string(**base_query_kwargs)
    section["unassigned_pagination_query"] = _query_string(**base_query_kwargs)
    section["sent_invites_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_staff_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_members_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_members_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_requests_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_unassigned_pagination_query"] = _query_string(**base_query_kwargs)
    section["teacher_invites_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_requests_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_unassigned_pagination_query"] = _query_string(**base_query_kwargs)
    section["staff_invites_pagination_query"] = _query_string(**base_query_kwargs)
    section["organizations_pagination_query"] = _query_string(**base_query_kwargs)
    section["post_next_url"] = _append_query_params(
        reverse("accounts:student_organization_management"),
        **{key: value for key, value in base_query_kwargs.items() if key != "section"},
    )

    section["student_tab_options"] = [
        {
            "value": "members",
            "label": "Tələbələr",
            "count": section["students_total_count"],
        },
        {
            "value": "pending",
            "label": "Müraciətlər",
            "count": section["pending_requested_students_total_count"],
        },
        {
            "value": "unassigned",
            "label": "Dəvətsizlər",
            "count": section["unassigned_students_total_count"],
        },
        {
            "value": "invites",
            "label": "Dəvətlər",
            "count": section["sent_student_invites_total_count"],
        },
    ]
    section["teacher_tab_options"] = [
        {
            "value": "members",
            "label": "Müəllimlər",
            "count": section["teacher_members_total_count"],
        },
        {
            "value": "requests",
            "label": "Müraciətlər",
            "count": section["pending_teacher_requests_total_count"],
        },
        {
            "value": "unassigned",
            "label": "Dəvətsizlər",
            "count": section["unassigned_teachers_total_count"],
        },
        {
            "value": "invites",
            "label": "Dəvətlər",
            "count": section["sent_teacher_invites_total_count"],
        },
    ]
    section["staff_tab_options"] = [
        {
            "value": "members",
            "label": "Staff",
            "count": section["staff_members_total_count"],
        },
        {
            "value": "requests",
            "label": "Müraciətlər",
            "count": section["pending_staff_requests_total_count"],
        },
        {
            "value": "unassigned",
            "label": "Dəvətsizlər",
            "count": section["unassigned_staff_total_count"],
        },
        {
            "value": "invites",
            "label": "Dəvətlər",
            "count": section["sent_staff_invites_total_count"],
        },
    ]
    section["management_view_options"] = [
        {
            "value": "students",
            "label": "Tələbələr",
            "count": section["students_total_count"],
        },
        {
            "value": "teachers",
            "label": "Müəllimlər",
            "count": (
                section["teacher_members_total_count"]
                + section["pending_teacher_requests_total_count"]
                + section["unassigned_teachers_total_count"]
                + section["sent_teacher_invites_total_count"]
            ),
        },
        {
            "value": "staff",
            "label": "Staff",
            "count": (
                section["staff_members_total_count"]
                + section["pending_staff_requests_total_count"]
                + section["unassigned_staff_total_count"]
                + section["sent_staff_invites_total_count"]
            ),
        },
    ]
    if is_superadmin:
        section["management_view_options"].append(
            {
                "value": "organizations",
                "label": "Təşkilatlar",
                "count": section["organization_records"].paginator.count,
            }
        )

    section["can_manage_students"] = bool(can_manage_students)
    section["can_invite_members"] = bool(can_invite_members)
    return section
